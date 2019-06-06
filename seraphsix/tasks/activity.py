import backoff
import logging
import pydest

from datetime import datetime
from peewee import DoesNotExist, IntegrityError
from seraphsix import constants
from seraphsix.models.destiny import ClanGame

logging.getLogger(__name__)


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def get_activity_list(destiny, member_id, char_ids, mode_id, count=10):
    all_activity_ids = []
    for char_id in char_ids:
        res = await destiny.api.get_activity_history(
            constants.PLATFORM_XBOX, member_id, char_id, mode=mode_id, count=count
        )

        try:
            activities = res['Response']['activities']
        except KeyError:
            return

        all_activity_ids.extend([
            activity['activityDetails']['instanceId']
            for activity in activities
        ])
    return all_activity_ids


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def get_activity(destiny, activity_id):
    return await destiny.api.get_post_game_carnage_report(activity_id)


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def decode_activity(destiny, reference_id):
    await destiny.update_manifest()
    return await destiny.decode_hash(reference_id, 'DestinyActivityDefinition')


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def get_profile(destiny, member_id, platform_id=constants.PLATFORM_XBOX):
    return await destiny.api.get_profile(
        platform_id, member_id, [constants.COMPONENT_CHARACTERS])


async def get_last_active(destiny, member_db):
    if member_db.clanmember.platform_id == constants.PLATFORM_XBOX:
        member_id = member_db.xbox_id
    elif member_db.clanmember.platform_id == constants.PLATFORM_PSN:
        member_id = member_db.psn_id
    else:
        member_id = member_db.blizzard_id

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


async def get_member_history(database, destiny, member_name, game_mode):
    game_counts = {}
    for mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode):
        try:
            count = await database.get_game_count(member_name, [mode_id])
        except DoesNotExist:
            continue
        else:
            game_counts[constants.MODE_MAP[mode_id]['title']] = count
    return game_counts


async def get_all_history(database, destiny, game_mode):
    game_counts = {}
    for mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode):
        try:
            count = await database.get_all_game_count([mode_id])
        except DoesNotExist:
            continue
        else:
            game_counts[constants.MODE_MAP[mode_id]['title']] = count
    return game_counts


async def store_member_history(member_dbs, database, destiny, member_db, game_mode):
    profile = await get_profile(destiny, member_db.xbox_id)
    try:
        char_ids = profile['Response']['characters']['data'].keys()
    except KeyError:
        logging.error(f"{member_db.xbox_username}: {profile}")
        return

    all_activity_ids = []
    for game_mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode):
        activity_ids = await get_activity_list(
            destiny, member_db.xbox_id, char_ids, game_mode_id
        )
        if activity_ids:
            all_activity_ids.extend(activity_ids)

    mode_count = 0
    for activity_id in all_activity_ids:
        pgcr = await get_activity(destiny, activity_id)

        if not pgcr.get('Response'):
            logging.error(f"{member_db.xbox_username}: {pgcr}")
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
            game_db = await database.create_game(vars(game))
        except IntegrityError:
            game_db = await database.get_game(game.instance_id)

        try:
            await database.create_clan_game(member_db.clanmember.clan_id, game_db.id)
            await database.create_clan_game_members(
                member_db.clanmember.clan_id, game_db.id, game.clan_players)
        except IntegrityError:
            continue

        logging.info(f"{game_title} game id {activity_id} created")
        mode_count += 1

    if mode_count:
        logging.debug(
            f"Found {mode_count} {game_mode} games for {member_db.xbox_username}")
