import discord

from discord.ext import commands
from peewee import DoesNotExist
from trent_six.destiny.constants import SUPPORTED_GAME_MODES
from trent_six.errors import (ConfigurationError, InvalidCommandError,
                              InvalidGameModeError, InvalidMemberError, NotRegisteredError)


def is_event(message):
    """Check if a message contains event data"""
    if len(message.embeds) > 0:
        embed = message.embeds[0]
        return (message.channel.name == 'upcoming-events'
                and embed.fields
                and embed.fields[0]
                and embed.fields[1]
                and embed.fields[2]
                and embed.fields[0].name == "Time"
                and embed.fields[1].name.startswith("Accepted")
                and embed.fields[2].name.startswith("Declined"))


def is_int(x):
    try:
        a = float(x)
        b = int(a)
    except ValueError:
        return False
    else:
        return a == b


def is_private_channel(channel):
    if isinstance(channel, discord.abc.PrivateChannel):
        return True


def is_message(message):
    return True


def is_valid_game_mode():
    def predicate(ctx):
        try:
            game_mode = ctx.message.content.split()[2]
        except IndexError:
            raise InvalidCommandError(
                f"Missing game mode, supported are `{', '.join(SUPPORTED_GAME_MODES.keys())}`")
        if game_mode in SUPPORTED_GAME_MODES.keys():
            return True
        raise InvalidGameModeError(game_mode, SUPPORTED_GAME_MODES.keys())
    return commands.check(predicate)


def is_clan_member():
    async def predicate(ctx):
        try:
            clan_db = await ctx.bot.database.get_clan_by_guild(ctx.message.guild.id)
        except DoesNotExist:
            raise ConfigurationError((
                f"Server **{ctx.message.guild.name}** has not been linked to "
                f"a Bungie clan, please run `?server clanlink` first"))
        try:
            await ctx.bot.database.get_clan_member_by_discord_id(ctx.author.id, clan_db.id)
        except DoesNotExist:
            raise InvalidMemberError
        return True
    return commands.check(predicate)


def is_registered():
    async def predicate(ctx):
        try:
            member_db = await ctx.bot.database.get_member_by_discord_id(ctx.author.id)
        except DoesNotExist:
            raise NotRegisteredError(ctx.prefix)
        if not member_db.bungie_access_token:
            raise NotRegisteredError(ctx.prefix)
        return True
    return commands.check(predicate)


def twitter_enabled():
    def predicate(ctx):
        if hasattr(ctx.bot, 'twitter'):
            return True
        raise ConfigurationError(
            "Twitter support is not enabled at the bot level")
    return commands.check(predicate)


def clan_is_linked():
    async def predicate(ctx):
        try:
            await ctx.bot.database.get_clan_by_guild(ctx.guild.id)
        except DoesNotExist:
            raise ConfigurationError((
                f"Server **{ctx.message.guild.name}** has not been linked to "
                f"a Bungie clan, please run `?server clanlink` first"))
        return True
    return commands.check(predicate)
