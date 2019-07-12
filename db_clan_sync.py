#!/usr/bin/env python3.7
import json
import jsonpickle
import asyncio
import logging
import os
import pydest

from datetime import datetime, timezone, timedelta
from peewee import DoesNotExist, IntegrityError, InternalError
from seraphsix.database import Database
from seraphsix.destiny.models import Member, User
from seraphsix.destiny.constants import PLATFORM_BLIZ, PLATFORM_BNG, PLATFORM_PSN, PLATFORM_XBOX, COMPONENT_CHARACTERS

DATABASE_URL = os.environ.get('DATABASE_URL')
BUNGIE_API_KEY = os.environ.get('BUNGIE_API_KEY')

logging.basicConfig(level=logging.INFO)
logging.getLogger(__name__)
logging.getLogger('aiohttp.client').setLevel(logging.ERROR)

loop = asyncio.new_event_loop()
database = Database(DATABASE_URL, loop=loop)
database.initialize() 

destiny = pydest.Pydest(BUNGIE_API_KEY, loop=loop)


async def get_all_members(group_id):
    group = await destiny.api.get_group_members(group_id)
    group_members = group['Response']['results']
    for member in group_members:
        thing = await destiny.api.get_membership_data_by_id(
            member['destinyUserInfo']['membershipId'], 
        )
        yield User(thing['Response'])


async def main(group_id):
    try:
        res = await destiny.api.get_group(group_id)
    except Exception:
        logging.error("Clan not found")
        return
    # logging.info(jsonpickle.encode(res['Response']))

    try:
        await database.create_clan(group_id, 1)
    except IntegrityError:
        pass

    # bungie_members = {
    #     PLATFORM_BLIZ: {},
    #     PLATFORM_PSN: {},
    #     PLATFORM_XBOX: {}
    # }
    bungie_members = []
    async for member in get_all_members(group_id):  # pylint: disable=not-an-iterable
        member_info = dict(
            bungie_id=member.memberships.bungie.id,
            bungie_username=member.memberships.bungie.username,
            xbox_id=member.memberships.xbox.id,
            xbox_username=member.memberships.xbox.username,
            psn_id=member.memberships.psn.id,
            psn_username=member.memberships.psn.username,
            blizzard_id=member.memberships.blizzard.id,
            blizzard_username=member.memberships.blizzard.username
        )
        if member_info not in bungie_members:
            bungie_members.append(member_info)
    
    for member in bungie_members:
        member_db = await database.create_member(member)

    #     if member.memberships.blizzard.id:
    #         bungie_members[PLATFORM_BLIZ].update(
    #             {member.memberships.blizzard.id: member_info})
    #     elif member.memberships.psn.id:
    #         bungie_members[PLATFORM_PSN].update(
    #             {member.memberships.psn.id: member_info})
    #     elif member.memberships.xbox.id:
    #         bungie_members[PLATFORM_XBOX].update(
    #             {member.memberships.xbox.id: member_info})

    # # logging.info(jsonpickle.encode(bungie_members))

    # # for member in await database.get_clan_members(clan_db.clan_id):

    # bungie_member_set = set(
    #     [f'{PLATFORM_BLIZ}-{member_id}' for member_id in bungie_members[PLATFORM_BLIZ].keys()] +
    #     [f'{PLATFORM_PSN}-{member_id}' for member_id in bungie_members[PLATFORM_PSN].keys()] +
    #     [f'{PLATFORM_XBOX}-{member_id}' for member_id in bungie_members[PLATFORM_XBOX].keys()]
    # )

    # db_members = {PLATFORM_BLIZ: {}, PLATFORM_PSN: {}, PLATFORM_XBOX: {}}
    # for member in await database.get_clan_members(group_id):
    #     if member.blizzard_id:
    #         db_members[PLATFORM_BLIZ].update({member.blizzard_id: member})
    #     elif member.psn_id:
    #         db_members[PLATFORM_PSN].update({member.psn_id: member})
    #     elif member.xbox_id:
    #         db_members[PLATFORM_XBOX].update({member.xbox_id: member})

    # db_member_set = set(
    #     [f'{PLATFORM_BLIZ}-{member_id}' for member_id in db_members[PLATFORM_BLIZ].keys()] +
    #     [f'{PLATFORM_PSN}-{member_id}' for member_id in db_members[PLATFORM_PSN].keys()] +
    #     [f'{PLATFORM_XBOX}-{member_id}' for member_id in db_members[PLATFORM_XBOX].keys()]
    # )

    # new_members = bungie_member_set
    # # purged_members = db_member_set - bungie_member_set
    # for id_hash in new_members:
    #     platform, user_id = id_hash.split('-')
    #     member_info = bungie_members[int(platform)][int(user_id)]

    #     try:
    #         member_db = await database.get_clan_member_by_platform(int(user_id), int(platform), group_id)
    #     except DoesNotExist:
    #         join_date = member_info.pop('join_date')
    #         try:
    #             member_db = await database.create_member(member_info)
    #         except IntegrityError:
    #             member_db = await database.get_member_by_platform(int(user_id), PLATFORM_BLIZ)
    #             if int(platform) == PLATFORM_BLIZ:
    #                 member_db.blizzard_id = member_info['blizzard_id']
    #                 member_db.blizzard_username = member_info['blizzard_username']
    #             elif int(platform) == PLATFORM_PSN:
    #                 member_db.psn_id = member_info['psn_id']
    #                 member_db.psn_username = member_info['psn_username']
    #             elif int(platform) == PLATFORM_XBOX:
    #                 member_db.xbox_id = member_info['xbox_id']
    #                 member_db.xbox_username = member_info['xbox_username']
    #             await database.update(member_db)

    #         member_db = await database.create_clan_member(
    #             member_db,
    #             group_id,
    #             join_date=join_date,
    #             platform_id=platform,
    #             is_active=True
    #         )

    #     if (hasattr(member_db, 'clanmember') and not member_db.clanmember.is_active) or (hasattr(member_db, 'is_active') and not member_db.is_active):
    #         try:
    #             member_db.clanmember.is_active = True
    #             member_db.clanmember.join_date = member_info['join_date']
    #             await database.update(member_db)
    #         except Exception:
    #             logging.exception(
    #                 f"Could update member \"{member_db.id}\"")
    #             return

    # # for member in purged_members:
    # #     member_db = db_members[member]
    # #     member_db.is_active = False
    # #     await database.update(member_db)

    # if len(new_members) > 0:
    #     new_member_usernames = []
    #     for id_hash in new_members:
    #         platform, user_id = id_hash.split('-')
    #         member_info = bungie_members[int(platform)][int(user_id)]

    #         if member_info['blizzard_username']:
    #             username = member_info['blizzard_username']
    #         elif member_info['psn_username']:
    #             username = member_info['psn_username']
    #         elif member_info['xbox_username']:
    #             username = member_info['xbox_username']

    #         new_member_usernames.append(username)
    #     added = sorted(new_member_usernames, key=lambda s: s.lower())
    #     logging.info(f"Added members {added}")

    # if len(purged_members) > 0:
    #     purged_member_usernames = []
    #     for xbox_id in purged_members:
    #         member_db = await database.get_member_by_xbox_id(xbox_id)
    #         purged_member_usernames.append(member_db.xbox_username)
    #     purged = sorted(purged_member_usernames, key=lambda s: s.lower())
    #     logging.info(f"Purged members {purged}")


try:
    loop.run_until_complete(main(881267))
except KeyboardInterrupt:
    pass
finally:
    destiny.close()
    # database.close()
loop.close()
