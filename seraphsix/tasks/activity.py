import asyncio
import itertools
import logging

from peewee import DoesNotExist, fn
from playhouse.shortcuts import dict_to_model
from seraphsix import constants
from seraphsix.cogs.utils.helpers import bungie_date_as_utc
from seraphsix.database import ClanMember, Game, GameMember, Guild, Member
from seraphsix.models.destiny import Game as GameApi, ClanGame
from seraphsix.tasks.core import execute_pydest, get_cached_members
from seraphsix.tasks.parsing import member_hash, member_hash_db, parse_platform

log = logging.getLogger(__name__)


async def get_activity_history(ctx, platform_id, member_id, char_id, count=250, full_sync=False, mode=0):
    destiny = ctx['destiny']

    page = 0
    activities = []

    data = await execute_pydest(
        destiny.api.get_activity_history, platform_id, member_id, char_id, count=count, page=page, mode=mode)
    if data:
        if full_sync:
            while 'activities' in data:
                page += 1
                if activities:
                    activities.extend(data['activities'])
                else:
                    activities = data['activities']
                data = await execute_pydest(
                    destiny.api.get_activity_history,
                    platform_id, member_id, char_id, count=count, page=page, mode=mode)
        else:
            activities = data['activities']
            if len(activities) == count:
                log.debug(
                    f'Activity count for {platform_id}-{member_id} ({char_id}) '
                    f'equals {count} but full sync is disabled'
                )
    return activities


async def get_pgcr(ctx, activity_id):
    destiny = ctx['destiny']
    return await execute_pydest(destiny.api.get_post_game_carnage_report, activity_id)


async def decode_activity(ctx, reference_id):
    destiny = ctx['destiny']
    await execute_pydest(destiny.update_manifest)
    return await execute_pydest(destiny.decode_hash, reference_id)


async def get_activity_list(ctx, platform_id, member_id, characters, count, full_sync=False, mode=0):
    tasks = [
        get_activity_history(ctx, platform_id, member_id, character, count, full_sync, mode)
        for character in list(characters.keys())
    ]
    activities = await asyncio.gather(*tasks)
    all_activities = list(itertools.chain.from_iterable(activities))
    return all_activities


async def get_last_active(ctx, member_db):
    platform_id = member_db.platform_id
    member_id, _ = parse_platform(member_db.member, platform_id)

    acct_last_active = None
    try:
        characters = await get_characters(ctx, member_id, platform_id)
        characters = characters.items()
    except AttributeError:
        log.error(f"Could not get character data for {platform_id}-{member_id}")
        return acct_last_active

    for _, character in characters:
        char_last_active = bungie_date_as_utc(character['dateLastPlayed'])
        if not acct_last_active or char_last_active > acct_last_active:
            acct_last_active = char_last_active
            log.debug(f"Found last active date for {platform_id}-{member_id}: {acct_last_active}")
    return acct_last_active


async def store_last_active(ctx, guild_id, guild_name):
    database = ctx['database']
    for member in await get_cached_members(ctx, guild_id, guild_name):
        member_db = dict_to_model(ClanMember, member)
        last_active = await get_last_active(ctx, member_db)
        member_db.last_active = last_active
        await database.update(member_db)
    log.info(f"Found last active dates for all members of {guild_name} ({guild_id})")


async def get_game_counts(database, game_mode, member_db=None):
    base_query = Game.select(Game.mode_id, fn.Count(Game.id))
    modes = [mode_id for mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode)]

    if member_db:
        query = base_query.join(GameMember).join(Member).join(ClanMember).where(
            (Member.id == member_db.id) &
            (ClanMember.clan_id == member_db.clanmember.clan_id) &
            (Game.mode_id << modes)
        )
    else:
        query = base_query.where(Game.mode_id << modes)

    data = await database.execute(query.group_by(Game.mode_id))
    counts = {}
    for row in data._rows:
        mode_id, count = row
        game_title = constants.MODE_MAP[mode_id]['title']
        counts[game_title] = count
    return counts


async def get_sherpa_time_played(database, member_db):
    clan_sherpas = Member.select(Member.id).join(ClanMember).where((ClanMember.is_sherpa) & (Member.id != member_db.id))

    full_list = list(constants.SUPPORTED_GAME_MODES.values())
    mode_list = list(set([mode for sublist in full_list for mode in sublist]))

    all_games = Game.select().join(GameMember).where(
        (GameMember.member_id == member_db.id) & (Game.mode_id << mode_list)
    )

    sherpa_games = Game.select(Game.id.distinct()).join(GameMember).where(
        (Game.id << all_games) & (GameMember.member_id << clan_sherpas)
    )

    query = GameMember.select(
        GameMember.member_id, GameMember.game_id, fn.MAX(GameMember.time_played).alias('sherpa_time')
    ).where(
        (GameMember.game_id << sherpa_games) & (GameMember.member_id << clan_sherpas)
    ).group_by(
        GameMember.game_id, GameMember.member_id
    ).order_by(
        GameMember.game_id, fn.MAX(GameMember.time_played).desc()
    ).distinct(GameMember.game_id)

    total_time = 0
    unique_sherpas = set()
    unique_games = set()
    try:
        results = await database.execute(query)
    except DoesNotExist:
        return (total_time, unique_sherpas)

    for result in results:
        unique_sherpas.add(result.member_id)
        unique_games.add(result.game_id)
        total_time += result.sherpa_time if result.sherpa_time else 0

    all_game_sherpas_query = GameMember.select(Member.id.distinct()).join(Member).switch().join(Game).where(
        (Game.id << sherpa_games) & (GameMember.member_id << clan_sherpas)
    )
    try:
        all_game_sherpas_db = await database.execute(all_game_sherpas_query)
    except DoesNotExist:
        return (total_time, unique_sherpas)

    for sherpa in all_game_sherpas_db:
        unique_sherpas.add(sherpa)

    return (total_time, unique_sherpas)


async def store_all_games(ctx, guild_id, guild_name, count=30):
    database = ctx['database']
    redis_jobs = ctx['redis_jobs']
    guild_db = await database.get(Guild, guild_id=guild_id)

    try:
        clan_dbs = await database.get_clans_by_guild(guild_id)
    except DoesNotExist:
        log.info(f"No clans found for {guild_name} ({guild_id})")
        return

    log.info(f"Finding all games for members of {guild_name} ({guild_id}) active in the last hour")

    tasks = []
    active_member_dbs = []
    all_member_dbs = []
    for clan_db in clan_dbs:
        if not clan_db.activity_tracking:
            log.info(f"Clan activity tracking disabled for Clan {clan_db.name}, skipping")
            continue

        active_members = await database.get_clan_members_active(clan_db.id, hours=1)
        all_members = await get_cached_members(ctx, guild_id, guild_name)

        if guild_db.aggregate_clans:
            active_member_dbs.extend(active_members)
            all_member_dbs.extend(all_members)
        else:
            active_member_dbs = active_members
            all_member_dbs = all_members

        tasks.extend([
            get_member_activity(ctx, member_db, count=count, full_sync=False)
            for member_db in active_member_dbs
        ])

    results = await asyncio.gather(*tasks)

    # Create a list of unique activities by first joining the gather results,
    # then iterate that list for unique instance id's
    all_activities = list(itertools.chain.from_iterable(results))
    all_activities_dict = {}
    for activity in all_activities:
        key = activity['activityDetails']['instanceId']
        if key not in all_activities_dict:
            all_activities_dict[key] = activity
    unique_activities = list(all_activities_dict.values())

    for activity in unique_activities:
        activity_id = activity['activityDetails']['instanceId']
        await redis_jobs.enqueue_job(
            'process_activity', activity, guild_id, _job_id=f'process_activity-{activity_id}'
        )

    log.info(
        f"Found {len(unique_activities)} games for members of {guild_name} ({guild_id}) active in the last hour"
    )


async def get_member_activity(ctx, member_db, count=250, full_sync=False, mode=0):
    platform_id = member_db.clanmember.platform_id
    member_id, member_username = parse_platform(member_db, platform_id)

    try:
        characters = await get_characters(ctx, member_id, platform_id)
    except (KeyError, TypeError):
        log.error(f"Could not get character data for {platform_id}-{member_id}")
    else:
        return await get_activity_list(ctx, platform_id, member_id, characters, count, full_sync, mode)


async def get_characters(ctx, member_id, platform_id):
    destiny = ctx['destiny']
    retval = None
    data = await execute_pydest(
        destiny.api.get_profile, platform_id, member_id, [constants.COMPONENT_CHARACTERS])
    if data:
        retval = data['characters']['data']
    return retval


async def process_activity(ctx, activity, guild_id, guild_name):
    database = ctx['database']
    game = GameApi(activity)
    clan_members = await get_cached_members(ctx, guild_id, guild_name)

    member_dbs = []
    for member in clan_members:
        member_dbs.append(dict_to_model(ClanMember, member))

    try:
        game_db = await database.get(Game, instance_id=game.instance_id)
    except DoesNotExist:
        log.debug(f"Skipping missing player check because game {game.instance_id} does not exist")
    else:
        pgcr = await get_pgcr(ctx, game.instance_id)
        clan_game = ClanGame(pgcr, member_dbs)
        api_players_db = [
            await database.get_clan_member_by_platform(player.membership_id, player.membership_type, 1)
            for player in clan_game.clan_players
        ]

        query = Member.select(Member, ClanMember).join(
            GameMember).switch(Member).join(ClanMember).switch(GameMember).join(Game).where(
            (Game.instance_id == game.instance_id)
        )
        db_players_db = await database.execute(query)
        missing_player_dbs = set(api_players_db).symmetric_difference(set([db_player for db_player in db_players_db]))

        if len(missing_player_dbs) > 0:
            for missing_player_db in missing_player_dbs:
                for game_player in clan_game.clan_players:
                    if member_hash(game_player) == member_hash_db(missing_player_db, game_player.membership_type) \
                            and game.date > missing_player_db.clanmember.join_date:
                        log.debug(f'Found missing player in {game.instance_id} {game_player}')
                        await database.create_game_member(
                            game_player, game_db, member_dbs[0].clan_id, missing_player_db)
        else:
            log.debug(f"Continuing because game {game.instance_id} exists")
        return

    supported_modes = set(sum(constants.SUPPORTED_GAME_MODES.values(), []))
    if game.mode_id not in supported_modes:
        log.debug(f'Continuing because game {game.instance_id} mode {game.mode_id} not supported')
        return

    pgcr = await get_pgcr(ctx, game.instance_id)
    if not pgcr:
        log.error(f"Continuing because error with pgcr for game {game.instance_id}")
        return

    clan_game = ClanGame(pgcr, member_dbs)
    game_mode_details = constants.MODE_MAP[game.mode_id]
    if len(clan_game.clan_players) < game_mode_details['threshold']:
        log.debug(f"Continuing because not enough clan players in game {game.instance_id}")
        return

    game_db = await database.create_game(clan_game)
    if not game_db:
        log.error(f"Continuing because error with storing game {game.instance_id}")
        return

    await database.create_clan_game(game_db, clan_game, clan_game.clan_id)
    game_title = game_mode_details['title'].title()
    log.info(f"{game_title} game id {game.instance_id} on {game.date} created")


async def store_member_history(ctx, member_db_id, guild_id, guild_name, full_sync=False, count=250, mode=0):
    database = ctx['database']
    redis_jobs = ctx['redis_jobs']

    query = Member.select(Member, ClanMember).join(ClanMember).where(Member.id == member_db_id)
    member_db = await database.get(query)
    activities = await get_member_activity(ctx, member_db, count, full_sync, mode)

    for activity in activities:
        activity_id = activity['activityDetails']['instanceId']
        await redis_jobs.enqueue_job(
            'process_activity', activity, guild_id, guild_name, _job_id=f'process_activity-{activity_id}'
        )
