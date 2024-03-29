#!/usr/bin/env python3
import aioredis
import asyncio
import discord
import io
import logging
import peony
import traceback

from discord.ext import commands, tasks
from peony import PeonyClient
from pydest.pydest import Pydest
from the100 import The100

from seraphsix import constants, Database
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.errors import (
    InvalidCommandError,
    InvalidGameModeError,
    InvalidMemberError,
    InvalidAdminError,
    NotRegisteredError,
    ConfigurationError,
    MissingTimezoneError,
    MaintenanceError,
)
from seraphsix.models.database import Guild, TwitterChannel
from seraphsix.tasks.clan import ack_clan_application
from seraphsix.tasks.core import create_redis_jobs_pool
from seraphsix.tasks.discord import store_sherpas, update_sherpa

log = logging.getLogger(__name__)
intents = discord.Intents.default()
intents.members = True
intents.reactions = True

STARTUP_EXTENSIONS = [
    "seraphsix.cogs.clan",
    "seraphsix.cogs.game",
    "seraphsix.cogs.member",
    "seraphsix.cogs.register",
    "seraphsix.cogs.server",
]


async def _prefix_callable(bot, message):
    """Get current command prefix"""
    base = [f"<@{bot.user.id}> "]
    if isinstance(message.channel, discord.abc.PrivateChannel):
        base.append("?")
    else:
        guild_db, _ = await Guild.get_or_create(guild_id=message.guild.id)
        base.append(guild_db.prefix)
    return base


class SeraphSix(commands.Bot):
    def __init__(self, config):
        super().__init__(
            command_prefix=_prefix_callable,
            case_insensitive=True,
            intents=intents,
            help_command=commands.DefaultHelpCommand(
                no_category="Assorted", dm_help=True, verify_checks=False
            ),
        )

        self.config = config
        self.database = Database(config.database_url, config.database_conns)

        self.destiny = Pydest(
            api_key=config.destiny.api_key,
            client_id=config.destiny.client_id,
            client_secret=config.destiny.client_secret,
        )

        self.the100 = The100(config.the100.api_key, config.the100.base_url)

        self.twitter = None
        if (
            config.twitter.consumer_key
            and config.twitter.consumer_secret
            and config.twitter.access_token
            and config.twitter.access_token_secret
        ):
            self.twitter = PeonyClient(**config.twitter.asdict())

        self.ext_conns = {
            "database": self.database,
            "destiny": self.destiny,
            "twitter": self.twitter,
            "the100": self.the100,
            "redis_cache": None,
            "redis_jobs": None,
        }

        for extension in STARTUP_EXTENSIONS:
            try:
                self.load_extension(extension)
            except Exception as e:
                exc = traceback.format_exception(type(e), e, e.__traceback__)
                log.error(f"Failed to load extension {extension}: {exc}")

        if config.enable_activity_tracking:
            self.update_members.start()

        self.cache_clan_members.start()

    @tasks.loop(minutes=5.0)
    async def update_members(self):
        guilds = await Guild.all()
        if not guilds:
            return
        for guild in guilds:
            guild_id = guild.guild_id
            discord_guild = await self.fetch_guild(guild_id)
            guild_name = str(discord_guild)

            log.info(
                f"Queueing task to find last active date for all members of {guild_name} ({guild_id})"
            )
            await self.ext_conns["redis_jobs"].enqueue_job(
                "store_last_active",
                guild_id,
                guild_name,
                _job_id=f"store_last_active-{guild_id}",
            )

            log.info(
                f"Queueing task to find recent games for all members {guild_name} ({guild_id})"
            )
            await self.ext_conns["redis_jobs"].enqueue_job(
                "store_all_games",
                guild_id,
                guild_name,
                _job_id=f"store_all_games-{guild_id}",
            )

    @update_members.before_loop
    async def before_update_members(self):
        await self.wait_until_ready()

    async def update_sherpa_roles(self):
        guilds = await Guild.all()
        if not guilds:
            return
        tasks = [store_sherpas(self, guild) for guild in guilds if guild.track_sherpas]
        await asyncio.gather(*tasks)

    async def process_tweet(self, tweet):
        channels = await TwitterChannel.filter(twitter_id=tweet.user.id)

        if not channels:
            log.info(
                f"Could not find any Discord channels for {tweet.user.screen_name} ({tweet.user.id})"
            )
            return

        twitter_url = f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}"
        log_message = f"Sending tweet {tweet.id} by {tweet.user.screen_name} to "

        for channel in channels:
            log.info(log_message + str(channel.channel_id))
            channel = self.get_channel(channel.channel_id)
            await channel.send(twitter_url)

    async def track_tweets(self):
        stream = self.twitter.stream.statuses.filter.post(
            follow=constants.TWITTER_FOLLOW_USERS
        )
        async for tweet in stream:
            if peony.events.tweet(tweet) and not peony.events.retweet(tweet):
                if tweet.in_reply_to_status_id:
                    continue
                # For some reason non-followed users sometimes sneak into the stream
                if tweet.user.id not in constants.TWITTER_FOLLOW_USERS:
                    continue
                self.loop.create_task(self.process_tweet(tweet))

    async def connect_redis(self):
        self.redis = await aioredis.create_redis_pool(self.config.redis_url)
        self.ext_conns["redis_cache"] = self.redis
        self.ext_conns["redis_jobs"] = await create_redis_jobs_pool()

    @tasks.loop(hours=1.0)
    async def cache_clan_members(self):
        guilds = await Guild.all()
        if not guilds:
            return
        for guild in guilds:
            guild_id = guild.guild_id
            discord_guild = await self.fetch_guild(guild.guild_id)
            guild_name = str(discord_guild)
            log.info(
                f"Queueing task to update cached members of {guild_name} ({guild_id})"
            )
            await self.ext_conns["redis_jobs"].enqueue_job(
                "set_cached_members",
                guild_id,
                guild_name,
                _job_id=f"set_cached_members-{guild_id}",
            )

    @cache_clan_members.before_loop
    async def before_cache_clan_members(self):
        await self.wait_until_ready()

    async def on_connect(self):
        await self.database.initialize()
        await self.connect_redis()

    async def on_ready(self):
        guilds = await Guild.all()
        if not guilds:
            return
        self.guild_map = {}
        for guild in guilds:
            self.guild_map[guild.guild_id] = guild

        self.log_channel = self.get_channel(self.config.log_channel)
        self.reg_channel = self.get_channel(self.config.reg_channel)

        start_message = (
            f"Logged in as {self.user.name} ({self.user.id}) "
            f"{discord.utils.oauth_url(self.user.id)}"
        )
        log.info(start_message)
        await self.log_channel.send("Seraph Six has started...")

        if self.twitter:
            log.info("Starting Twitter stream tracking")
            self.loop.create_task(self.track_tweets())

        await self.update_sherpa_roles()

    async def on_member_update(self, before, after):
        if not before.bot:
            await update_sherpa(self, before, after)

    async def on_raw_reaction_add(self, payload):
        if payload.channel_id == self.guild_map[
            payload.guild_id
        ].admin_channel and payload.emoji.name in [
            constants.EMOJI_CHECKMARK,
            constants.EMOJI_CROSSMARK,
        ]:
            await ack_clan_application(self, payload)

    async def on_guild_join(self, guild):
        await self.log_channel.send(f"Seraph Six joined {guild.name} (id:{guild.id})!")

    async def on_guild_remove(self, guild):
        await self.log_channel.send(f"Seraph Six left {guild.name} (id:{guild.id})...")

    async def on_command_error(self, ctx, error):
        manager = MessageManager(ctx)

        text = None
        if isinstance(error, commands.MissingPermissions):
            text = "Sorry, but you do not have permissions to do that!"
        elif isinstance(
            error,
            (
                ConfigurationError,
                InvalidCommandError,
                InvalidMemberError,
                InvalidGameModeError,
                NotRegisteredError,
                MissingTimezoneError,
                MaintenanceError,
                InvalidAdminError,
            ),
        ):
            text = error
        elif isinstance(error, commands.CommandNotFound):
            text = f"Invalid command `{ctx.message.content}`."
        elif isinstance(error, commands.MissingRequiredArgument):
            text = f"Required argument `{error.param}` is missing."
        else:
            error_trace = traceback.format_exception(
                type(error), error, error.__traceback__
            )
            log.error(f"Ignoring exception in command '{ctx.command}': {error_trace}")
            if ctx.guild:
                location = f"guild `{ctx.guild.id}`"
            else:
                location = "user dm"
            log_channel_message = (
                f"Exception `{error}` occurred in {location} in command `{ctx.command}`. "
                f"See attachment for full stack trace."
            )
            await self.log_channel.send(
                content=log_channel_message,
                file=discord.File(
                    io.BytesIO("".join(error_trace).encode("utf-8")),
                    filename="exception.txt",
                ),
            )
            await manager.send_message(
                (
                    f"Unexpected error occurred while running `{ctx.command}`. "
                    f"Details have been dispatched to the development team."
                ),
                clean=False,
            )

        if text:
            await manager.send_and_clean(
                f"{text}\nType `{ctx.prefix}help` for more information."
            )

    # Update guild count at bot listing sites and in bots status/presence
    # async def update_status(self):
    #     await api.bot_lists.update_guild_counts(self)
    #     status = discord.Game(name=self.status_formats[self.status_index].
    #                           format(len(self.guilds)))
    #     await self.change_presence(activity=status)

    async def on_message(self, message):
        if not message.author.bot:
            try:
                ctx = await self.get_context(message)
                await self.invoke(ctx)
            except AttributeError as error:
                error_trace = traceback.format_exception(
                    type(error), error, error.__traceback__
                )
                log.error(f"Ignoring exception from message '{message}': {error_trace}")

    async def close(self):
        await self.log_channel.send("Seraph Six is shutting down...")
        await self.ext_conns["destiny"].close()
        await self.ext_conns["database"].close()
        await self.ext_conns["the100"].close()

        if self.twitter:
            await self.ext_conns["twitter"].close()

        self.ext_conns["redis_jobs"].close()
        await self.ext_conns["redis_jobs"].wait_closed()

        self.ext_conns["redis_cache"].close()
        await self.ext_conns["redis_cache"].wait_closed()

        await super().close()
