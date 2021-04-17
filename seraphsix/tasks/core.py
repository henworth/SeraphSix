import arq
import asyncio
import backoff
import logging
import msgpack

from playhouse.shortcuts import model_to_dict
from pydest.pydest import PydestException
from pyrate_limiter import BucketFullException
from seraphsix import constants
from seraphsix.tasks.config import Config
from seraphsix.errors import MaintenanceError, PrivateHistoryError
from seraphsix.models.destiny import DestinyResponse, DestinyTokenResponse, DestinyTokenErrorResponse
from seraphsix.tasks.parsing import decode_datetime, encode_datetime

log = logging.getLogger(__name__)
config = Config()


async def create_redis_jobs_pool(config):
    return await arq.create_pool(
        config,
        job_serializer=lambda b: msgpack.packb(b, default=encode_datetime),
        job_deserializer=lambda b: msgpack.unpackb(b, object_hook=decode_datetime)
    )


def backoff_handler(details):
    if details['wait'] > 30 or details['tries'] > 10:
        log.debug(
            f"Backing off {details['wait']:0.1f} seconds after {details['tries']} tries "
            f"for {details['target']} args {details['args']} kwargs {details['kwargs']}"
        )


@backoff.on_exception(backoff.constant, (PrivateHistoryError, MaintenanceError), max_tries=1, logger=None)
@backoff.on_exception(
    backoff.expo, (PydestException, asyncio.TimeoutError, BucketFullException), logger=None, on_backoff=backoff_handler)
async def execute_pydest(function, *args, **kwargs):
    retval = None
    log.debug(f"{function} {args} {kwargs}")

    async with config.destiny_api_limiter.ratelimit('destiny_api', delay=True):
        data = await function(*args, **kwargs)

    log.debug(f"{function} {args} {kwargs} - {data}")

    try:
        res = DestinyResponse.from_dict(data)
    except KeyError:
        try:
            res = DestinyTokenResponse.from_dict(data)
        except KeyError:
            res = DestinyTokenErrorResponse.from_dict(data)
        except Exception:
            raise RuntimeError(f"Cannot parse Destiny API response {data}")
    else:
        if res.error_status != 'Success':
            # https://bungie-net.github.io/#/components/schemas/Exceptions.PlatformErrorCodes
            if res.error_status == 'SystemDisabled':
                raise MaintenanceError
            elif res.error_status in ['PerEndpointRequestThrottleExceeded', 'DestinyDirectBabelClientTimeout']:
                raise PydestException
            elif res.error_status == 'DestinyPrivacyRestriction':
                raise PrivateHistoryError
            else:
                log.error(f"Error running {function} {args} {kwargs} - {res}")
                if res.error_status in ['DestinyAccountNotFound']:
                    raise PydestException
    retval = res
    log.debug(f"{function} {args} {kwargs} - {res}")
    return retval


def member_dbs_to_dict(member_dbs):
    members = []
    for member_db in member_dbs:
        member_dict = model_to_dict(member_db.clanmember, recurse=False)
        member_dict['member'] = model_to_dict(member_db, recurse=False)
        members.append(member_dict)
    return members


async def get_cached_members(ctx, guild_id, guild_name):
    cache_key = f'{guild_id}-members'
    clan_members = await ctx['redis_cache'].get(cache_key)
    if not clan_members:
        clan_members = await set_cached_members(ctx, guild_id, guild_name)
    clan_members = msgpack.unpackb(clan_members, object_hook=decode_datetime, raw=False)
    return clan_members


async def set_cached_members(ctx, guild_id, guild_name):
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
    log.info(f"Successfully cached all members of {guild_name} ({guild_id})")
    return members
