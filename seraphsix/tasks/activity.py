import asyncio
import backoff
import logging
import pydest

from datetime import datetime
from peewee import DoesNotExist
from seraphsix import constants
from seraphsix.database import ClanGame as ClanGameDb, ClanMember, Game, GameMember, Guild, Member
from seraphsix.models.destiny import ClanGame

logging.getLogger(__name__)


def parse_platform(member_db, platform_id):
    if platform_id == constants.PLATFORM_BLIZ:
        member_id = member_db.blizzard_id
        member_username = member_db.blizzard_username
    elif platform_id == constants.PLATFORM_BNG:
        member_id = member_db.bungie_id
        member_username = member_db.bungie_username
    elif platform_id == constants.PLATFORM_PSN:
        member_id = member_db.psn_id
        member_username = member_db.psn_username
    elif platform_id == constants.PLATFORM_XBOX:
        member_id = member_db.xbox_id
        member_username = member_db.xbox_username
    return member_id, member_username


@backoff.on_exception(backoff.expo, pydest.pydest.PydestPrivateHistoryException, max_tries=1, logger=None)
@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
@backoff.on_exception(backoff.expo, asyncio.TimeoutError, max_time=60)
async def get_activity_history(destiny, platform_id, member_id, char_id, mode_id, count):
    return await destiny.api.get_activity_history(
        platform_id, member_id, char_id, mode=mode_id, count=count
    )


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
@backoff.on_exception(backoff.expo, asyncio.TimeoutError, max_time=60)
async def get_activity(destiny, activity_id):
    return await destiny.api.get_post_game_carnage_report(activity_id)


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def decode_activity(destiny, reference_id):
    await destiny.update_manifest()
    return await destiny.decode_hash(reference_id, 'DestinyActivityDefinition')


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def get_profile(destiny, member_id, platform_id):
    return await destiny.api.get_profile(platform_id, member_id, [constants.COMPONENT_CHARACTERS])


async def get_activity_list(destiny, platform_id, member_id, char_ids, mode_id, count=30):
    all_activity_ids = []
    for char_id in char_ids:
        try:
            res = await get_activity_history(destiny, platform_id, member_id, char_id, mode_id, count)
        except Exception:
            continue

        try:
            activities = res['Response']['activities']
        except KeyError:
            continue

        all_activity_ids.extend([
            activity['activityDetails']['instanceId']
            for activity in activities
        ])
    return all_activity_ids


async def get_last_active(destiny, member_db):
    platform_id = member_db.clanmember.platform_id
    member_id, _ = parse_platform(member_db, platform_id)
    profile = await get_profile(
        destiny, member_id, member_db.clanmember.platform_id)
    acct_last_active = None
    try:
        profile_data = profile['Response']['characters']['data'].items()
    except KeyError:
        logging.error(f"Could not get profile data for {member_db.clanmember.platform_id}-{member_id}")
        return
    for _, data in profile_data:
        char_last_active = datetime.strptime(
            data['dateLastPlayed'], '%Y-%m-%dT%H:%M:%S%z')
        if not acct_last_active or char_last_active > acct_last_active:
            acct_last_active = char_last_active
    return acct_last_active


async def store_last_active(database, destiny, member_db):
    last_active = await get_last_active(destiny, member_db)
    member_db.clanmember.last_active = last_active
    await database.update(member_db.clanmember)


async def get_game_counts(database, destiny, game_mode, member_db=None):
    counts = {}
    query = Game.select()
    for mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode):
        if member_db:
            query = query.join(GameMember).join_from(GameMember, Member).join_from(Member, ClanMember).where(
                (Member.id == member_db.id) &
                (ClanMember.clan_id == member_db.clanmember.clan_id) &
                (Game.mode_id << [mode_id])
            ).distinct()
        else:
            query = query.where(Game.mode_id << [mode_id]).distinct()
        try:
            count = await database.count(query)
        except DoesNotExist:
            continue
        else:
            counts[constants.MODE_MAP[mode_id]['title']] = count
    return counts


async def store_member_history(member_dbs, database, destiny, member_db, game_mode):  #noqa TODO
    platform_id = member_db.clanmember.platform_id

    member_id, member_username = parse_platform(member_db, platform_id)

    profile = await get_profile(destiny, member_id, platform_id)
    try:
        char_ids = profile['Response']['characters']['data'].keys()
    except KeyError:
        logging.error(f"{member_username}: {profile}")
        return

    all_activity_ids = []
    for game_mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode):
        activity_ids = await get_activity_list(
            destiny, platform_id, member_id, char_ids, game_mode_id
        )
        if activity_ids:
            all_activity_ids.extend(activity_ids)

    mode_count = 0
    for activity_id in all_activity_ids:
        try:
            pgcr = await get_activity(destiny, activity_id)
        except Exception:
            continue

        if not pgcr.get('Response'):
            logging.error(f"{member_username}: {pgcr}")
            continue

        game = ClanGame(pgcr['Response'], member_dbs)

        game_mode_details = constants.MODE_MAP[game.mode_id]

        # Check if player count is below the threshold, or if the game
        # occurred after Forsaken released (ie. Season 4) or if the
        # member joined before game time. If any of those apply, the
        # game is not eligible.
        if (len(game.clan_players) < game_mode_details['threshold'] or
                game.date < constants.FORSAKEN_RELEASE or
                game.date < member_db.clanmember.join_date):
            continue

        game_title = game_mode_details['title'].title()

        try:
            game_db = await database.get(Game, instance_id=game.instance_id)
        except DoesNotExist:
            game_db = await database.create(Game, **vars(game))
            logging.info(f"{game_title} game id {activity_id} created")
            mode_count += 1

        try:
            await database.get(ClanGameDb, clan=member_db.clanmember.clan_id, game=game_db.id)
        except DoesNotExist:
            await database.create(ClanGameDb, clan=member_db.clanmember.clan_id, game=game_db.id)
            await database.create_clan_game_members(
                member_db.clanmember.clan_id, game_db.id, game.clan_players)

    if mode_count:
        logging.debug(
            f"Found {mode_count} {game_mode} games for {member_username}")
        return mode_count


async def store_all_games(database, destiny, game_mode, guild_id):
    guild_db = await database.get(Guild, guild_id=guild_id)

    try:
        clan_dbs = await database.get_clans_by_guild(guild_id)
    except DoesNotExist:
        return

    logging.info(
        f"Finding all {game_mode} games for members of server {guild_id} active in the last hour")

    tasks = []
    member_dbs = []
    for clan_db in clan_dbs:
        if not clan_db.activity_tracking:
            logging.info(f"Clan activity tracking disabled for Clan {clan_db.name}, skipping")
            continue

        active_members = await database.get_clan_members_active(clan_db.id, days=7)
        if guild_db.aggregate_clans:
            member_dbs.extend(active_members)
        else:
            member_dbs = active_members

        tasks.extend([
            store_member_history(
                member_dbs, database, destiny, member_db, game_mode)
            for member_db in member_dbs
        ])

    results = await asyncio.gather(*tasks)

    logging.info(
        f"Found {sum(filter(None, results))} {game_mode} games for members "
        f"of server {guild_id} active in the last hour"
    )
