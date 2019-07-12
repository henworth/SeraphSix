#!/usr/bin/env python3.7
import itertools
import asyncio
import json
import logging
import os
import pydest

from datetime import datetime
# from peewee import DoesNotExist, IntegrityError, InternalError
from seraphsix.database import Database, Member
from seraphsix.destiny import constants

DATABASE_URL = os.environ.get('DATABASE_URL')
BUNGIE_API_KEY = os.environ.get('BUNGIE_API_KEY')

logging.basicConfig(level=logging.INFO)
logging.getLogger(__name__)
logging.getLogger('aiohttp.client').setLevel(logging.ERROR)

loop = asyncio.new_event_loop()
database = Database(DATABASE_URL, loop=loop)
database.initialize() 

destiny = pydest.Pydest(BUNGIE_API_KEY, loop=loop)


def grouper(n, iterable):
    it = iter(iterable)
    while True:
       chunk = tuple(itertools.islice(it, n))
       if not chunk:
           return
       yield chunk


async def get_profile(destiny, member_id, platform_id=constants.PLATFORM_XBOX):
    return await destiny.api.get_profile(platform_id, member_id, [constants.COMPONENT_CHARACTERS])


async def get_last_played(destiny, member):
    profile = await get_profile(destiny, member.xbox_id, member.clanmember.platform_id)
    acct_last_played = None
    for _, data in profile['Response']['characters']['data'].items():
        print(data['minutesPlayedThisSession'])
        char_last_played = datetime.strptime(
            data['dateLastPlayed'], '%Y-%m-%dT%H:%M:%S%z')
        if not acct_last_played or char_last_played > acct_last_played:
            acct_last_played = char_last_played
    return acct_last_played


async def main():
    # thing = await database.get_clan_member_by_discord_id(245992950033678337, 803613)
    # last_played = await get_last_played(destiny, thing)
    thing = await database.get_clan_members_active(1, days=30)
    for stuff in thing:
        print(stuff.clanmember.last_active)
    # thing = await database.get_twitter_channels(59804598)
    # for channel in thing:
    #     print(channel.channel_id)
    # for member_db in await database.get_members(is_active=True):
    #     await database.create_clan_member(member_db, 803613, join_date=member_db.join_date, is_active=True, platform_id=1)
    # data = await destiny.api.get_profile(1, 4611686018469069377, [200])
    # print(json.dumps(data))
    # clan_db = await database.get_clans_by_guild(468491715230302208)
    # clan_members = await database.get_clan_members(clan_db.clan_id, sorted_by='xbox_username')
    # group = grouper(10, clan_members)
    # for chunk in group:
    #     print([item.xbox_username for item in chunk])


try:
    loop.run_until_complete(main())
except KeyboardInterrupt:
    pass
finally:
    destiny.close()
    database.close()
loop.close()
