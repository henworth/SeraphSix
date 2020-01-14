import asyncio
import backoff
import logging
import pydest

from peewee import DoesNotExist, fn, IntegrityError
from seraphsix import constants
from seraphsix.cogs.utils.helpers import bungie_date_as_utc
from seraphsix.database import ClanGame as ClanGameDb, ClanMember, Game, GameMember, Guild, Member
from seraphsix.errors import MaintenanceError
from seraphsix.models.destiny import Game as GameApi, ClanGame
from ratelimit import limits, RateLimitException

log = logging.getLogger(__name__)


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


def backoff_hdlr(details):
    if details["wait"] > 30 or details["tries"] > 10:
        log.info(
            f"Backing off {details['wait']:0.1f} seconds after {details['tries']} tries "
            f"for {details['args'][3]}-{details['args'][2]}"
        )


@backoff.on_exception(
    backoff.expo,
    (pydest.pydest.PydestPrivateHistoryException, pydest.pydest.PydestMaintenanceException),
    max_tries=1, logger=None)
@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_tries=100, logger=None)
@backoff.on_exception(backoff.expo, asyncio.TimeoutError, max_tries=1)
@backoff.on_exception(backoff.expo, RateLimitException, max_tries=100, logger=None, on_backoff=backoff_hdlr)
@limits(calls=25, period=1)
async def execute_pydest(function, redis, member_id=None, caller=None):
    is_maintenance = await redis.get('global-bungie-maintenance')
    if is_maintenance and eval(is_maintenance):
        await function()
        raise MaintenanceError
    try:
        return await asyncio.create_task(function)
    except pydest.pydest.PydestMaintenanceException as e:
        await redis.set('global-bungie-maintenance', str(True), expire=constants.TIME_MIN_SECONDS)
        log.error(e)
        raise MaintenanceError
    except RuntimeError as e:
        log.error(f"{member_id} {caller} {e}")
        return None


async def get_activity_history(destiny, redis, platform_id, member_id, char_id, count):
    function = destiny.api.get_activity_history(platform_id, member_id, char_id, count=count)
    data = await execute_pydest(function, redis, member_id, "get_activity_history")
    try:
        activities = data['Response']['activities']
    except (KeyError, TypeError):
        return None
    return activities


async def get_pgcr(destiny, redis, activity_id):
    function = destiny.api.get_post_game_carnage_report(activity_id)
    data = await execute_pydest(function, redis, activity_id, "get_pgcr")
    pgcr = data['Response']
    return pgcr


async def get_characters(destiny, redis, member_id, platform_id, caller=None):
    function = destiny.api.get_profile(platform_id, member_id, [constants.COMPONENT_CHARACTERS])
    data = await execute_pydest(function, redis, member_id, caller)
    characters = data['Response']['characters']['data']
    return characters


async def decode_activity(destiny, redis, reference_id):
    await execute_pydest(destiny.update_manifest(), reference_id, "decode_activity")
    function = destiny.decode_hash(reference_id, 'DestinyActivityDefinition')
    return await execute_pydest(function, redis, reference_id, "decode_activity")


async def get_activity_list(destiny, redis, platform_id, member_id, char_ids, count):
    all_activity_ids = []
    for char_id in char_ids:
        activities = await get_activity_history(
            destiny, redis, platform_id, member_id, char_id, count=count)
        if not activities:
            continue
        all_activity_ids.extend([activity for activity in activities])
    return all_activity_ids


async def get_last_active(destiny, redis, member_db):
    platform_id = member_db.clanmember.platform_id
    member_id, _ = parse_platform(member_db, platform_id)

    acct_last_active = None
    try:
        characters = await get_characters(destiny, redis, member_id, platform_id, "get_last_active")
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
    last_active = await get_last_active(bot.destiny, bot.redis, member_db)
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
            counts[constants.MODE_MAP[mode_id]['title']] = count
    return counts


async def get_sherpa_time_played(database, member_db):
    clan_sherpas = Member.select(Member.id).join(ClanMember).where((ClanMember.is_sherpa) & (Member.id != member_db.id))

    full_list = list(constants.SUPPORTED_GAME_MODES.values())
    mode_list = list(set([mode for sublist in full_list for mode in sublist]))

    games = Game.select().join(GameMember).where(
        (GameMember.member_id == member_db.id) & (Game.mode_id << mode_list)
    )

    game_sherpas = Game.select(Game.id.distinct()).join(GameMember).join(Member).join(ClanMember).where(
        (Game.id << games) & (Member.id << clan_sherpas)
    )

    game_members = Member.select(Member.id.distinct()).join(GameMember).join(Game).where(
        (Game.id << games) & (Member.id << clan_sherpas)
    )

    try:
        await database.execute(game_sherpas)
    except DoesNotExist:
        return None

    query = GameMember.select(fn.SUM(GameMember.time_played).alias('sum')).where(
        (GameMember.member_id == member_db.id) & (GameMember.game_id << game_sherpas)
    )
    time_played = await database.execute(query)

    game_members_db = await database.execute(game_members)
    sherpa_members_db = await database.execute(clan_sherpas)

    game_member_set = set([member.id for member in game_members_db])
    clan_sherpa_set = set([sherpa.id for sherpa in sherpa_members_db])

    game_sherpas_unique = list(game_member_set.intersection(clan_sherpa_set))

    return (time_played[0].sum, game_sherpas_unique)


async def store_game_member(bot, player, game_db, member_db):
    player_db = await bot.database.get_clan_member_by_platform(
        player.membership_id, player.membership_type, member_db.clanmember.clan_id)

    try:
        # Create the game member
        await bot.database.create(
            GameMember, member=player_db.id, game=game_db.id,
            completed=player.completed, time_played=player.time_played)
    except IntegrityError:
        # If one already exists, we can assume this is due to a drop/re-join event so
        # increment the time played and set the completion flag
        game_member_db = await bot.database.get(GameMember, game=game_db.id, member=player_db.id)
        game_member_db.time_played += player.time_played

        if not game_member_db.completed or game_member_db.completed != player.completed:
            game_member_db.completed = player.completed
        await bot.database.update(game_member_db)

    log.debug(f"Player {player.membership_id} created in game id {game_db.instance_id}")


async def store_member_history(member_dbs, bot, member_db, count):
    platform_id = member_db.clanmember.platform_id

    member_id, member_username = parse_platform(member_db, platform_id)

    try:
        characters = await get_characters(
            bot.destiny, bot.redis, member_id, platform_id, "store_member_history")
        char_ids = characters.keys()
    except (KeyError, TypeError):
        log.error(f"Could not get character data for {member_db.clanmember.platform_id}-{member_id}")
        return

    all_activities = await get_activity_list(
        bot.destiny, bot.redis, platform_id, member_id, char_ids, count
    )

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

        # Check if the game occurred before Forsaken released (ie. Season 4), or
        # if the game occurred before a configured cutoff date, or if the member
        # joined before game time, or if the game is not a supported one.
        # If any of those apply, the game is not eligible.
        supported_modes = set(sum(constants.SUPPORTED_GAME_MODES.values(), []))
        if (game.date < constants.FORSAKEN_RELEASE or
                game.date < bot.config.activity_cutoff or
                game.date < member_db.clanmember.join_date or
                game.mode_id not in supported_modes):
            log.debug(f"Continuing because game {game.instance_id} isn't eligible")
            continue

        pgcr = await get_pgcr(bot.destiny, bot.redis, game.instance_id)
        if not pgcr:
            log.error(f"{member_username}: {pgcr}")
            log.debug(f"Continuing because error with game {game.instance_id}")
            continue

        clan_game = ClanGame(pgcr, member_dbs)

        # Check if player count is below the threshold
        game_mode_details = constants.MODE_MAP[game.mode_id]
        if len(clan_game.clan_players) < game_mode_details['threshold']:
            log.debug(f"Continuing because not enough clan players in game {game.instance_id}")
            continue

        try:
            game_db = await bot.database.create(Game, **vars(clan_game))
        except IntegrityError:
            # Mitigate possible race condition when multiple parallel jobs try to
            # do the same thing. Likely when there are multiple people in the same
            # game instance.
            # TODO: Figure out a better way to "lock" things
            continue

        game_title = game_mode_details['title'].title()
        log.info(f"{game_title} game id {game.instance_id} created")
        mode_count += 1

        try:
            await bot.database.get(ClanGameDb, clan=member_db.clanmember.clan_id, game=game_db.id)
        except DoesNotExist:
            await bot.database.create(ClanGameDb, clan=member_db.clanmember.clan_id, game=game_db.id)
            tasks = [
                store_game_member(bot, player, game_db, member_db)
                for player in clan_game.clan_players
            ]
            await asyncio.gather(*tasks)

    if mode_count:
        log.debug(f"Found {mode_count} games for {member_username}")
        return mode_count


async def store_all_games(bot, guild_id, count=30):
    guild_db = await bot.database.get(Guild, guild_id=guild_id)

    try:
        clan_dbs = await bot.database.get_clans_by_guild(guild_id)
    except DoesNotExist:
        return

    log.info(f"Finding all games for members of server {guild_id} active in the last hour")

    tasks = []
    member_dbs = []
    for clan_db in clan_dbs:
        if not clan_db.activity_tracking:
            log.info(f"Clan activity tracking disabled for Clan {clan_db.name}, skipping")
            continue

        active_members = await bot.database.get_clan_members_active(clan_db.id, days=7)
        if guild_db.aggregate_clans:
            member_dbs.extend(active_members)
        else:
            member_dbs = active_members

        tasks.extend([
            store_member_history(member_dbs, bot, member_db, count)
            for member_db in member_dbs
        ])

    results = await asyncio.gather(*tasks)

    log.info(
        f"Found {sum(filter(None, results))} games for members "
        f"of server {guild_id} active in the last hour"
    )
