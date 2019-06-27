import discord
import logging
import pytz

from datetime import datetime
from discord.ext import commands
from discord.ext.commands.errors import BadArgument
from peewee import DoesNotExist
from urllib.parse import quote

from seraphsix import constants
from seraphsix.cogs.utils.checks import is_valid_game_mode, clan_is_linked, is_registered
from seraphsix.cogs.utils.helpers import get_timezone_name
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.tasks.activity import get_game_counts

from seraphsix.database import Member, ClanMember, Clan, Guild

logging.getLogger(__name__)


class MemberCog(commands.Cog, name='Member'):

    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    async def member(self, ctx):
        """Member Specific Commands"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @member.command(help="Get member information")
    @clan_is_linked()
    @commands.guild_only()
    async def info(self, ctx, *args):
        """Show member information"""
        await ctx.trigger_typing()
        member_name = ' '.join(args)

        if not member_name:
            member_name = ctx.message.author

        try:
            member_discord = await commands.MemberConverter().convert(ctx, str(member_name))
        except Exception:
            return

        try:
            member_db = await self.bot.database.get(
                Member.select(Member, ClanMember).join(ClanMember).join(Clan).join(Guild).where(
                    Guild.guild_id == ctx.guild.id,
                    Member.discord_id == member_discord.id
                )
            )
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
            colour=constants.BLUE,
            title=f"Member Info for {member_discord.display_name}"
        )
        embed.add_field(name="Xbox Gamertag", value=member_db.xbox_username)
        embed.add_field(name="PSN Username", value=member_db.psn_username)
        embed.add_field(name="Blizzard Username", value=member_db.blizzard_username)
        embed.add_field(name="Discord Username",
                        value=f"{member_discord.name}#{member_discord.discriminator}")
        embed.add_field(name="Bungie Username", value=bungie_link)
        embed.add_field(name="The100 Username", value=the100_link)
        embed.add_field(
            name="Join Date", value=member_db.clanmember.join_date.strftime('%Y-%m-%d %H:%M:%S'))
        embed.add_field(name="Time Zone", value=timezone)

        await ctx.send(embed=embed)

    @member.command(help="Link member to discord account")
    @commands.has_permissions(administrator=True)
    async def link(self, ctx):
        """Link Discord user to Gamertag (Admin)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        msg = await manager.send_message(
            "What is the gamertag/username to link to?", clean=False)
        res = await manager.get_next_message()
        gamertag = res.content
        await msg.delete()
        await res.delete()

        msg = await manager.send_message(
            "What is the discord user to link to?", clean=False)
        res = await manager.get_next_message()
        discord_user = res.content
        await msg.delete()
        await res.delete()
        try:
            member_discord = await commands.MemberConverter().convert(ctx, discord_user)
        except BadArgument:
            await manager.send_message(f"Discord user \"{discord_user}\" not found")
            return await manager.clean_messages()

        msg = await manager.send_message_react(
            "What is the user game platform? One of: `blizzard`, `psn`, `xbox`",
            reactions=[constants.EMOJI_PC, constants.EMOJI_PSN, constants.EMOJI_XBOX],
            clean=False)
        res = await manager.get_next_message()
        platform = res.content
        await msg.delete()
        await res.delete()
        try:
            platform_id = constants.PLATFORM_MAP[platform]
        except KeyError:
            await manager.send_message(f"Invalid platform `{platform}` was specified")
            return await manager.clean_messages()

        try:
            member_db = await self.bot.database.get_member_by_platform_username(platform_id, gamertag)
        except DoesNotExist:
            await manager.send_message(f"Gamertag/username \"{gamertag}\" does not match a valid member")
            return
        if member_db.discord_id:
            member_discord = await commands.MemberConverter().convert(ctx, str(member_db.discord_id))
            await manager.send_message((
                f"Gamertag/username \"{gamertag}\" already linked to "
                f"Discord user \"{member_discord.display_name}\""))
            return await manager.clean_messages()

        member_db.discord_id = member_discord.id
        try:
            await self.bot.database.update(member_db)
        except Exception:
            message = (
                f"Could not link gamertag/username \"{gamertag}\" to "
                f"Discord user \"{member_discord.display_name}\" (id:{member_discord.id}")
            logging.exception(message)
            await manager.send_message(message)
            return await manager.clean_messages()
        await manager.send_message((
            f"Linked gamertag/username \"{gamertag}\" to "
            f"Discord user \"{member_discord.display_name}\""))
        return await manager.clean_messages()

    @member.command(
        help=f"""
Show itemized list of all eligible clan games participated in
Eligiblity is simply whether the fireteam is at least half clan members.

Supported game modes: {', '.join(constants.SUPPORTED_GAME_MODES.keys())}

Example: ?member games raid
""")
    @is_valid_game_mode()
    async def games(self, ctx, *, command: str):
        """
        Show itemized list of all eligible clan games participated in
        Eligiblity is simply whether the fireteam is at least half clan members.
        """
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        command = command.split()
        game_mode = command[0]
        member_name = ' '.join(command[1:])

        if not member_name:
            discord_id = ctx.author.id
            member_name = ctx.author.display_name
            try:
                member_db = await self.bot.database.get_member_by_discord_id(discord_id)
            except DoesNotExist:
                await ctx.send(
                    f"User {ctx.author.display_name} has not registered or is not a clan member")
                return
            logging.info(
                f"Getting {game_mode} games for {ctx.author.display_name}")
        else:
            try:
                member_db = await self.bot.database.get_member_by_naive_username(member_name)
            except DoesNotExist:
                await ctx.send(f"Invalid member name {member_name}")
                return
            logging.info(
                f"Getting {game_mode} games by Gamertag {member_name} for {ctx.author.display_name}")

        game_counts = await get_game_counts(
            self.bot.database, self.bot.destiny, game_mode, member_db=member_db)

        embed = discord.Embed(
            colour=constants.BLUE,
            title=f"Eligible {game_mode.title().replace('Pvp', 'PvP')} Games for {member_name}"
        )

        total_count = 0
        if len(game_counts) == 1:
            total_count, = game_counts.values()
        else:
            for game, count in game_counts.items():
                embed.add_field(name=game.title(), value=str(count))
                total_count += count

        embed.description = str(total_count)
        await manager.send_embed(embed)

    @is_registered()
    @member.command(help="Set member timezone")
    async def settimezone(self, ctx):
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        member_db = await self.bot.database.get(Member, discord_id=ctx.author.id)
        if member_db.timezone:
            res = await manager.send_message_react(
                message_text=(
                    f"Your current timezone is set to `{member_db.timezone}`,"
                    f"would you like to change it?"),
                reactions=[constants.EMOJI_CHECKMARK, constants.EMOJI_CROSSMARK],
                clean=False,
                with_cancel=True
            )

            if res == constants.EMOJI_CROSSMARK:
                await manager.send_message("Canceling post")
                return await manager.clean_messages()

        res = await manager.send_and_get_response(
            "Enter your timezone name and country code, accepted formats are:\n"
            "```EST US\nAmerica/New_York US\n0500 US```")
        if res.lower() == 'cancel':
            await manager.send_message("Canceling")
            return await manager.clean_messages()

        timezone, country_code = res.split(' ')
        timezones = get_timezone_name(timezone, country_code)

        if not timezones:
            await manager.send_message(f"No timezone found for `{res}`, canceling")
            return await manager.clean_messages()

        if len(timezones) == 1:
            timezone = next(iter(timezones))

            res = await manager.send_message_react(
                message_text=f"Is the timezone `{timezone}` correct?",
                reactions=[constants.EMOJI_CHECKMARK, constants.EMOJI_CROSSMARK],
                clean=False,
                with_cancel=True
            )

            if res == constants.EMOJI_CROSSMARK:
                await manager.send_message("Canceling post")
                return await manager.clean_messages()

            member_db.timezone = timezone
            await self.bot.database.update(member_db)
            await manager.send_message("Timezone updated successfully!")
            return await manager.clean_messages()

        text = '\n'.join(sorted(timezones, key=lambda s: s.lower()))
        res = await manager.send_and_get_response(f"Which of these timezones is correct?\n```{text}```")
        if res.lower() == 'cancel':
            await manager.send_message("Canceling")

        if res in timezones:
            member_db.timezone = res
            await self.bot.database.update(member_db)
            await manager.send_message("Timezone updated successfully!")
        else:
            await manager.send_message("Unexpected response, canceling")
        return await manager.clean_messages()


def setup(bot):
    bot.add_cog(MemberCog(bot))
