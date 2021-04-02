import asyncio
import backoff
import itertools
import logging

from peewee import DoesNotExist, fn, IntegrityError
from pydest.pydest import PydestException, PydestPrivateHistoryException, PydestMaintenanceException
from seraphsix import constants
from seraphsix.cogs.utils.helpers import bungie_date_as_utc
from seraphsix.database import ClanGame as ClanGameDb, ClanMember, Game, GameMember, Guild, Member
from seraphsix.errors import MaintenanceError
from seraphsix.models.destiny import Game as GameApi, ClanGame

log = logging.getLogger(__name__)


def member_hash(member):
    return f"{member.membership_type}-{member.membership_id}"


def member_hash_db(member_db, platform_id):
    membership_id, _ = parse_platform(member_db, platform_id)
    return f"{platform_id}-{membership_id}"


def parse_platform(member_db, platform_id):
    if platform_id == constants.PLATFORM_BUNGIE:
        member_id = member_db.bungie_id
        member_username = member_db.bungie_username
    elif platform_id == constants.PLATFORM_PSN:
        member_id = member_db.psn_id
        member_username = member_db.psn_username
    elif platform_id == constants.PLATFORM_XBOX:
        member_id = member_db.xbox_id
        member_username = member_db.xbox_username
    elif platform_id == constants.PLATFORM_BLIZZARD:
        member_id = member_db.blizzard_id
        member_username = member_db.blizzard_username
    elif platform_id == constants.PLATFORM_STEAM:
        member_id = member_db.steam_id
        member_username = member_db.steam_username
    elif platform_id == constants.PLATFORM_STADIA:
        member_id = member_db.stadia_id
        member_username = member_db.stadia_username
    return member_id, member_username


def backoff_handler(details):
    if details['wait'] > 30 or details['tries'] > 10:
        log.info(
            f"Backing off {details['wait']:0.1f} seconds after {details['tries']} tries "
            f"for {details['target']} args {details['args'][1:]} kwargs {details['kwargs'][1:]}"
        )


@backoff.on_exception(
    backoff.expo,
    (PydestPrivateHistoryException, PydestMaintenanceException),
    max_tries=1, logger=None)
@backoff.on_exception(backoff.expo, PydestException, logger=None, on_backoff=backoff_handler)
@backoff.on_exception(backoff.expo, asyncio.TimeoutError, max_tries=1, logger=None)
async def execute_pydest(function, *args, **kwargs):
    retval = None
    try:
        data = await function(*args, **kwargs)
    except PydestMaintenanceException:
        raise MaintenanceError
    except PydestPrivateHistoryException:
        return retval
    else:
        if 'Response' in data:
            retval = data['Response']
    return retval


async def get_activity_history(destiny, platform_id, member_id, char_id, count=250, full_sync=False):
    page = 0
    activities = []

    data = await execute_pydest(
        destiny.api.get_activity_history, platform_id, member_id, char_id, count=count, page=page, mode=0)
    if data:
        if full_sync:
            while 'activities' in data:
                page += 1
                if activities:
                    activities.extend(data['activities'])
                else:
                    activities = data['activities']
                data = await execute_pydest(
                    destiny.api.get_activity_history, platform_id, member_id, char_id, count=count, page=page, mode=0)
        else:
            activities = data['activities']
    return activities


async def get_pgcr(destiny, activity_id):
    return await execute_pydest(destiny.api.get_post_game_carnage_report, activity_id)


async def get_characters(destiny, member_id, platform_id):
    retval = None
    data = await execute_pydest(
        destiny.api.get_profile, platform_id, member_id, [constants.COMPONENT_CHARACTERS])
    if data:
        retval = data['characters']['data']
    return retval


async def decode_activity(destiny, reference_id):
    await execute_pydest(destiny.update_manifest)
    return await execute_pydest(destiny.decode_hash, reference_id)


async def get_activity_list(destiny, platform_id, member_id, characters, count, full_sync=False):
    tasks = [
        get_activity_history(destiny, platform_id, member_id, character, count, full_sync)
        for character in list(characters.keys())
    ]
    activities = await asyncio.gather(*tasks)
    all_activities = list(itertools.chain.from_iterable(activities))
    return all_activities


async def get_last_active(destiny, member_db):
    platform_id = member_db.clanmember.platform_id
    member_id, _ = parse_platform(member_db, platform_id)

    acct_last_active = None
    try:
        characters = await get_characters(destiny, member_id, platform_id)
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


async def store_last_active(bot, member_db):
    last_active = await get_last_active(bot.destiny, bot.member_db)
    member_db.clanmember.last_active = last_active
    await bot.database.update(member_db.clanmember)


async def get_game_counts(database, game_mode, member_db=None):
    counts = {}
    base_query = Game.select()
    for mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode):
        if member_db:
            query = base_query.join(GameMember).join(Member).join(ClanMember).where(
                (Member.id == member_db.id) &
                (ClanMember.clan_id == member_db.clanmember.clan_id) &
                (Game.mode_id << [mode_id])
            )
        else:
            query = base_query.where(Game.mode_id << [mode_id])
        try:
            count = await database.count(query.distinct())
        except DoesNotExist:
            continue
        else:
            game_title = constants.MODE_MAP[mode_id]['title']
            if game_title in counts:
                counts[game_title] += count
            else:
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


async def store_game_member(database, player, game_db, clan_id, player_db=None):
    if not player_db:
        player_db = await database.get_clan_member_by_platform(
            player.membership_id, player.membership_type, clan_id)

    try:
        # Create the game member
        await database.create(
            GameMember, member=player_db.id, game=game_db.id,
            completed=player.completed, time_played=player.time_played)
    except IntegrityError:
        # If one already exists, we can assume this is due to a drop/re-join event so
        # increment the time played and set the completion flag
        game_member_db = await database.get(GameMember, game=game_db.id, member=player_db.id)
        game_member_db.time_played += player.time_played

        if not game_member_db.completed or game_member_db.completed != player.completed:
            game_member_db.completed = player.completed
        await database.update(game_member_db)

    log.info(f"Player {player.membership_id} created in game id {game_db.instance_id}")


async def create_game(database, game):
    try:
        return await database.create(Game, **vars(game))
    except IntegrityError:
        # Mitigate possible race condition when multiple parallel jobs try to
        # do the same thing. Likely when there are multiple people in the same
        # game instance.
        # TODO: Figure out a better way to 'lock' things
        return


async def create_clan_game(database, game_db, game, clan_id):
    try:
        await database.get(ClanGameDb, clan=clan_id, game=game_db.id)
    except DoesNotExist:
        await database.create(ClanGameDb, clan=clan_id, game=game_db.id)
        tasks = [
            store_game_member(database, player, game_db, clan_id)
            for player in game.clan_players
        ]
        await asyncio.gather(*tasks)


async def store_member_history(bot, member_db, member_dbs, count):
    platform_id = member_db.clanmember.platform_id
    member_id, member_username = parse_platform(member_db, platform_id)

    try:
        characters = await get_characters(bot.destiny, member_id, platform_id)
    except (KeyError, TypeError):
        log.error(f"Could not get character data for {platform_id}-{member_id}")
        return

    all_activities = await get_activity_list(bot.destiny, platform_id, member_id, characters, count)

    mode_count = 0
    for activity in all_activities:
        game = GameApi(activity)

        try:
            await bot.database.get(Game, instance_id=game.instance_id)
        except DoesNotExist:
            pass
        else:
            log.debug(f"Continuing because game {game.instance_id} exists")
            continue

        # Check if the game occurred before the member joined the clan
        # before the game time, or if the game is not a supported one.
        # If either of those apply, the game is not eligible.
        supported_modes = set(sum(constants.SUPPORTED_GAME_MODES.values(), []))
        if (game.date < bot.config.activity_cutoff or
                game.date < member_db.clanmember.join_date or
                game.mode_id not in supported_modes):
            log.debug(f"Continuing because game {game.instance_id} isn't eligible")
            continue

        pgcr = await get_pgcr(bot.destiny, game.instance_id)
        if not pgcr:
            log.error(f"Continuing because error with pgcr for game {game.instance_id}")
            log.debug(f"{member_username}: {pgcr}")
            continue

        # Create a clan game object from the pgcr, this stores clan members that were members
        # before the game time.
        clan_game = ClanGame(pgcr, member_dbs)

        # Check if player count is below the threshold
        game_mode_details = constants.MODE_MAP[game.mode_id]
        if len(clan_game.clan_players) < game_mode_details['threshold']:
            log.debug(f"Continuing because not enough clan players in game {game.instance_id}")
            continue

        game_db = await create_game(bot.database, clan_game)
        if not game_db:
            continue

        game_title = game_mode_details['title'].title()
        log.info(f"{game_title} game id {game.instance_id} created")
        mode_count += 1

        await create_clan_game(bot.database, game_db, clan_game, member_db.clanmember.clan_id)

    if mode_count:
        log.debug(f"Found {mode_count} games for {member_username}")
        return mode_count


async def store_all_games(bot, guild_id, count=30):
    discord_guild = await bot.fetch_guild(guild_id)
    guild_db = await bot.database.get(Guild, guild_id=guild_id)

    try:
        clan_dbs = await bot.database.get_clans_by_guild(guild_id)
    except DoesNotExist:
        log.info(f"No clans found for {str(discord_guild)} ({guild_id})")
        return

    log.info(f"Finding all games for members of {str(discord_guild)} ({guild_id}) active in the last hour")

    tasks = []
    active_member_dbs = []
    all_member_dbs = []
    for clan_db in clan_dbs:
        if not clan_db.activity_tracking:
            log.info(f"Clan activity tracking disabled for Clan {clan_db.name}, skipping")
            continue

        active_members = await bot.database.get_clan_members_active(clan_db.id, hours=1)
        all_members = await bot.database.get_clan_members(clan_db.id)
        if guild_db.aggregate_clans:
            active_member_dbs.extend(active_members)
            all_member_dbs.extend(all_members)
        else:
            active_member_dbs = active_members
            all_member_dbs = all_members

        tasks.extend([
            store_member_history(bot, member_db, all_member_dbs, count)
            for member_db in active_member_dbs
        ])

    results = await asyncio.gather(*tasks)

    log.info(
        f"Found {sum(filter(None, results))} games for members "
        f"of {str(discord_guild)} ({guild_id}) active in the last hour"
    )
