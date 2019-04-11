import logging

import backoff
import pydest

from datetime import datetime, timedelta, timezone
from peewee import DoesNotExist, IntegrityError, InternalError

from members import Game

PLATFORM_XBOX = 1

COMPONENT_CHARACTERS = 200

MODE_STRIKE = 3
MODE_RAID = 4
MODE_NIGHTFALL = 46

MODE_PVP_MAYHEM = 25
MODE_PVP_SUPREMACY = 31
MODE_PVP_SURVIVAL = 37
MODE_PVP_COUNTDOWN = 38
MODE_PVP_IRONBANNER_CONTROL = 43
MODE_PVP_IRONBANNER_CLASH = 44
MODE_PVP_DOUBLES = 50
MODE_PVP_LOCKDOWN = 60
MODE_PVP_BREAKTHROUGH = 65
MODE_PVP_CLASH_QUICK = 71
MODE_PVP_CLASH_COMP = 72
MODE_PVP_CONTROL_QUICK = 73
MODE_PVP_CONTROL_COMP = 74

MODE_GAMBIT = 63
MODE_GAMBIT_PRIME = 75
MODE_GAMBIT_RECKONING = 76

MODES_PVP_QUICK = [
    MODE_PVP_MAYHEM, MODE_PVP_SUPREMACY, MODE_PVP_DOUBLES,
    MODE_PVP_LOCKDOWN, MODE_PVP_BREAKTHROUGH,
    MODE_PVP_IRONBANNER_CONTROL, MODE_PVP_IRONBANNER_CLASH,
    MODE_PVP_CLASH_QUICK, MODE_PVP_CONTROL_QUICK
]

MODES_PVP_COMP = [
    MODE_PVP_SURVIVAL, MODE_PVP_COUNTDOWN, 
    MODE_PVP_CLASH_COMP, MODE_PVP_CONTROL_COMP
]

MODES_GAMBIT = [
    MODE_GAMBIT, MODE_GAMBIT_PRIME, MODE_GAMBIT_RECKONING
]

MODES_STRIKE = [
    MODE_STRIKE, MODE_NIGHTFALL
]

MODE_MAP = {
    MODE_STRIKE: {'title': 'strike', 'player_count': 3},
    MODE_RAID: {'title': 'raid', 'player_count': 6},
    MODE_NIGHTFALL: {'title': 'nightfall', 'player_count': 3},
    MODE_PVP_MAYHEM: {'title': 'mayhem', 'player_count': 6},
    MODE_PVP_SUPREMACY: {'title': 'supremacy', 'player_count': 4},
    MODE_PVP_SURVIVAL: {'title': 'survival', 'player_count': 4},
    MODE_PVP_COUNTDOWN: {'title': 'countdown', 'player_count': 4},
    MODE_PVP_IRONBANNER_CONTROL: {'title': 'ironbanner control', 'player_count': 6},
    MODE_PVP_IRONBANNER_CLASH: {'title': 'ironbanner clash', 'player_count': 6},
    MODE_PVP_DOUBLES: {'title': 'doubles', 'player_count': 2},
    MODE_PVP_LOCKDOWN: {'title': 'lockdown', 'player_count': 4},
    MODE_PVP_BREAKTHROUGH: {'title': 'breakthrough', 'player_count': 4},
    MODE_PVP_CLASH_QUICK: {'title': 'clash (quickplay)', 'player_count': 6},
    MODE_PVP_CLASH_COMP: {'title': 'clash (competitive)', 'player_count': 4},
    MODE_PVP_CONTROL_QUICK: {'title': 'control (quickplay)', 'player_count': 6},
    MODE_PVP_CONTROL_COMP: {'title': 'control (competitive)', 'player_count': 4},
    MODE_GAMBIT: {'title': 'gambit', 'player_count': 4},
    MODE_GAMBIT_PRIME: {'title': 'gambit prime', 'player_count': 4},
    MODE_GAMBIT_RECKONING: {'title': 'reckoning', 'player_count': 4}
}


FORSAKEN_RELEASE = datetime.strptime('2018-09-04T18:00:00Z', '%Y-%m-%dT%H:%M:%S%z')

logging.getLogger(__name__)


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def get_activity_list(destiny, member_id, char_id, mode_id, count=10):
    return await destiny.api.get_activity_history(
        PLATFORM_XBOX, member_id, char_id, mode=mode_id, count=count
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
    return await destiny.api.get_profile(PLATFORM_XBOX, member_id, [COMPONENT_CHARACTERS])


async def get_member_history(database, destiny, member_name, game_mode):

    if game_mode == 'gambit':
        game_mode_list = MODES_GAMBIT
    elif game_mode == 'strike':
        game_mode_list = MODES_STRIKE
    elif game_mode == 'raid':
        game_mode_list = [MODE_RAID]
    elif game_mode == 'pvp':
        game_mode_list = MODES_PVP_COMP + MODES_PVP_QUICK
    elif game_mode == 'pvp-quick':
        game_mode_list = MODES_PVP_QUICK
    elif game_mode == 'pvp-comp':
        game_mode_list = MODES_PVP_COMP

    total_game_count = 0
    for mode_id in game_mode_list:
        try:
            count = await database.get_game_count(member_name, [mode_id])
        except DoesNotExist:
            continue
        else:
            total_game_count += count

    return total_game_count


async def store_member_history(database, destiny, member_name, game_mode):

    if game_mode == 'gambit':
        game_mode_list = MODES_GAMBIT
    elif game_mode == 'strike':
        game_mode_list = MODES_STRIKE
    elif game_mode == 'raid':
        game_mode_list = [MODE_RAID]
    elif game_mode == 'pvp':
        game_mode_list = MODES_PVP_COMP + MODES_PVP_QUICK

    members = [member.xbox_username for member in await database.get_members()]

    member_db = await database.get_member(member_name)
    member_id = member_db.bungie_id
    member_join_date = member_db.join_date

    profile = await get_profile(destiny, member_id)
    char_ids = list(profile['Response']['characters']['data'].keys())

    mode_count = 0
    for game_mode_id in game_mode_list:
        player_threshold = int(MODE_MAP[game_mode_id]['player_count'] / 2)
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
                        member_db = await database.get_member(player['name'])
                        if game.date > member_db.join_date:
                            players.append(player['name'])

                # Check if player count is below the threshold, or if the game
                # occurred after Forsaken released (ie. Season 4) or if the
                # member joined before game time. If any of those apply, the
                # game is not eligible.
                if (len(players) < player_threshold or
                        game.date < FORSAKEN_RELEASE or 
                        game.date < member_join_date):
                    continue

                game_details = {
                    'date': game.date,
                    'mode_id': game.mode_id,
                    'instance_id': activity_id,
                }

                try:
                    await database.create_game(game_details, players)
                except IntegrityError:
                    logging.info(f"{MODE_MAP[game_mode_id]['title'].title()} game id {activity_id} exists for {member_name}, skipping")
                    continue
                else:
                    mode_count += 1
                    logging.info(f"{MODE_MAP[game_mode_id]['title'].title()} game id {activity_id} created for {member_name}")

    return mode_count