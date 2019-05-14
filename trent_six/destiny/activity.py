import ast
import backoff
import jsonpickle
import logging
import pydest
import pytz

from datetime import datetime, timedelta, timezone
from peewee import DoesNotExist, IntegrityError, InternalError
from trent_six.destiny import constants
from trent_six.destiny.models import Game

logging.getLogger(__name__)


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def get_activity_list(destiny, member_id, char_id, mode_id, count=10):
    return await destiny.api.get_activity_history(
        constants.PLATFORM_XBOX, member_id, char_id, mode=mode_id, count=count
    )


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def get_activity(destiny, activity_id):
    return await destiny.api.get_post_game_carnage_report(activity_id)


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def decode_activity(destiny, reference_id):
    await destiny.update_manifest()
    return await destiny.decode_hash(reference_id, 'DestinyActivityDefinition')


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def get_profile(destiny, member_id, platform_id=constants.PLATFORM_XBOX):
    return await destiny.api.get_profile(platform_id, member_id, [constants.COMPONENT_CHARACTERS])


async def get_last_active(destiny, member_db):
    if member_db.clanmember.platform_id == constants.PLATFORM_XBOX:
        member_id = member_db.xbox_id
    elif member_db.clanmember.platform_id == constants.PLATFORM_PSN:
        member_id = member_db.psn_id
    else:
        member_id = member_db.blizzard_id

    profile = await get_profile(destiny, member_id, member_db.clanmember.platform_id)
    acct_last_active = None
    for _, data in profile['Response']['characters']['data'].items():
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


async def store_member_history(members, database, destiny, member_db, game_mode):
    # Check if member hasn't been active within the past hour
    hour_ago = datetime.now(pytz.utc) - timedelta(hours=1)
    if not member_db.clanmember.last_active > hour_ago:
        return

    logging.debug(
        f"Member {member_db.id} was last active {member_db.clanmember.last_active}")

    # Create a dict holding model references for all members key by their username
    member_dbs = {}
    for member in members:
        temp = jsonpickle.decode(member)
        member_dbs.update({temp.xbox_username: temp})

    profile = await get_profile(destiny, member_db.xbox_id)
    try:
        char_ids = profile['Response']['characters']['data'].keys()
    except KeyError:
        logging.error(f"{member_db.xbox_username}: {profile}")
        return

    mode_count = 0
    for game_mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode):
        player_threshold = int(
            constants.MODE_MAP[game_mode_id]['player_count'] / 2)
        if player_threshold < 2:
            player_threshold = 2

        for char_id in char_ids:
            activity = await get_activity_list(
                destiny, member_db.xbox_id, char_id, game_mode_id
            )

            try:
                activities = activity['Response']['activities']
            except KeyError:
                continue

            activity_ids = [
                activity['activityDetails']['instanceId']
                for activity in activities
            ]

            for activity_id in activity_ids:
                pgcr = await get_activity(destiny, activity_id)
                try:
                    game = Game(pgcr['Response'])
                except KeyError:
                    logging.error(f"{member_db.xbox_username}: {pgcr}")
                    continue

                # Loop through all players to find any members that completed
                # the game session. Also check if the member joined before
                # the game time.
                players = []
                for player in game.players:
                    if player['completed'] and player['name'] in member_dbs.keys():
                        if game.date > member_dbs[player['name']].clanmember.join_date:
                            players.append(player['name'])

                # Check if player count is below the threshold, or if the game
                # occurred after Forsaken released (ie. Season 4) or if the
                # member joined before game time. If any of those apply, the
                # game is not eligible.
                if (len(players) < player_threshold or
                        game.date < constants.FORSAKEN_RELEASE or
                        game.date < member_db.clanmember.join_date):
                    continue

                game_details = {
                    'date': game.date,
                    'mode_id': game.mode_id,
                    'instance_id': game.instance_id,
                    'reference_id': game.reference_id
                }

                game_title = constants.MODE_MAP[game_mode_id]['title'].title()
                try:
                    await database.create_game(game_details, players)
                except IntegrityError:
                    game_db = await database.get_game(game.instance_id)
                    game_db.reference_id = game.reference_id
                    await database.update_game(game_db)
                    logging.debug(
                        f"{game_title} game id {activity_id} exists for {member_db.xbox_username}, skipping")
                    continue
                else:
                    mode_count += 1
                    logging.info(
                        f"{game_title} game id {activity_id} created for {member_db.xbox_username}")

    return mode_count
