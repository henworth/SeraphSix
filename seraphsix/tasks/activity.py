import asyncio
import itertools
import logging

from tortoise.functions import Max, Count
from tortoise.exceptions import DoesNotExist
from tortoise.expressions import Subquery
from typing import Tuple

from seraphsix import constants
from seraphsix.errors import PrivateHistoryError
from seraphsix.models.database import ClanMember, Game, GameMember, Member
from seraphsix.models.destiny import (
    Game as GameApi, ClanGame, DestinyProfileResponse, DestinyActivityResponse, DestinyPGCRResponse
)
from seraphsix.tasks.core import execute_pydest, get_cached_members, get_primary_membership
from seraphsix.tasks.parsing import member_hash, member_hash_db


log = logging.getLogger(__name__)


async def get_activity_history(ctx, platform_id, member_id, char_id, count=250, full_sync=False, mode=0):
    destiny = ctx['destiny']

    page = 0
    activities = []

    data = await execute_pydest(
        destiny.api.get_activity_history,
        platform_id, member_id, char_id, count=count, page=page, mode=mode,
        return_type=DestinyActivityResponse
    )
    if data.response:
        if full_sync:
            while data.response.activities:
                page += 1
                if activities:
                    activities.extend(data.response.activities)
                else:
                    activities = data.response.activities
                data = await execute_pydest(
                    destiny.api.get_activity_history,
                    platform_id, member_id, char_id, count=count, page=page, mode=mode,
                    return_type=DestinyActivityResponse
                )
        else:
            activities = data.response.activities
            if not activities:
                activities = []
            elif len(activities) == count:
                log.debug(
                    f'Activity count for {platform_id}-{member_id} ({char_id}) '
                    f'equals {count} but full sync is disabled'
                )
    return activities


async def get_pgcr(ctx, activity_id):
    destiny = ctx['destiny']
    data = await execute_pydest(
        destiny.api.get_post_game_carnage_report, activity_id, return_type=DestinyPGCRResponse)
    return data.response


async def decode_activity(ctx, reference_id, definition):
    destiny = ctx['destiny']
    await execute_pydest(destiny.update_manifest, return_type=None)
    return await execute_pydest(destiny.decode_hash, reference_id, definition, return_type=None)


async def get_activity_list(ctx, platform_id, member_id, characters, count, full_sync=False, mode=0):
    tasks = [
        get_activity_history(ctx, platform_id, member_id, character, count, full_sync, mode)
        for character in characters
    ]
    try:
        activities = await asyncio.gather(*tasks)
    except PrivateHistoryError:
        log.info(f"Member {platform_id}-{member_id} has set their account private")
        all_activities = []
    else:
        all_activities = list(itertools.chain.from_iterable(activities))
    return all_activities


async def get_last_active(ctx, member_db=None, platform_id=None, member_id=None):
    acct_last_active = None
    if member_db and not platform_id and not member_id:
        platform_id, member_id, _ = get_primary_membership(member_db)

    profile = await execute_pydest(
        ctx['destiny'].api.get_profile, platform_id, member_id, [constants.COMPONENT_PROFILES],
        return_type=DestinyProfileResponse
    )
    if not profile.response:
        log.error(f"Could not get character data for {platform_id}-{member_id}: {profile.message}")
    else:
        acct_last_active = profile.response.profile.data.date_last_played
        log.debug(f"Found last active date for {platform_id}-{member_id}: {acct_last_active}")
    return acct_last_active


async def save_last_active(ctx, member_id):
    clanmember_db = await ClanMember.get(member__id=member_id).prefetch_related("member")
    last_active = await get_last_active(ctx, clanmember_db.member)
    clanmember_db.last_active = last_active
    await clanmember_db.save()


async def store_last_active(ctx, guild_id, guild_name):
    redis_jobs = ctx['redis_jobs']
    for member_db in await get_cached_members(ctx, guild_id, guild_name):
        await redis_jobs.enqueue_job(
            'save_last_active', member_db.member.id, _job_id=f'save_last_active-{member_db.member.id}'
        )
    log.info(f"Queued last active collection for all members of {guild_name} ({guild_id})")


async def get_game_counts(database, game_mode, member_db=None):
    base_query = Game.annotate(count=Count('id'))
    modes = [mode_id for mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode)]

    if member_db:
        query = base_query.filter(
            members__member=member_db.member,
            members__member__clans__clan=member_db.clan,
            mode_id__in=modes
        )
    else:
        query = base_query.filter(mode_id__in=modes)

    counts = {}
    for row in await query.group_by('mode_id').values('mode_id', 'count'):
        game_title = constants.MODE_MAP[row['mode_id']]['title']
        counts[game_title] = row['count']
    return counts


async def get_sherpa_time_played(member_db: object) -> Tuple[int, list]:
    await member_db.member
    clan_sherpas = ClanMember.filter(
        is_sherpa=True, id__not=member_db.id
    ).only('member_id')

    full_list = list(constants.SUPPORTED_GAME_MODES.values())
    mode_list = list(set([mode for sublist in full_list for mode in sublist]))

    all_games = GameMember.filter(
        game__mode_id__in=mode_list, member=member_db.member, time_played__not_isnull=True
    ).only('game_id')

    sherpa_games = GameMember.filter(
        game_id__in=Subquery(all_games), member_id__in=Subquery(clan_sherpas), time_played__not_isnull=True
    ).distinct().only('game_id')

    # Ideally one more optimal query whould look like this, which would return all the data we'd need
    # in one query. But this is not currently possible with Tortoise.
    # SELECT DISTINCT ON (m.game_id) m.game_id, m.member_id, t.sherpa_time
    # FROM(
    # 	SELECT "game_id" "game_id", MAX("time_played") "sherpa_time"
    # 	FROM "gamemember"
    # 	WHERE "game_id" IN(2078188, 2078189)
    # 	AND "member_id" IN(7, 75, 92, 108, 14, 11, 56, 95, 38, 167, 220, 48, 263, 47)
    # 	AND NOT "time_played" IS NULL
    # 	GROUP BY "game_id"
    # ) AS t
    # JOIN gamemember m ON m.game_id = t.game_id

    query = await GameMember.annotate(
        sherpa_time=Max('time_played')
    ).filter(
        game_id__in=Subquery(sherpa_games),
        member_id__in=Subquery(clan_sherpas),
        sherpa_time__not_isnull=True
    ).group_by(
        'game_id'
    ).values('game_id', 'sherpa_time')

    total_time = 0
    for result in query:
        total_time += result['sherpa_time']

    # https://github.com/tortoise/tortoise-orm/issues/780
    all_games = GameMember.filter(
        game__mode_id__in=mode_list, member=member_db.member, time_played__not_isnull=True
    ).only('game_id')

    sherpa_games = GameMember.filter(
        game_id__in=Subquery(all_games), member_id__in=Subquery(clan_sherpas), time_played__not_isnull=True
    ).distinct().only('game_id')

    sherpa_ids = GameMember.filter(
        game_id__in=Subquery(sherpa_games), member_id__in=Subquery(clan_sherpas), time_played__not_isnull=True
    ).distinct().values_list('member__discord_id', flat=True)

    return (total_time, sherpa_ids)


async def store_all_games(ctx, guild_id, guild_name, count=30, recent=True):
    database = ctx['database']
    redis_jobs = ctx['redis_jobs']

    try:
        clan_dbs = await database.get_clans_by_guild(guild_id)
    except DoesNotExist:
        log.info(f"No clans found for {guild_name} ({guild_id})")
        return

    tasks = []
    if recent:
        log.info(f"Finding all games for members of {guild_name} ({guild_id}) active in the last hour")

        for clan_db in clan_dbs:
            if not clan_db.activity_tracking:
                log.info(f"Clan activity tracking disabled for Clan {clan_db.name}, skipping")
                continue

            tasks.extend([
                get_member_activity(ctx, clanmember.member, count=count, full_sync=False)
                for clanmember in await database.get_clan_members_active(clan_db, hours=1)
            ])
    else:
        for clan_db in clan_dbs:
            if not clan_db.activity_tracking:
                log.info(f"Clan activity tracking disabled for Clan {clan_db.name}, skipping")
                continue

            tasks.extend([
                get_member_activity(ctx, clanmember.member, count=count, full_sync=False)
                for clanmember in await database.get_clan_members([clan_db.clan_id])
            ])

    results = await asyncio.gather(*tasks)

    # Create a list of unique activities by first joining the gather results,
    # then iterate that list for unique instance id's
    all_activities = list(itertools.chain.from_iterable(results))
    all_activities_dict = {}
    for activity in all_activities:
        key = activity.activity_details.instance_id
        if key not in all_activities_dict:
            all_activities_dict[key] = activity
    unique_activities = list(all_activities_dict.values())

    tasks = []
    for activity in unique_activities:
        activity_id = activity.activity_details.instance_id
        await redis_jobs.enqueue_job(
            'process_activity', activity, guild_id, guild_name, _job_id=f'process_activity-{activity_id}'
        )

    log.info(
        f"Processed {len(unique_activities)} games for members of {guild_name} ({guild_id}) active in the last hour"
    )


async def get_member_activity(ctx, member_db, count=250, full_sync=False, mode=0):
    platform_id, member_id, _ = get_primary_membership(member_db)
    characters = await get_characters(ctx, member_id, platform_id)
    if not characters:
        log.error(f"Could not get character data for {platform_id}-{member_id} - {characters}")
    else:
        return await get_activity_list(ctx, platform_id, member_id, characters, count, full_sync, mode)


async def get_characters(ctx, member_id, platform_id):
    destiny = ctx['destiny']
    retval = None
    profile = await execute_pydest(
        destiny.api.get_profile, platform_id, member_id, [constants.COMPONENT_PROFILES],
        return_type=DestinyProfileResponse
    )
    if profile.response:
        retval = profile.response.profile.data.character_ids
    return retval


async def process_activity(ctx, activity, guild_id, guild_name, player_check=False):
    database = ctx['database']
    game = GameApi(activity)
    member_dbs = await get_cached_members(ctx, guild_id, guild_name)

    clan_dbs = await database.get_clans_by_guild(guild_id)
    clan_ids = [clan.id for clan in clan_dbs]

    game_db = await Game.get_or_none(instance_id=game.instance_id)
    if not game_db:
        log.debug(f"Skipping missing player check because game {game.instance_id} does not exist")
    elif player_check:
        pgcr = await get_pgcr(ctx, game.instance_id)
        clan_game = ClanGame(pgcr, member_dbs)
        api_players_db = [
            await database.get_clan_member_by_platform(player.membership_id, player.membership_type, clan_ids)
            for player in clan_game.clan_players
        ]

        db_players_db = await ClanMember.filter(
            member__games__game__instance_id=game.instance_id
        ).prefetch_related('member')

        try:
            missing_player_dbs = set(api_players_db).symmetric_difference(
                set([db_player for db_player in db_players_db]))
        except TypeError:
            log.debug(f"api_players_db: {api_players_db} db_players_db: {db_players_db}")
            raise

        if len(missing_player_dbs) > 0:
            for missing_player_db in missing_player_dbs:
                member_db = missing_player_db.member
                for game_player in clan_game.clan_players:
                    if member_hash(game_player) == member_hash_db(member_db, game_player.membership_type) \
                            and game.date > missing_player_db.join_date:
                        log.debug(f'Found missing player in {game.instance_id} {game_player}')
                        await database.create_game_member(
                            game_player, game_db, member_dbs[0].clan_id, member_db)
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
    redis_jobs = ctx['redis_jobs']

    member_db = await Member.get(id=member_db_id)
    activities = await get_member_activity(ctx, member_db, count, full_sync, mode)

    for activity in activities:
        activity_id = activity.activity_details.instance_id
        await redis_jobs.enqueue_job(
            'process_activity', activity, guild_id, guild_name, _job_id=f'process_activity-{activity_id}'
        )
