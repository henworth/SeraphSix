#!/usr/bin/env python3.7
# import ast
import asyncio
import discord
# import jsonpickle
import logging
import peony
import traceback

from discord.ext import commands, tasks
# from iron_cache import IronCache  # TODO: Replace this with Memcache
from peewee import DoesNotExist
from peony import PeonyClient
from pydest import Pydest
from the100 import The100

from seraphsix import constants
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.database import Database, Guild, TwitterChannel

from seraphsix.errors import (
    InvalidCommandError, InvalidGameModeError, InvalidMemberError,
    NotRegisteredError, ConfigurationError, MissingTimezoneError)
from seraphsix.tasks.activity import store_all_games, store_last_active

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
        self.database = Database(config['database_url'])
        self.database.initialize()

        self.destiny = Pydest(
            api_key=config['bungie']['api_key'],
            client_id=config['bungie']['client_id'],
            client_secret=config['bungie']['client_secret']
        )

        self.the100 = The100(config['the100']['api_key'], config['the100']['base_url'])

        self.twitter = None
        if (config['twitter'].get('consumer_key') and
                config['twitter'].get('consumer_secret') and
                config['twitter'].get('access_token') and
                config['twitter'].get('access_token_secret')):
            self.twitter = PeonyClient(**config['twitter'])

        for extension in STARTUP_EXTENSIONS:
            try:
                self.load_extension(extension)
            except Exception as e:
                exc = traceback.format_exception(type(e), e, e.__traceback__)
                logging.error(f"Failed to load extension {extension}: {exc}")

        self.update_last_active.start()
        self.update_member_games.start()

    @tasks.loop(minutes=5.0)
    async def update_last_active(self):
        tasks = []
        for guild in await self.database.execute(Guild.select()):
            guild_id = guild.guild_id

            logging.info(
                f"Finding last active dates for all members of {guild_id}")

            # members = ast.literal_eval(
            #     self.caches[guild_id].get('members').value)

            # tasks.extend([
            #     store_last_active(self.database, self.destiny, jsonpickle.decode(member))
            #     for member in members
            # ])

            tasks.extend([
                store_last_active(self.database, self.destiny, member)
                for member in await self.database.get_clan_members_by_guild_id(guild_id)
            ])

        await asyncio.gather(*tasks)

    @update_last_active.before_loop
    async def before_update_last_active(self):
        await self.wait_until_ready()

    # async def build_member_cache(self, guild_id: int):
    #     self.caches[guild_id] = IronCache(
    #         name=str(guild_id), **self.config['iron_cache'])

    #     members = [
    #         jsonpickle.encode(member)
    #         for member in await self.database.get_clan_members_by_guild_id(
    #             guild_id)
    #     ]

    #     self.caches[guild_id].put('members', members)
    #     logging.info(f"Populated member cache for server {guild_id}")

    @tasks.loop(hours=1.0)
    async def update_member_games(self):
        tasks = []
        for guild in await self.database.execute(Guild.select()):
            for game_mode in constants.SUPPORTED_GAME_MODES.keys():
                if '-' not in game_mode:
                    tasks.append(store_all_games(self.database, self.destiny, game_mode, guild.guild_id))
        await asyncio.gather(*tasks)

    @update_member_games.before_loop
    async def before_update_member_games(self):
        await self.wait_until_ready()

    async def process_tweet(self, tweet):
        # pylint: disable=assignment-from-no-return
        query = TwitterChannel.select().where(
            TwitterChannel.twitter_id == tweet.user.id
        )
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

    # async def on_connect(self):
    #     self.caches = {}
    #     guilds = await self.database.execute(Guild.select())
    #     tasks = [self.build_member_cache(guild.guild_id) for guild in guilds]
    #     await asyncio.gather(*tasks)

    async def on_ready(self):
        start_message = (
            f"Logged in as {self.user.name} ({self.user.id}) "
            f"{discord.utils.oauth_url(self.user.id)}"
        )
        logging.info(start_message)

        if self.twitter:
            logging.info("Starting Twitter stream tracking")
            self.loop.create_task(self.track_tweets())

    async def on_command_error(self, ctx, error):
        manager = MessageManager(ctx)

        text = None
        if isinstance(error, commands.MissingPermissions):
            text = "Sorry, but you do not have permissions to do that!"
        elif isinstance(error, (
            ConfigurationError, InvalidCommandError, InvalidMemberError,
            InvalidGameModeError, NotRegisteredError, MissingTimezoneError
        )):
            text = error
        elif isinstance(error, commands.CommandNotFound):
            text = f"Invalid command `{ctx.message.content}`."
        elif isinstance(error, commands.MissingRequiredArgument):
            text = f"Required argument `{error.param}` is missing."
        else:
            error_trace = traceback.format_exception(
                type(error), error, error.__traceback__)
            logging.error(
                f"Ignoring exception in command \"{ctx.command}\": {error_trace}")

        if text:
            await manager.send_message(
                f"{text}\nType `{ctx.prefix}help` for more information.")
            await manager.clean_messages()

    async def on_message(self, message):
        if not message.author.bot:
            ctx = await self.get_context(message)
            await self.invoke(ctx)

    async def close(self):
        await self.destiny.close()
        await self.database.close()
        await self.the100.close()
        if self.twitter:
            await self.twitter.close()
        await super().close()
