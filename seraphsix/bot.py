#!/usr/bin/env python3.7
import aioredis
import asyncio
import discord
import io
import logging
import peony
import traceback

from discord.ext import commands, tasks
from peewee import DoesNotExist
from peony import PeonyClient
from pydest import Pydest
from the100 import The100

from seraphsix import constants
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.database import Database, Guild, TwitterChannel

from seraphsix.errors import (
    InvalidCommandError, InvalidGameModeError, InvalidMemberError,
    NotRegisteredError, ConfigurationError, MissingTimezoneError, MaintenanceError)
from seraphsix.tasks.activity import store_all_games, store_last_active
from seraphsix.tasks.discord import store_sherpas, update_sherpa

logging.getLogger(__name__)

STARTUP_EXTENSIONS = [
    'seraphsix.cogs.clan', 'seraphsix.cogs.game', 'seraphsix.cogs.member',
    'seraphsix.cogs.register', 'seraphsix.cogs.server'
]


async def _prefix_callable(bot, message):
    """Get current command prefix"""
    base = [f'<@{bot.user.id}> ']
    if isinstance(message.channel, discord.abc.PrivateChannel):
        base.append('?')
    else:
        try:
            guild = await bot.database.get(Guild, guild_id=message.guild.id)
        except DoesNotExist:
            await bot.database.create(Guild, guild_id=message.guild.id)
            base.append('?')
        else:
            base.append(guild.prefix)
    return base


class SeraphSix(commands.Bot):

    def __init__(self, config):
        super().__init__(
            command_prefix=_prefix_callable, case_insensitive=True,
            help_command=commands.DefaultHelpCommand(
                no_category="Assorted", dm_help=True, verify_checks=False)
        )

        self.config = config
        self.database = Database(config.database_url)
        self.database.initialize()

        self.destiny = Pydest(
            api_key=config.bungie.api_key,
            client_id=config.bungie.client_id,
            client_secret=config.bungie.client_secret,
        )

        self.the100 = The100(config.the100.api_key, config.the100.base_url)

        self.twitter = None
        if (config.twitter.consumer_key and config.twitter.consumer_secret and
                config.twitter.access_token and config.twitter.access_token_secret):
            self.twitter = PeonyClient(**config.twitter.asdict())

        for extension in STARTUP_EXTENSIONS:
            try:
                self.load_extension(extension)
            except Exception as e:
                exc = traceback.format_exception(type(e), e, e.__traceback__)
                logging.error(f"Failed to load extension {extension}: {exc}")

        self.bungie_maintenance = False

        if config.enable_activity_tracking:
            self.update_last_active.start()
            self.update_member_games.start()

        self.update_sherpa_roles.start()

    @tasks.loop(minutes=5.0)
    async def update_last_active(self):
        tasks = []
        guilds = await self.database.execute(Guild.select())
        if not guilds:
            return
        for guild in guilds:
            guild_id = guild.guild_id
            logging.info(f"Finding last active dates for all members of {guild_id}")
            tasks.extend([
                store_last_active(self.database, self.destiny, self.redis, member)
                for member in await self.database.get_clan_members_by_guild_id(guild_id)
            ])
        try:
            await asyncio.gather(*tasks)
        except MaintenanceError as e:
            if not self.bungie_maintenance:
                logging.info(f"Bungie maintenance is ongoing: {e}")
                self.bungie_maintenance = True
        else:
            if self.bungie_maintenance:
                self.bungie_maintenance = False
                logging.info("Bungie maintenance has ended")

    @update_last_active.before_loop
    async def before_update_last_active(self):
        await self.wait_until_ready()

    @tasks.loop(hours=1.0)
    async def update_member_games(self):
        await asyncio.sleep(5 * constants.TIME_MIN_SECONDS)

        tasks = []
        guilds = await self.database.execute(Guild.select())
        if not guilds:
            return
        for guild in guilds:
            tasks.extend([
                store_all_games(self, game_mode, guild.guild_id)
                for game_mode in constants.SUPPORTED_GAME_MODES.keys()
            ])
        try:
            await asyncio.gather(*tasks)
        except MaintenanceError as e:
            if not self.bungie_maintenance:
                logging.info(f"Bungie maintenance is ongoing: {e}")
                self.bungie_maintenance = True
        else:
            if self.bungie_maintenance:
                self.bungie_maintenance = False
                logging.info("Bungie maintenance has ended")

    @update_member_games.before_loop
    async def before_update_member_games(self):
        await self.wait_until_ready()

    @tasks.loop(hours=1.0)
    async def update_sherpa_roles(self):
        guilds = await self.database.execute(Guild.select())
        if not guilds:
            return
        tasks = [store_sherpas(self, guild) for guild in guilds]
        await asyncio.gather(*tasks)

    @update_sherpa_roles.before_loop
    async def before_update_sherpa_roles(self):
        await self.wait_until_ready()

    async def process_tweet(self, tweet):
        # pylint: disable=assignment-from-no-return
        query = TwitterChannel.select().where(TwitterChannel.twitter_id == tweet.user.id)
        channels = await self.database.execute(query)

        if not channels:
            logging.info(
                f"Could not find any Discord channels for {tweet.user.screen_name} ({tweet.user.id})")
            return

        twitter_url = f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}"
        log_message = f"Sending tweet {tweet.id} by {tweet.user.screen_name} to "

        for channel in channels:
            logging.info(log_message + str(channel.channel_id))
            channel = self.get_channel(channel.channel_id)
            await channel.send(twitter_url)

    async def track_tweets(self):
        stream = self.twitter.stream.statuses.filter.post(follow=constants.TWITTER_FOLLOW_USERS)
        async for tweet in stream:
            if peony.events.tweet(tweet):
                if tweet.in_reply_to_status_id:
                    continue
                # For some reason non-followed users sometimes sneak into the stream
                if tweet.user.id not in constants.TWITTER_FOLLOW_USERS:
                    continue
                self.loop.create_task(self.process_tweet(tweet))

    async def on_ready(self):
        self.log_channel = self.get_channel(self.config.log_channel)

        start_message = (
            f"Logged in as {self.user.name} ({self.user.id}) "
            f"{discord.utils.oauth_url(self.user.id)}"
        )
        logging.info(start_message)
        await self.log_channel.send("Seraph Six has started...")

        self.redis = await aioredis.create_redis_pool(self.config.redis_url)

        if self.twitter:
            logging.info("Starting Twitter stream tracking")
            self.loop.create_task(self.track_tweets())

    async def on_member_update(self, before, after):
        await update_sherpa(self, before, after)

    async def on_guild_join(self, guild):
        await self.log_channel.send(f"Seraph Six joined {guild.name} (id:{guild.id})!")

    async def on_guild_remove(self, guild):
        await self.log_channel.send(f"Seraph Six left {guild.name} (id:{guild.id})...")

    async def on_command_error(self, ctx, error):
        manager = MessageManager(ctx)

        text = None
        if isinstance(error, commands.MissingPermissions):
            text = "Sorry, but you do not have permissions to do that!"
        elif isinstance(error, (
            ConfigurationError, InvalidCommandError, InvalidMemberError,
            InvalidGameModeError, NotRegisteredError, MissingTimezoneError,
            MaintenanceError
        )):
            text = error
        elif isinstance(error, commands.CommandNotFound):
            text = f"Invalid command `{ctx.message.content}`."
        elif isinstance(error, commands.MissingRequiredArgument):
            text = f"Required argument `{error.param}` is missing."
        else:
            error_trace = traceback.format_exception(type(error), error, error.__traceback__)
            logging.error(f"Ignoring exception in command \"{ctx.command}\": {error_trace}")
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
                file=discord.File(io.BytesIO(''.join(error_trace).encode('utf-8')), filename='exception.txt')
            )
            await manager.send_message(
                (
                    f"Unexpected error occurred while running `{ctx.command}`. "
                    f"Details have been dispatched to the development team."
                ),
                clean=False
            )

        if text:
            await manager.send_message(
                f"{text}\nType `{ctx.prefix}help` for more information.")
            await manager.clean_messages()

    # Update guild count at bot listing sites and in bots status/presence
    # async def update_status(self):
    #     await api.bot_lists.update_guild_counts(self)
    #     status = discord.Game(name=self.status_formats[self.status_index].
    #                           format(len(self.guilds)))
    #     await self.change_presence(activity=status)

    async def on_message(self, message):
        if not message.author.bot:
            ctx = await self.get_context(message)
            await self.invoke(ctx)

    async def close(self):
        await self.log_channel.send("Seraph Six is shutting down...")
        await self.destiny.close()
        await self.database.close()
        await self.the100.close()
        if self.twitter:
            await self.twitter.close()
        await super().close()
