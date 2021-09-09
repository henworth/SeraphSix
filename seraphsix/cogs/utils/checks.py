import discord

from discord.ext import commands
from tortoise.exceptions import DoesNotExist

from seraphsix.constants import SUPPORTED_GAME_MODES, CLAN_MEMBER_ADMIN
from seraphsix.errors import (
    ConfigurationError,
    InvalidAdminError,
    InvalidCommandError,
    InvalidGameModeError,
    InvalidMemberError,
    NotRegisteredError,
    MissingTimezoneError,
)
from seraphsix.models.database import Member, ClanMember


def is_event(message):
    """Check if a message contains event data"""
    if len(message.embeds) > 0:
        embed = message.embeds[0]
        return (
            message.channel.name == "upcoming-events"
            and embed.fields
            and embed.fields[0]
            and embed.fields[1]
            and embed.fields[2]
            and embed.fields[0].name == "Time"
            and embed.fields[1].name.startswith("Accepted")
            and embed.fields[2].name.startswith("Declined")
        )


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
                f"Missing game mode, supported are `{', '.join(SUPPORTED_GAME_MODES.keys())}`"
            )
        if game_mode in SUPPORTED_GAME_MODES.keys():
            return True
        raise InvalidGameModeError(game_mode, SUPPORTED_GAME_MODES.keys())

    return commands.check(predicate)


async def check_registered(ctx):
    member_db = await Member.get_or_none(discord_id=ctx.author.id)
    if not member_db or not member_db.bungie_access_token:
        raise NotRegisteredError(ctx.prefix)
    return True


async def check_clan_linked(ctx):
    try:
        await ctx.bot.database.get_clans_by_guild(ctx.guild.id)
    except DoesNotExist:
        raise ConfigurationError(
            (
                f"Server **{ctx.message.guild.name}** has not been linked to "
                f"a Destiny clan, please run `{ctx.prefix}server clanlink` first"
            )
        )
    return True


async def check_clan_member(ctx):
    try:
        await ClanMember.get(
            clan__guild__guild_id=ctx.message.guild.id, member__discord_id=ctx.author.id
        )
    except DoesNotExist:
        raise InvalidMemberError
    return True


async def check_timezone(ctx):
    member_db = await Member.get_or_none(discord_id=ctx.author.id)
    if not member_db:
        raise NotRegisteredError
    if not member_db.timezone:
        raise MissingTimezoneError
    return True


def is_registered():
    async def predicate(ctx):
        return await check_registered(ctx)

    return commands.check(predicate)


def member_has_timezone():
    async def predicate(ctx):
        return await check_timezone(ctx)

    return commands.check(predicate)


def clan_is_linked():
    async def predicate(ctx):
        return await check_clan_linked(ctx)

    return commands.check(predicate)


def is_clan_member():
    async def predicate(ctx):
        await check_clan_linked(ctx)
        await check_clan_member(ctx)

    return commands.check(predicate)


def is_clan_admin():
    async def predicate(ctx):
        await check_registered(ctx)
        await check_clan_linked(ctx)
        await check_clan_member(ctx)
        try:
            await ClanMember.get(
                clan__guild__guild_id=ctx.message.guild.id,
                member_type__gte=CLAN_MEMBER_ADMIN,
                member__discord_id=ctx.author.id,
            )
        except DoesNotExist:
            raise InvalidAdminError
        return True

    return commands.check(predicate)


def twitter_enabled():
    def predicate(ctx):
        if hasattr(ctx.bot, "twitter"):
            return True
        raise ConfigurationError("Twitter support is not enabled at the bot level")

    return commands.check(predicate)
