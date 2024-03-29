import arq
import asyncio
import backoff
import discord
import logging
import pickle
import pydest

from aiohttp.client_exceptions import ServerDisconnectedError, ClientOSError
from pydest.pydest import PydestException
from pyrate_limiter import BucketFullException

from seraphsix import constants
from seraphsix.models import deserializer, serializer
from seraphsix.models.destiny import (
    DestinyResponse,
    DestinyTokenResponse,
    DestinyTokenErrorResponse,
)
from seraphsix.tasks.config import Config
from seraphsix.errors import MaintenanceError, PrivateHistoryError, InvalidCommandError

log = logging.getLogger(__name__)
config = Config()


async def create_redis_jobs_pool():
    return await arq.create_pool(
        config.arq_redis,
        job_serializer=lambda b: serializer(b),
        job_deserializer=lambda b: deserializer(b),
    )


async def queue_redis_job(ctx, message, *args, **kwargs):
    log.info(f"Queueing task to {message}")
    await ctx["redis_jobs"].enqueue_job(*args, **kwargs)


def backoff_handler(details):
    if details["wait"] > 30 or details["tries"] > 10:
        log.debug(
            f"Backing off {details['wait']:0.1f} seconds after {details['tries']} tries "
            f"for {details['target']} args {details['args']} kwargs {details['kwargs']}"
        )


@backoff.on_exception(
    backoff.constant, (PrivateHistoryError, MaintenanceError), max_tries=1, logger=None
)
@backoff.on_exception(
    backoff.expo,
    (
        PydestException,
        asyncio.TimeoutError,
        BucketFullException,
        ServerDisconnectedError,
        ClientOSError,
    ),
    logger=None,
    on_backoff=backoff_handler,
)
async def execute_pydest(function, *args, **kwargs):
    retval = None

    if "return_type" in kwargs:
        return_type = kwargs.pop("return_type")
    else:
        return_type = DestinyResponse

    log.debug(f"{function} {args} {kwargs}")

    async with config.destiny_api_limiter.ratelimit("destiny_api", delay=True):
        data = await function(*args, **kwargs)

    log.debug(f"{function} {args} {kwargs} - {data}")

    # None is a valid value for return_type, in this case we don't try and turn it into
    # a dataclass. This is primarily used for manifest decoding.
    if not return_type:
        return data

    try:
        res = return_type.from_dict(data)
    except KeyError:
        try:
            res = DestinyTokenErrorResponse.from_dict(data)
        except Exception:
            raise RuntimeError(f"Cannot parse Destiny API response {data}")
    else:
        if not res:
            raise RuntimeError("Unexpected empty response from the Destiny API")

        # DestinyTokenResponse and DestinyTokenErrorResponse have an "error" field
        if hasattr(res, "error") and res.error:
            log.error(f"Error running {function} {args} {kwargs} - {res}")
            raise RuntimeError(f"Error running {function} {args} {kwargs} - {res}")
        elif hasattr(res, "error_status") and res.error_status != "Success":
            # The rest of the API responses use "error_status"
            # https://bungie-net.github.io/#/components/schemas/Exceptions.PlatformErrorCodes
            if res.error_status == "SystemDisabled":
                raise MaintenanceError
            elif res.error_status in [
                "PerEndpointRequestThrottleExceeded",
                "DestinyDirectBabelClientTimeout",
            ]:
                raise PydestException
            elif res.error_status == "DestinyPrivacyRestriction":
                raise PrivateHistoryError
            elif res.error_status == "WebAuthRequired":
                raise pydest.PydestTokenException
            else:
                log.error(f"Error running {function} {args} {kwargs} - {res}")
                if res.error_status not in [
                    "DestinyAccountNotFound",
                    "ClanMaximumMembershipReached",
                ]:
                    raise PydestException
    retval = res
    log.debug(f"{function} {args} {kwargs} - {res}")
    return retval


async def execute_pydest_auth(ctx, func, auth_user_db, manager, *args, **kwargs):
    try:
        res = await execute_pydest(func, *args, **kwargs)
    except pydest.PydestTokenException:
        tokens = await refresh_user_tokens(ctx, manager, auth_user_db)
        kwargs["access_token"] = tokens.access_token
        res = await execute_pydest(func, *args, **kwargs)
        auth_user_db.bungie_access_token = tokens.access_token
        auth_user_db.bungie_refresh_token = tokens.refresh_token
        await auth_user_db.save()
    return res


async def refresh_user_tokens(ctx, manager, auth_user_db):
    tokens = await execute_pydest(
        ctx["destiny"].api.refresh_oauth_token,
        auth_user_db.bungie_refresh_token,
        return_type=DestinyTokenResponse,
    )

    if tokens.error:
        log.warning(f"{tokens.error_description} Registration is needed")
        user_info = await register(
            manager,
            "Your registration token has expired and re-registration is needed.",
        )
        if not user_info:
            raise InvalidCommandError(
                "I'm not sure where you went. We can try this again later."
            )
        tokens = {
            token: user_info.get(token)
            for token in [tokens.access_token, tokens.refresh_token]
        }

    return tokens


async def register(manager, extra_message="", confirm_message=""):
    ctx = manager.ctx

    if not confirm_message:
        confirm_message = "Registration Complete"

    auth_url = (
        f"https://{ctx.bot.config.destiny.redirect_host}/oauth?state={ctx.author.id}"
    )

    if not isinstance(ctx.channel, discord.abc.PrivateChannel):
        await manager.send_message(
            f"{extra_message} Registration instructions have been sent directly to {ctx.author}".strip(),
            mention=False,
            clean=False,
        )

    # Prompt user with link to Bungie.net OAuth authentication
    e = discord.Embed(colour=constants.BLUE)
    e.title = "Click Here to Register"
    e.url = auth_url
    e.description = (
        "Click the above link to register your Bungie.net account with Seraph Six. "
        "Registering will allow Seraph Six to access your connected Destiny 2 "
        "accounts. At no point will Seraph Six have access to your password."
    )
    registration_msg = await manager.send_private_embed(e)

    # Wait for user info from the web server via Redis
    res = await ctx.bot.ext_conns["redis_cache"].subscribe(ctx.author.id)

    tsk = asyncio.create_task(wait_for_msg(res[0]))
    try:
        user_info = await asyncio.wait_for(tsk, timeout=constants.TIME_MIN_SECONDS)
    except asyncio.TimeoutError:
        log.debug(
            f"Timed out waiting for {str(ctx.author)} ({ctx.author.id}) to register"
        )
        await manager.send_private_message(
            "I'm not sure where you went. We can try this again later."
        )
        await registration_msg.delete()
        await manager.clean_messages()
        await ctx.bot.ext_conns["redis_cache"].unsubscribe(ctx.author.id)
        return (None, None)
    await ctx.author.dm_channel.trigger_typing()

    # Send confirmation of successful registration
    e = discord.Embed(colour=constants.BLUE, title=confirm_message)
    embed = await manager.send_private_embed(e)
    await ctx.bot.ext_conns["redis_cache"].unsubscribe(ctx.author.id)

    return embed, user_info


async def wait_for_msg(channel):
    """Wait for a message on the specified Redis channel"""
    while await channel.wait_message():
        pickled_msg = await channel.get()
        return pickle.loads(pickled_msg)


# def member_dbs_to_dict(member_dbs):
#     members = []
#     for member_db in member_dbs:
#         member_dict = model_to_dict(member_db, recurse=False)
#         member_dict['clanmember'] = model_to_dict(member_db.clanmember, recurse=False)
#         members.append(member_dict)
#     return members


async def get_cached_members(ctx, guild_id, guild_name):
    return await ctx["database"].get_clan_members_by_guild_id(guild_id)
    # TODO: Until Tortoise has deserialization support, this has to stay disabled
    # cache_key = f'{guild_id}-members'
    # clan_members = await ctx['redis_cache'].get(cache_key)
    # if not clan_members:
    #     clan_members = await set_cached_members(ctx, guild_id, guild_name)
    # clan_members = deserializer(clan_members)
    # member_dbs = [dict_to_model(ClanMember, member) for member in clan_members]
    # return member_dbs


async def set_cached_members(ctx, guild_id, guild_name):
    return
    # TODO: Until Tortoise has deserialization support, this has to stay disabled
    # cache_key = f'{guild_id}-members'
    # redis_cache = ctx['redis_cache']
    # database = ctx['database']

    # members = []
    # member_dbs = await database.get_clan_members_by_guild_id(guild_id)
    # for member_db in member_dbs:
    #     member_dict = model_to_dict(member_db.clanmember, recurse=False)
    #     member_dict['member'] = model_to_dict(member_db, recurse=False)
    #     members.append(member_dict)
    # members = serializer([member for member in members])
    # await redis_cache.set(cache_key, members, expire=constants.TIME_HOUR_SECONDS)
    # log.info(f"Successfully cached all members of {guild_name} ({guild_id})")
    # return members


def get_primary_membership(member_db, restrict_platform_id=None):
    memberships = [
        [constants.PLATFORM_XBOX, member_db.xbox_id, member_db.xbox_username],
        [constants.PLATFORM_PSN, member_db.psn_id, member_db.psn_username],
        [constants.PLATFORM_STEAM, member_db.steam_id, member_db.steam_username],
        [constants.PLATFORM_STADIA, member_db.stadia_id, member_db.stadia_username],
    ]
    membership_id = member_db.primary_membership_id
    platform_id = None
    for membership in memberships:
        if membership_id and membership[1] == membership_id:
            platform_id = membership[0]
            username = membership[2]
            break
        elif (restrict_platform_id and restrict_platform_id == membership[0]) or (
            not membership_id and membership[1]
        ):
            platform_id, membership_id, username = membership
            break

    if not platform_id and not membership_id:
        log.error(f"Platform not found in membership list {memberships}")
    return platform_id, membership_id, username


def get_memberships(member_db):
    memberships = [
        [constants.PLATFORM_BUNGIE, member_db.bungie_id, member_db.bungie_username],
        [constants.PLATFORM_XBOX, member_db.xbox_id, member_db.xbox_username],
        [constants.PLATFORM_PSN, member_db.psn_id, member_db.psn_username],
        [constants.PLATFORM_STEAM, member_db.steam_id, member_db.steam_username],
        [constants.PLATFORM_STADIA, member_db.stadia_id, member_db.stadia_username],
    ]
    retval = {}
    for membership in memberships:
        platform_id, membership_id, username = membership
        if membership_id and username:
            retval[platform_id] = [membership_id, username]
    return retval
