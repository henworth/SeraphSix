#!/usr/bin/env python3.7
import json
import jsonpickle
import argparse
import asyncio
import backoff
import logging
import os
import pydest

from datetime import datetime, timezone, timedelta

from peewee import DoesNotExist, IntegrityError, InternalError
from seraphsix.database import Database, Game, Member, GameMember, ClanMember
# from seraphsix.models.destiny import Game, User, Member, GameMember, ClanMember
from seraphsix import constants

# DATABASE_URL = os.environ.get('DATABASE_URL')
BUNGIE_API_KEY = os.environ.get('BUNGIE_API_KEY')
DISCORD_API_KEY = os.environ.get('DISCORD_API_KEY')
GROUP_ID = os.environ.get('GROUP_ID')

logging.basicConfig(level=logging.INFO)
logging.getLogger(__name__)
logging.getLogger('aiohttp.client').setLevel(logging.ERROR)

loop = asyncio.get_event_loop()
database = Database('DATABASE_URL')
database.initialize()

destiny = pydest.Pydest(BUNGIE_API_KEY, client_id=os.environ.get(
    'BUNGIE_CLIENT_ID'), client_secret=os.environ.get('BUNGIE_CLIENT_SECRET'))


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


@backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
async def get_group_pending_members(destiny, group_id):
    return await destiny.api.get_group_pending_members(group_id)


async def store_member_history(members, database, destiny, member_db, game_mode):
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

    # mode_count = 0
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
                        # if game.date > member_dbs[player['name']].clanmember.join_date:
                        if game.date > member_db.clanmember.join_date:
                            players.append(player['name'])

                # Check if player count is below the threshold, or if the game
                # occurred after Forsaken released (ie. Season 4) or if the
                # member joined before game time. If any of those apply, the
                # game is not eligible.
                if (len(players) < player_threshold or
                        game.date < constants.FORSAKEN_RELEASE or
                        game.date < member_db.clanmember.join_date):
                    continue

                # game_details = {
                #     'date': game.date,
                #     'mode_id': game.mode_id,
                #     'instance_id': game.instance_id,
                #     'reference_id': game.reference_id
                # }

                logging.info(
                    f"{member_db.xbox_username} {game.date} {game.instance_id} {players}")

                # game_title = constants.MODE_MAP[game_mode_id]['title'].title()
                # try:
                #     await database.create_game(game_details, players)
                # except IntegrityError:
                #     game_db = await database.get_game(game.instance_id)
                #     game_db.reference_id = game.reference_id
                #     await database.update(game_db)
                #     logging.debug(
                #         f"{game_title} game id {activity_id} exists for {member_db.xbox_username}, skipping")
                #     continue
                # else:
                #     mode_count += 1
                #     logging.info(
                #         f"{game_title} game id {activity_id} created for {member_db.xbox_username}")

    # return mode_count


async def main():
    # parser = argparse.ArgumentParser(description='Find clan member activity')
    # parser.add_argument('--game-mode', dest='game_mode', help='Game mode to filter on')
    # parser.add_argument('--member-name', dest='member_name', help='Game mode to filter on')
    # args = parser.parse_args()

    # members = [
    #     jsonpickle.encode(member)
    #     for member in await database.get_clan_members_by_guild_id(468491715230302208)
    # ]

    # for member in members:
    #     member_db = jsonpickle.decode(member)
    #     await store_member_history(members, database, destiny, member_db, 'pvp')

    # count = await get_member_history(database, destiny, args.member_name, [10, 12, 25, 31, 50, 43, 44, 37, 38, 65, 63, 4], check_date=True)
    # count = await get_member_history(database, destiny, args.member_name, [46, 47], check_date=False)
    # count = 0
    # for mode_id in MODES_PVP_COMP:
    #     print(await database.get_game_count(args.member_name, mode_id))
    # count = await database.get_game_count(args.member_name, MODES_PVP_COMP)
    # await store_member_history(database, destiny, args.member_name, MODE_RAID)

    # get_membership_data_by_id(4611686018460231113)
    # profile = await destiny.api.search_destiny_player(1, 'TR8R SPIN CYCLE')
    # members = await destiny.api.get_group_members(GROUP_ID)

    # player = await destiny.api.get_content_by_id(4142223378)
    # profile = await destiny.api.get_membership_data_by_id(4611686018475974306)
    # print(profile)
    # mem_list = []
    # for member in members['Response']['results']:
    #     d = Member(member)
    #     mem_list.append(d)
    #     break
    # print(todict(mem_list[0]))
    # print(todict(mem_list[0].memberships))

    # members = await database.get_clan_members_by_guild_id(499982563016704001)
    # for member in members:
    #     pickle = jsonpickle.encode(member)
    #     print(pickle)
    # pending_members = await get_group_pending_members(destiny, GROUP_ID)
    # print(members)
    # for member in await database.get_members():
    #     count = await get_member_history(member.xbox_username, [10, 12, 25, 31, 50, 43, 44, 37, 38, 65], check_date=True)
    #     print(member.xbox_username, count)

    # user_data = {
    #     'bungie_id': 15971319,
    #     'bungie_username': 'lifeinchains',
    #     'xbox_id': 4611686018469069377,
    #     'xbox_username': 'lifeinchains',
    #     'psn_id': None,
    #     'psn_username': None,
    #     'blizzard_id': None,
    #     'blizzard_username': None,
    #     'bungie_access_token': 'CNasARKGAgAg969cDOwYXNYfGlW37ePjGMmMzX4srlt8E+W1LIRL6F3gAAAAuLmSvHE26kGl9a+gARSj+dl32rmszmnrylEMDLmWqBGHzQASYsEo/M/uHOME2+QxYsRSEkUx1scaRSjnvhhck8u65x5RCsgNgnE3HSS7SkUoJdvB4Upw/DTcewXWiVnrfE83qO7qovEZghPZUw8K3ADeS+1ic8lBVA1RFftMWQ1wH2VBaovIgYm3RKtOZacqCObutBCyB7FYNJa/e7bAAqjtPsxTgeA9fw4I+lP7sV1dp5ptijyMyloq62qeaNsQa5ScF9jor9XOJcw9+mdFgv4BigvV5TPZc7ZgUpMKPnU=',
    #     'bungie_refresh_token': 'CNasARKGAgAgC6VDk/eYOKnS88yjHCd7tg262HjbYGgRcdBlKog3qIvgAAAA9buZgLl+54wIxNhAunKRbUWrKMm+ikK788mIIeL9EM0v0GdrakDqc6uEgtm14putI+KSgH+ClfVvYxc42Q7Kk+3qxrDVSBZTFZIwzqBJuUxyKpK5K/ZRW3z9sZ3iW+ShNg5FEfdlAoAG6ojL4KTn2pPWTrf4FKfDXRXTGC94ANzgmqxcmo7T58oycEnrxQ8DB3CIKgVE+487c26+qA+voutc9Zvu8Qgprxjo+Y/97zaIlqNyymLL65ZQ6dsB1QA94Z+4wTgcD08w9KnaKwSlBOyq06wBs9aFA9N/bvMHWQ0='
    # }

    # member_db = await database.get_member_by_platform(15971319, constants.PLATFORM_BNG)

    # for key, value in user_data.items():
    #     setattr(member_db, key, value)

    # print(vars(member_db))
    # await database.update(member_db)

    # thing = await get_activity(destiny, 3965706789)
    # print(json.dumps(thing))

    # access_token = "COysARKGAgAg3QuvyNPPUdozBF2Vqy6oYiaq9iGaqtMjjZ3+ajheXtLgAAAA4fgmJxgdhLgJJtOS+mSrW1HpyNtH59P0I3Ft+nv5yhuk+pBTk6cLTs70css9rhNpHr+YX4DlWC3iaxhHBQ6yycZsYNCp3csk5hMgPq6S0mLh9TqdAss1dcqCZt+1y4VZMDmyC3RgSGSrhvIXKPCtcrOzvQCzFSbPR0jsB1qhJjeUv0p/NVCQy/7jn/dSsxnp2/3V/wpUNsNumK12F4Q4Xtnrm80e1wXt1awbd5K/qNO4A8c7LTFk1M3vAaHqwC5EWVAo029H3g3VKF4Sgtjx0944In0pES6JbS5Qz3bOVq0=",
    # refresh_token = "COysARKGAgAgdGrQz7fI84S024egqaWaHTgTFIar5sfBpHw3B9meuL/gAAAA5w/33xYXojDljOWegcEcwRxgDolocRdjUYD8G/RdttE3HbOtGHyBuLLukAzzn6usuNGZizNlBWMw+PMR5mZZDWwSqMb3ivsw0y8tCUW614b1OuvcaxXBay1e1kLMBF5uVK/quUk+H0GaHVrHG/SeMzRaGLeB2jodvANv3Ksc11W0mRUY7R7m7aSxJvyAT2SQsJCRODYD26e3FJPz53D0Jz+E/+SUPmtFDQOulPETTOLgfurxKT7Uvaz5rlG50gTRrv/XZaQh6YEvUncDNsth4StRPDzODXLGvlDB1Hbyn7A=",

    # tokens = await destiny.api.refresh_oauth_token(refresh_token)
    # # print(tokens)
    # thing = await destiny.api.get_membership_current_user(tokens['access_token'])
    # print(json.dumps(thing))
    # member_db = await database.execute(
    #     Member.select(Member, ClanMember).join(ClanMember).where(
    #         Member.xbox_username == 'lifeinchains'
    #     ).get()
    # )
    # print(vars(member_db))
    # game_counts = {}
    # base_query = Game.select()
    # for mode_id in constants.SUPPORTED_GAME_MODES.get('raid'):
    #     query = base_query.join(GameMember).join(Member).join(ClanMember).where(
    #         (Member.id == member_db.id) &
    #         (ClanMember.clan_id == member_db.clanmember.clan_id) &
    #         (Game.mode_id << [mode_id])
    #     ).distinct()
    #     count = await database.count(query)
    #     try:
    #         count = await database.count(query.distinct())
    #     except DoesNotExist:
    #         continue
    #     else:
    #         game_counts[constants.MODE_MAP[mode_id]['title']] = count

    # total_count = 0
    # if len(game_counts) == 1:
    #     print('thing')
    #     total_count, = game_counts.values()
    # else:
    #     for game, count in game_counts.items():
    #         # embed.add_field(name=game.title(), value=str(count))
    #         total_count += count
    # print(total_count)
    # platform_id = constants.PLATFORM_XBOX
    # gamertag = "VKL LORD TALOS"
    # player = await destiny.api.search_destiny_player(
    #     platform_id, gamertag
    # )
    # membership_id = None
    # for membership in player['Response']:
    #     print(membership)
    #     if membership['membershipType'] == platform_id and \
    #             membership['displayName'].lower() == gamertag.lower():
    #         membership_id = membership['membershipId']
    #         break
    # print(membership_id)
    things = await database.get_clans_by_guild(577158002000527390)
    if things:
        print(vars(things))

    # async def bulk_update(self, model_list, fields, batch_size):
    #     query = model.bulk_update(
    #         game_list, fields=fields, batch_size=batch_size)
    #     try:
    #         return await self.execute(query)
    #     except AttributeError:
    #         return True
    things[0].platform = constants.PLATFORM_XBOX
    await database.bulk_update(things, ['platform'])

    things = await database.get_clans_by_guild(577158002000527390)
    if things:
        print(vars(things))

    await destiny.close()
    await database.close()


try:
    loop.run_until_complete(main())
except KeyboardInterrupt:
    pass
# finally:
#     loop = asyncio.get_event_loop()
#     asyncio.ensure_future(destiny.close())
#     asyncio.create_task(database.close())
loop.close()
