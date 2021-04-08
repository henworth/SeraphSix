import asyncio
import backoff
import logging
import msgpack

from playhouse.shortcuts import model_to_dict
from pydest.pydest import PydestException, PydestPrivateHistoryException, PydestMaintenanceException
from seraphsix import constants
from seraphsix.errors import MaintenanceError
from seraphsix.tasks.parsing import decode_datetime, encode_datetime

log = logging.getLogger(__name__)


def backoff_handler(details):
    if details['wait'] > 30 or details['tries'] > 10:
        log.debug(
            f"Backing off {details['wait']:0.1f} seconds after {details['tries']} tries "
            f"for {details['target']} args {details['args']} kwargs {details['kwargs']}"
        )


@backoff.on_exception(
    backoff.expo,
    (PydestPrivateHistoryException, PydestMaintenanceException),
    max_tries=1, logger=None)
# @backoff.on_exception(backoff.expo, asyncio.TimeoutError, max_tries=1, logger=None)
@backoff.on_exception(backoff.expo, (PydestException, asyncio.TimeoutError), logger=None, on_backoff=backoff_handler)
async def execute_pydest(function, *args, **kwargs):
    retval = None
    try:
        data = await function(*args, **kwargs)
    except PydestMaintenanceException:
        raise MaintenanceError
    except PydestPrivateHistoryException:
        return retval
    else:
        if 'Response' in data:
            retval = data['Response']
    return retval


def member_dbs_to_dict(member_dbs):
    members = []
    for member_db in member_dbs:
        member_dict = model_to_dict(member_db.clanmember, recurse=False)
        member_dict['member'] = model_to_dict(member_db, recurse=False)
        members.append(member_dict)
    return members


async def get_cached_members(ctx, guild_id):
    cache_key = f'{guild_id}-members'
    clan_members = await ctx['redis_cache'].get(cache_key)
    if not clan_members:
        clan_members = await set_cached_members(ctx, guild_id)
    clan_members = msgpack.unpackb(clan_members, object_hook=decode_datetime, raw=False)
    return clan_members


async def set_cached_members(ctx, guild_id):
    cache_key = f'{guild_id}-members'
    redis_cache = ctx['redis_cache']
    database = ctx['database']

    members = []
    member_dbs = await database.get_clan_members_by_guild_id(guild_id)
    for member_db in member_dbs:
        member_dict = model_to_dict(member_db.clanmember, recurse=False)
        member_dict['member'] = model_to_dict(member_db, recurse=False)
        members.append(member_dict)
    members = msgpack.packb([member for member in members], default=encode_datetime, use_bin_type=True)
    await redis_cache.set(cache_key, members, expire=constants.TIME_HOUR_SECONDS)
    return members
