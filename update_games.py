import asyncio
import backoff
import logging
import os
import pydest

from peewee import DoesNotExist, IntegrityError, InternalError, Tuple, Case
from playhouse.shortcuts import model_to_dict
from seraphsix.database import Database, Member, ClanMember
from seraphsix.tasks.clan import get_all_members, member_sync

DATABASE_URL = os.environ.get('DATABASE_URL')
BUNGIE_API_KEY = os.environ.get('BUNGIE_API_KEY')
GROUP_ID = os.environ.get('GROUP_ID')

logging.basicConfig(level=logging.INFO)
logging.getLogger(__name__)
logging.getLogger('aiohttp.client').setLevel(logging.ERROR)

loop = asyncio.new_event_loop()
database = Database(DATABASE_URL, loop=loop)
database.initialize()

# destiny = pydest.Pydest(BUNGIE_API_KEY, loop, os.environ.get('CLIENT_ID'), os.environ.get('CLIENT_SECRET'))


# @backoff.on_exception(backoff.expo, pydest.pydest.PydestException, max_time=60)
# async def get_activity(destiny, activity_id):
#     return await destiny.api.get_post_game_carnage_report(activity_id)


# async def update_games(database, destiny):
#     games_db = await database.get_games()
#     games = []
#     for game in games_db:
#         # pgcr = await get_activity(destiny, game.instance_id)

#         if not game.reference_id:
#             pgcr = await get_activity(destiny, game.instance_id)
#             # game.reference_id = int(pgcr['Response']['activityDetails']['referenceId'])
#             # games.append(game)

#     # async with database.objects.atomic():
#     #     await database.update_game_bulk(games, ['reference_id'], 100)


async def main():
    # members = await destiny.api.get_group_pending_members(
    #     '803613', 
    #     access_token='CImhARKGAgAgBatSepFGYD+Bm5xZtlewzkOxbgbunmu5HwQqSipQ+iXgAAAAmkq4hU+Vjrlv4Eh0253AMji2DzeAXhuBcdsCC1bmB9wrquZR/Is3ucOF1j2H3aek6LPfl2kVFEL1vshwIzm8Y3SymYCUHux0WMu7Y5kSc/kIJ00QFKE/VqRKlZEUI1O/1RdOMW7/WRDlfBfTKXvbvwqfgrGst/ZvXfo4/6so4DMYjSfiypxVY1nehkIkjabhEsfKb5bHo42H2FoEcwjsSviesk5ISAqKR+FZR+sHzUqCIDjymUzjQXA4LtQfQ5MwjLkrp6NbZemFbO7TXMX+ZPIrm9f1POyvm+mA8nsWJQw=',
    #     refresh_token='CImhARKGAgAgSV35L/tbGgtsYpuwA7TX6QCYXKNhR413mFeWjtr8R2jgAAAACjt4I4+ktv0irwoDSY2Ru+WbRoNn7kDtle02jNChyfnLSiNk6feHd0QB+QxQY0OEnp8dXb0rEvi4cYsMN489M5GWjFYWJyHQZPiiOnK1zV8g81mv0QdZeznPQEmnftZVlcTCUbpddHQZbVC00/N0GPGZEdfASFGe9k8cgxkwSIrzxBW62VUTlztaIoiOGVNDT/Dh2QK8d++eHFxosBRyenKbQmOIkRrbCYUq3Y/PDOFl+0QiVfsOhm2J7uRihF4fTTxw7iGmPNPlkjSg21fRRcis/fFv8mduiWZ6Uq0WO1s='
    # )
    # data = await destiny.api.get_profile(1, 4611686018469069377, [200])
    # data = await destiny.api.group.get_by_id(803613)
    # print(data)
    # data = await destiny.api.user.get_bungie_net_user_by_id(13407335)
    # print(data)
    # data = await destiny.api.get_destiny_manifest()
    # print(data)
    # await update_games(database, destiny)
    # query = Member.select().where(
    #     (Member.xbox_id == 15971319) |
    #     (Member.psn_id == 15971319) |
    #     (Member.blizzard_id == 15971319) |
    #     (Member.bungie_id == 15971319)
    # )
    # result = await database.objects.get(query)
    # print(vars(result))
    # bungie_members = {}
    # async for member in get_all_members(destiny, 881267):
    #     bungie_members[f'11-{member}'] = dict(
    #         bungie_id=member.memberships.bungie.id,
    #         bungie_username=member.memberships.bungie.username,
    #         join_date=member.join_date,
    #         blizzard_id=member.memberships.blizzard.id,
    #         blizzard_username=member.memberships.blizzard.username,
    #         psn_id=member.memberships.psn.id,
    #         psn_username=member.memberships.psn.username,
    #         xbox_id=member.memberships.xbox.id,
    #         xbox_username=member.memberships.xbox.username
    #     )
    # print(bungie_members)
    # await member_sync(database, destiny, 577158002000527390, loop)
    username = Case(ClanMember.platform_id, (
        (1, Member.xbox_username),
        (2, Member.psn_username),
        (4, Member.blizzard_username))
    )

    query = await database.objects.execute(Member.select(username.alias('username')).join(ClanMember).order_by(username))
    for member in query:
        print(member.username)
    # print(vars(query))

try:
    loop.run_until_complete(main())
except KeyboardInterrupt:
    pass
finally:
    # destiny.close()
    database.close()
loop.close()
