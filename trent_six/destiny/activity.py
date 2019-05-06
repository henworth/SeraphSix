import ast
import backoff
import logging
import pydest

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
async def get_profile(destiny, member_id):
    return await destiny.api.get_profile(constants.PLATFORM_XBOX, member_id, [constants.COMPONENT_CHARACTERS])


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


async def store_member_history(cache, database, destiny, member_name, game_mode):
    members = ast.literal_eval(cache.get('members').value)

    member_db = await database.get_member_by_xbox_username(member_name)
    member_id = member_db.xbox_id
    member_join_date = member_db.join_date

    profile = await get_profile(destiny, member_id)
    try:
        char_ids = profile['Response']['characters']['data'].keys()
    except KeyError:
        logging.error(f"{member_name}: {profile}")
        return

    mode_count = 0
    for game_mode_id in constants.SUPPORTED_GAME_MODES.get(game_mode):
        player_threshold = int(
            constants.MODE_MAP[game_mode_id]['player_count'] / 2)
        if player_threshold < 2:
            player_threshold = 2

        for char_id in char_ids:
            activity = await get_activity_list(
                destiny, member_id, char_id, game_mode_id
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
                game = Game(pgcr['Response'])

                # Loop through all players to find any members that completed
                # the game session. Also check if the member joined before
                # the game time.
                players = []
                for player in game.players:
                    if player['completed'] and player['name'] in members:
                        member_db = await database.get_member_by_xbox_username(player['name'])
                        if game.date > member_db.join_date:
                            players.append(player['name'])

                # Check if player count is below the threshold, or if the game
                # occurred after Forsaken released (ie. Season 4) or if the
                # member joined before game time. If any of those apply, the
                # game is not eligible.
                if (len(players) < player_threshold or
                        game.date < constants.FORSAKEN_RELEASE or
                        game.date < member_join_date):
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
                    logging.info(
                        f"{game_title} game id {activity_id} exists for {member_name}, skipping")
                    continue
                else:
                    mode_count += 1
                    logging.info(
                        f"{game_title} game id {activity_id} created for {member_name}")

    return mode_count
