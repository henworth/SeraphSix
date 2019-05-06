#!/usr/bin/env python3.7
import ast
import asyncio
import discord
import json
import logging
import os
import peony
import pytz
import traceback

from datetime import datetime
from discord.ext import commands
from iron_cache import IronCache
from peewee import DoesNotExist

from trent_six.destiny.activity import store_member_history
from trent_six.destiny.constants import SUPPORTED_GAME_MODES
from trent_six.errors import InvalidGameModeError, NotRegisteredError, ConfigurationError

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
        guild = await bot.database.get_guild(message.guild.id)
        if guild:
            base.append(guild.prefix)
        else:
            bot.db.add_guild(message.guild.id)
            base.append('?')
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
        self.cache = IronCache(name='bot', **self.config['iron_cache'])
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

    async def store_all_games(self, game_mode: str):
        await self.wait_until_ready()
        while not self.is_closed():
            logging.info(
                f"background: Finding all {game_mode} games for all members")
            members = ast.literal_eval(self.cache.get('members').value)
            for member in members:
                count = await store_member_history(self.cache, self.database, self.destiny, member, game_mode)
                logging.info(
                    f"background: Found {count} {game_mode} games for {member}")
            logging.info(
                f"background: Found all {game_mode} games for all members")
            await asyncio.sleep(3600)

    async def track_tweets(self):
        await self.wait_until_ready()

        statuses = self.twitter.stream.statuses.filter.post(
            follow=[self.TWITTER_XBOX_SUPPORT, self.TWITTER_DTG])

        dtg_channel = None
        xbox_channel = None

        try:
            xbox_channel_id = await self.database.get_twitter_channel(self.TWITTER_XBOX_SUPPORT)
        except DoesNotExist:
            pass
        else:
            xbox_channel = self.get_channel(xbox_channel_id.channel_id)

        try:
            dtg_channel_id = await self.database.get_twitter_channel(self.TWITTER_DTG)
        except DoesNotExist:
            pass
        else:
            dtg_channel = self.get_channel(dtg_channel_id.channel_id)

        async with statuses as stream:
            async for tweet in stream:
                if peony.events.tweet(tweet):
                    if tweet.in_reply_to_status_id:
                        continue
                    twitter_url = f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}"
                    if tweet.user.id == self.TWITTER_XBOX_SUPPORT and xbox_channel:
                        await xbox_channel.send(twitter_url)
                    elif tweet.user.id == self.TWITTER_DTG and dtg_channel:
                        await dtg_channel.send(twitter_url)

    async def on_ready(self):
        logging.info(f"Logged in as {self.user.name} ({self.user.id})")
        logging.info(
            f"Invite: https://discordapp.com/oauth2/authorize?client_id={self.user.id}&scope=bot")
        try:
            members = self.cache.get('members')
        except Exception:
            members = [member.xbox_username for member in await self.database.get_members()]
            self.cache.put('members', members)

        if hasattr(self, 'twitter'):
            self.loop.create_task(self.track_tweets())

        for game_mode in SUPPORTED_GAME_MODES.keys():
            if '-' not in game_mode:
                self.loop.create_task(self.store_all_games(game_mode))

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            text = f"{ctx.message.author.mention}: Sorry, but you do not have permissions to do that!"
            await ctx.send(text)
        elif isinstance(error, (ConfigurationError, InvalidGameModeError, NotRegisteredError)):
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
