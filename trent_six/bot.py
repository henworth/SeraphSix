#!/usr/bin/env python3.7
import ast
import asyncio
import discord
import jsonpickle
import logging
import peony
import traceback

from discord.ext import commands
from iron_cache import IronCache
from peewee import DoesNotExist

from trent_six.destiny.activity import store_member_history, store_last_active
from trent_six.errors import (
    InvalidCommandError, InvalidGameModeError,
    NotRegisteredError, ConfigurationError)

logging.getLogger(__name__)

STARTUP_EXTENSIONS = [
    'trent_six.cogs.clan', 'trent_six.cogs.member',
    'trent_six.cogs.register', 'trent_six.cogs.server'
]


async def _prefix_callable(bot, message):
    """Get current command prefix"""
    base = [f'<@{bot.user.id}> ']
    if isinstance(message.channel, discord.abc.PrivateChannel):
        base.append('?')
    else:
        try:
            guild = await bot.database.get_guild(message.guild.id)
        except DoesNotExist:
            await bot.database.create_guild(message.guild.id)
            base.append('?')
        else:
            base.append(guild.prefix)
    return base


class TrentSix(commands.Bot):

    TWITTER_DTG = 2608131020
    TWITTER_XBOX_SUPPORT = 59804598

    def __init__(self, loop, config, database, destiny, twitter=None):
        super().__init__(
            command_prefix=_prefix_callable, loop=loop, case_insensitive=True,
            help_command=commands.DefaultHelpCommand(
                no_category="Assorted", dm_help=True, verify_checks=False)
        )

        self.config = config
        self.database = database
        self.destiny = destiny

        if twitter:
            self.twitter = twitter

        for extension in STARTUP_EXTENSIONS:
            try:
                self.load_extension(extension)
            except Exception as e:
                exc = traceback.format_exception(type(e), e, e.__traceback__)
                logging.error(f"Failed to load extension {extension}: {exc}")

    async def store_all_games(self, game_mode: str, guild_id: int):
        await self.wait_until_ready()
        while not self.is_closed():
            logging.info(
                f"background: Finding all {game_mode} games for all members")
            members = ast.literal_eval(self.caches[str(guild_id)].get('members').value)
            for member in members:
                member_db = jsonpickle.decode(member)
                count = await store_member_history(members, self.database, self.destiny, member_db, game_mode)
                logging.info(
                    f"background: Found {count} {game_mode} games for {member_db.xbox_username}")
            logging.info(
                f"background: Found all {game_mode} games for all members")
            await asyncio.sleep(3600)

    async def update_last_active(self, guild_id):
        await self.wait_until_ready()
        while not self.is_closed():
            logging.info(f"Finding last active dates for all members of {guild_id}")
            members = ast.literal_eval(
                self.caches[str(guild_id)].get('members').value)

            for member in members:
                member_db = jsonpickle.decode(member)
                await store_last_active(self.database, self.destiny, member_db)

            await asyncio.sleep(300)

    async def track_tweets(self):
        await self.wait_until_ready()

        statuses = self.twitter.stream.statuses.filter.post(
            follow=[self.TWITTER_XBOX_SUPPORT, self.TWITTER_DTG])

        dtg_channels = None
        xbox_channels = None

        try:
            xbox_channels= await self.database.get_twitter_channels(self.TWITTER_XBOX_SUPPORT)
        except DoesNotExist:
            pass

        try:
            dtg_channels = await self.database.get_twitter_channels(self.TWITTER_DTG)
        except DoesNotExist:
            pass

        async with statuses as stream:
            async for tweet in stream:
                if peony.events.tweet(tweet):
                    if tweet.in_reply_to_status_id:
                        continue

                    twitter_url = f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}"
                    if tweet.user.id == self.TWITTER_XBOX_SUPPORT and xbox_channels:
                        for xbox_channel in xbox_channels:
                            logging.info(
                                f"Sending tweet {tweet.id} by {tweet.user.screen_name} to {xbox_channel.channel_id}")
                            channel = self.get_channel(xbox_channel.channel_id)
                            await channel.send(twitter_url)
                    elif tweet.user.id == self.TWITTER_DTG and dtg_channels:
                        for dtg_channel in dtg_channels:
                            logging.info(
                                f"Sending tweet {tweet.id} by {tweet.user.screen_name} to {dtg_channel.channel_id}")
                            channel = self.get_channel(dtg_channel.channel_id)
                            await channel.send(twitter_url)

    async def build_member_cache(self, guild_id: int):
        await self.wait_until_ready()
        self.caches[str(guild_id)] = IronCache(
            name=guild_id, **self.config['iron_cache'])
        members = [
            jsonpickle.encode(member)
            for member in await self.database.get_clan_members_by_guild_id(
                guild_id)
        ]
        self.caches[str(guild_id)].put('members', members)
        logging.info(f"Populated member cache for server {guild_id}")

    async def on_ready(self):
        start_message = (
            f"Logged in as {self.user.name} ({self.user.id}) "
            f"https://discordapp.com/oauth2/authorize?"
            f"client_id={self.user.id}&scope=bot"
        )
        logging.info(start_message)

        self.caches = {}
        guilds = await self.database.get_guilds()
        for guild in guilds:
            guild_id = str(guild.guild_id)

            self.caches[guild_id] = IronCache(
                name=guild_id, **self.config['iron_cache'])

            await self.build_member_cache(guild_id)
            self.loop.create_task(self.update_last_active(guild_id))

            for game_mode in SUPPORTED_GAME_MODES.keys():
                if '-' not in game_mode:
                    self.loop.create_task(
                        self.store_all_games(game_mode, guild_id))

        if hasattr(self, 'twitter'):
            logging.info("Starting Twitter stream tracking")
            self.loop.create_task(self.track_tweets())

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            text = f"{ctx.message.author.mention}: Sorry, but you do not have permissions to do that!"
            await ctx.send(text)
        elif isinstance(error, (ConfigurationError, InvalidCommandError, InvalidGameModeError, NotRegisteredError)):
            await ctx.send(error.message)
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send(f"Invalid command `{ctx.message.content}`")
        else:
            error_trace = traceback.format_exception(
                type(error), error, error.__traceback__)
            logging.error(
                f"Ignoring exception in command \"{ctx.command}\": {error_trace}")

    async def on_message(self, message):
        if not message.author.bot:
            ctx = await self.get_context(message)
            await self.invoke(ctx)
