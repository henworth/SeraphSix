import discord
import logging
import pytz

from datetime import datetime
from discord.ext import commands
from discord.ext.commands.errors import BadArgument
from peewee import DoesNotExist
from urllib.parse import quote

from trent_six.cogs.utils import constants as util_constants
from trent_six.cogs.utils.checks import is_valid_game_mode, clan_is_linked
from trent_six.destiny.activity import get_member_history
from trent_six.destiny.constants import SUPPORTED_GAME_MODES

logging.getLogger(__name__)


class MemberCog(commands.Cog, name='Member'):

    def __init__(self, bot):
        self.bot = bot

    @commands.group(brief="Member Commands")
    async def member(self, ctx):
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @clan_is_linked()
    @commands.guild_only()
    @member.command(help="Show member information")
    async def info(self, ctx, *args):
        await ctx.trigger_typing()
        member_name = ' '.join(args)

        if not member_name:
            member_name = ctx.message.author

        try:
            member_discord = await commands.MemberConverter().convert(ctx, str(member_name))
        except Exception:
            return

        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)

        try:
            member_db = await self.bot.database.get_clan_member_by_discord_id(member_discord.id, clan_db.id)
        except DoesNotExist:
            await ctx.send(f"Discord username \"{member_name}\" does not match a valid member")
            return

        the100_link = None
        if member_db.the100_username:
            the100_url = f"https://www.the100.io/users/{quote(member_db.the100_username)}"
            the100_link = f"[{member_db.the100_username}]({the100_url})"

        bungie_link = None
        if member_db.bungie_id:
            bungie_info = await self.bot.destiny.api.get_membership_data_by_id(member_db.bungie_id)
            membership_info = bungie_info['Response']['destinyMemberships'][0]
            bungie_member_id = membership_info['membershipId']
            bungie_member_type = membership_info['membershipType']
            bungie_member_name = membership_info['displayName']
            bungie_url = f"https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id}"
            bungie_link = f"[{bungie_member_name}]({bungie_url})"

        timezone = None
        if member_db.timezone:
            tz = datetime.now(pytz.timezone(member_db.timezone))
            timezone = f"{tz.strftime('UTC%z')} ({tz.tzname()})"

        embed = discord.Embed(
            colour=util_constants.BLUE,
            title=f"Member Info for {member_discord.display_name}"
        )
        embed.add_field(name="Xbox Gamertag", value=member_db.xbox_username)
        embed.add_field(name="Discord Username",
                        value=f"{member_discord.name}#{member_discord.discriminator}")
        embed.add_field(name="Bungie Username", value=bungie_link)
        embed.add_field(name="The100 Username", value=the100_link)
        embed.add_field(
            name="Join Date", value=member_db.clanmember.join_date.strftime('%Y-%m-%d %H:%M:%S'))
        embed.add_field(name="Time Zone", value=timezone)

        await ctx.send(embed=embed)

    @member.command(help="Link Discord user to Xbox Gamertag")
    async def link(self, ctx, *, xbox_username: str):
        await ctx.trigger_typing()
        try:
            member_discord = await commands.MemberConverter().convert(ctx, str(ctx.message.author))
        except Exception:
            return

        xbox_username = xbox_username.replace('"', '')
        try:
            member_db = await self.bot.database.get_member_by_xbox_username(xbox_username)
        except DoesNotExist:
            await ctx.send(f"Gamertag \"{xbox_username}\" does not match a valid member")
            return
        if member_db.discord_id:
            member_discord = await commands.MemberConverter().convert(ctx, str(member_db.discord_id))
            await ctx.send((
                f"Gamertag \"{xbox_username}\" already linked to "
                f"Discord user \"{member_discord.display_name}\""))
            return

        member_db.discord_id = member_discord.id
        try:
            await self.bot.database.update_member(member_db)
        except Exception:
            logging.exception((
                f"Could not link member \"{xbox_username}\" to "
                f"Discord user \"{member_discord.display_name}\" (id:{member_discord.id}"))
            return
        await ctx.send((
            f"Linked Gamertag \"{xbox_username}\" to "
            f"Discord user \"{member_discord.display_name}\""))

    @member.command(help="Link other Discord user to Xbox Gamertag (Admin)")
    @commands.has_permissions(administrator=True)
    async def link_other(self, ctx, xbox_username: str, discord_username: str):
        await ctx.trigger_typing()
        try:
            member_discord = await commands.MemberConverter().convert(ctx, discord_username)
        except BadArgument:
            await ctx.send(f"Discord user \"{discord_username}\" not found")
            return

        try:
            member_db = await self.bot.database.get_member_by_xbox_username(xbox_username)
        except DoesNotExist:
            await ctx.send(f"Gamertag \"{xbox_username}\" does not match a valid member")
            return
        if member_db.discord_id:
            member_discord = await commands.MemberConverter().convert(ctx, str(member_db.discord_id))
            await ctx.send((
                f"Gamertag \"{xbox_username}\" already linked to "
                f"Discord user \"{member_discord.display_name}\""))
            return

        member_db.discord_id = member_discord.id
        try:
            await self.bot.database.update_member(member_db)
        except Exception:
            logging.exception((
                f"Could not link member \"{xbox_username}\" to "
                f"Discord user \"{member_discord.display_name}\" (id:{member_discord.id}"))
            return
        await ctx.send((
            f"Linked Gamertag \"{xbox_username}\" to "
            f"Discord user \"{member_discord.display_name}\""))

    @member.command(
        usage=f"<{', '.join(SUPPORTED_GAME_MODES.keys())}>",
        help=f"""
Show itemized list of all eligible clan games participated in
Eligiblity is simply whether the fireteam is at least half clan members.

Supported game modes: {', '.join(SUPPORTED_GAME_MODES.keys())}

Example: ?member games raid
""")
    @is_valid_game_mode()
    async def games(self, ctx, *, command: str):
        await ctx.trigger_typing()
        command = command.split()
        game_mode = command[0]
        member_name = ' '.join(command[1:])

        if not member_name:
            discord_id = ctx.author.id
            try:
                member_db = await self.bot.database.get_member_by_discord_id(discord_id)
            except DoesNotExist:
                await ctx.send(
                    f"User {ctx.author.display_name} has not registered or is not a clan member")
                return
            logging.info(
                f"Getting {game_mode} games by Discord id {discord_id} for {ctx.author.display_name}")
        else:
            try:
                member_db = await self.bot.database.get_member_by_xbox_username(member_name)
            except DoesNotExist:
                await ctx.send(f"Invalid member name {member_name}")
                return
            logging.info(
                f"Getting {game_mode} games by Gamertag {member_name} for {ctx.author.display_name}")

        game_counts = await get_member_history(
            self.bot.database, self.bot.destiny, member_db.xbox_username, game_mode)

        embed = discord.Embed(
            colour=util_constants.BLUE,
            title=f"Eligible {game_mode.title().replace('Pvp', 'PvP')} Games for {member_db.xbox_username}",
        )

        total_count = 0
        if len(game_counts) == 1:
            total_count, = game_counts.values()
        else:
            for game, count in game_counts.items():
                embed.add_field(name=game.title(), value=str(count))
                total_count += count

        embed.description = str(total_count)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(MemberCog(bot))
