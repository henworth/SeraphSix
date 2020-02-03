import asyncio
import discord
import logging
import pydest
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
from seraphsix.models.destiny import User as BungieUser
from seraphsix.tasks.activity import get_game_counts, get_sherpa_time_played, execute_pydest

from seraphsix.database import Member, ClanMember, Clan, Guild

log = logging.getLogger(__name__)


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
    async def info(self, ctx, *args):  # noqa TODO
        """Show member information"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        member_name = ' '.join(args)

        requestor_query = self.bot.database.get(
            Member.select(Member, ClanMember, Clan).join(ClanMember).join(Clan).join(Guild).where(
                Guild.guild_id == ctx.guild.id,
                Member.discord_id == ctx.author.id
            )
        )

        try:
            requestor_db = await asyncio.create_task(requestor_query)
        except DoesNotExist:
            requestor_db = None

        if not member_name:
            member_db = requestor_db
            member_name = ctx.author.nick
            member_discord = ctx.message.author
            discord_username = str(ctx.message.author)
        else:
            try:
                member_discord = await commands.MemberConverter().convert(ctx, str(member_name))
            except BadArgument:
                discord_username = None
            else:
                discord_username = str(member_discord)

            member_query = self.bot.database.get_member_by_naive_username(member_name)
            try:
                member_db = await asyncio.create_task(member_query)
            except DoesNotExist:
                await manager.send_message(f"Could not find username `{member_name}` in any connected clans")
                return

        the100_link = None
        if member_db.the100_username:
            the100_url = f"https://www.the100.io/users/{quote(member_db.the100_username)}"
            the100_link = f"[{member_db.the100_username}]({the100_url})"

        bungie_link = None
        if member_db.bungie_id:
            try:
                bungie_info = await execute_pydest(
                    self.bot.destiny.api.get_membership_data_by_id(member_db.bungie_id),
                    self.bot.redis
                )
            except pydest.PydestException:
                bungie_link = member_db.bungie_username
            else:
                bungie_member_data = BungieUser(bungie_info['Response'])
                bungie_member_id = bungie_member_data.memberships.bungie.id
                bungie_member_type = constants.PLATFORM_BUNGIE
                bungie_member_name = bungie_member_data.memberships.bungie.username
                bungie_url = f"https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id}"
                bungie_link = f"[{bungie_member_name}]({bungie_url})"

        timezone = None
        if member_db.timezone:
            tz = datetime.now(pytz.timezone(member_db.timezone))
            timezone = f"{tz.strftime('UTC%z')} ({tz.tzname()})"

        if member_db.discord_id:
            member_discord = await commands.MemberConverter().convert(ctx, str(member_db.discord_id))
            discord_username = str(member_discord)

        requestor_is_admin = False
        if requestor_db and requestor_db.clanmember.member_type >= constants.CLAN_MEMBER_ADMIN:
            requestor_is_admin = True

        member_is_admin = False
        if member_db.clanmember.member_type >= constants.CLAN_MEMBER_ADMIN:
            member_is_admin = True

        embed = discord.Embed(
            colour=constants.BLUE,
            title=f"Member Info for {member_name}"
        )
        embed.add_field(
            name="Clan",
            value=f"{member_db.clanmember.clan.name} [{member_db.clanmember.clan.callsign}]"
        )
        embed.add_field(
            name="Join Date",
            value=member_db.clanmember.join_date.strftime('%Y-%m-%d %H:%M:%S')
        )

        if requestor_is_admin:
            embed.add_field(
                name="Last Active Date",
                value=member_db.clanmember.last_active.strftime('%Y-%m-%d %H:%M:%S')
            )

        embed.add_field(name="Time Zone", value=timezone)
        embed.add_field(name="Xbox Gamertag", value=member_db.xbox_username)
        embed.add_field(name="PSN Username", value=member_db.psn_username)
        embed.add_field(name="Steam Username", value=member_db.steam_username)
        embed.add_field(name="Stadia Username", value=member_db.stadia_username)
        embed.add_field(name="Discord Username", value=discord_username)
        embed.add_field(name="Bungie Username", value=bungie_link)
        embed.add_field(name="The100 Username", value=the100_link)
        embed.add_field(
            name="Is Sherpa",
            value=constants.EMOJI_CHECKMARK if member_db.clanmember.is_sherpa else constants.EMOJI_CROSSMARK
        )
        embed.add_field(
            name="Is Admin",
            value=constants.EMOJI_CHECKMARK if member_is_admin else constants.EMOJI_CROSSMARK
        )
        await manager.send_embed(embed)

    @member.command(help="Link member to discord account")
    @commands.has_permissions(administrator=True)
    async def link(self, ctx):
        """Link Discord user to Gamertag (Admin)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        username = await manager.send_and_get_response(
            "What is the in-game username to link to? (enter `cancel` to cancel command)")
        if username.lower() == 'cancel':
            return await manager.send_and_clean("Canceling command")

        discord_user = await manager.send_and_get_response(
            "What is the discord user to link to? (enter `cancel` to cancel command)")
        if discord_user.lower() == 'cancel':
            return await manager.send_and_clean("Canceling command")

        try:
            member_discord = await commands.MemberConverter().convert(ctx, discord_user)
        except BadArgument:
            return await manager.send_and_clean(f"Discord user \"{discord_user}\" not found")

        react = await manager.send_message_react(
            "What is the member's game platform?",
            reactions=[constants.EMOJI_STEAM, constants.EMOJI_PSN, constants.EMOJI_XBOX],
            clean=False,
            with_cancel=True
        )

        if not react:
            return await manager.send_and_clean("Canceling command")

        platform_id = constants.PLATFORM_EMOJI_ID[react.id]

        try:
            member_db = await self.bot.database.get_member_by_platform_username(username, platform_id)
        except DoesNotExist:
            return await manager.send_and_clean(f"Username \"{username}\" does not match a valid member")

        if member_db.discord_id:
            member_discord = await commands.MemberConverter().convert(ctx, str(member_db.discord_id))
            return await manager.send_and_clean(
                f"Username \"{username}\" already linked to Discord user \"{member_discord.display_name}\"")

        member_db.discord_id = member_discord.id
        try:
            await self.bot.database.update(member_db)
        except Exception:
            message = (
                f"Could not link username \"{username}\" to Discord user \"{member_discord.display_name}\"")
            log.exception(message)
            return await manager.send_and_clean(message)

        return await manager.send_and_clean(
            f"Linked username \"{username}\" to Discord user \"{member_discord.display_name}\"")

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
                    f"User `{ctx.author.display_name}` has not registered or is not a clan member")
                return
            log.info(
                f"Getting {game_mode} games for \"{ctx.author.display_name}\"")
        else:
            try:
                member_db = await self.bot.database.get_member_by_naive_username(member_name)
            except DoesNotExist:
                await ctx.send(f"Invalid member name `{member_name}`")
                return
            log.info(
                f"Getting {game_mode} games by gamertag \"{member_name}\" for \"{ctx.author.display_name}\"")

        game_counts = await get_game_counts(self.bot.database, game_mode, member_db=member_db)

        embed = discord.Embed(
            colour=constants.BLUE,
            title=f"Eligible {game_mode.title().replace('Pvp', 'PvP').replace('Pve', 'PvE')} Games for {member_name}"
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

    @member.command(
        help=f"""
Show total time spent in activities with at least one sherpa member.

Example: ?member sherpatime
""")
    async def sherpatime(self, ctx, *args):
        """
        Show total time spent in activities with at least one sherpa member.
        """
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        member_name = ' '.join(args)

        if not member_name:
            discord_id = ctx.author.id
            member_name = ctx.author.display_name
            try:
                member_db = await self.bot.database.get_member_by_discord_id(discord_id)
            except DoesNotExist:
                return await manager.send_and_clean(
                    f"User `{ctx.author.display_name}` has not registered or is not a clan member")
            log.info(
                f"Getting sherpa time played for \"{ctx.author.display_name}\"")
        else:
            try:
                member_db = await self.bot.database.get_member_by_naive_username(member_name)
            except DoesNotExist:
                try:
                    member_discord = await commands.MemberConverter().convert(ctx, member_name)
                    member_db = await self.bot.database.get_member_by_discord_id(member_discord.id)
                except (BadArgument, DoesNotExist):                
                    return await manager.send_and_clean(f"Invalid member name `{member_name}`")
                else:
                    member_name = member_discord.display_name
            log.info(
                f"Getting sherpa time played by username \"{member_name}\" for \"{ctx.author}\"")

        time_played, sherpa_ids = await get_sherpa_time_played(self.bot.database, member_db)

        sherpa_list = []
        if time_played:
            sherpas = await self.bot.database.execute(Member.select().where(Member.id << sherpa_ids))
            for sherpa in sherpas:
                if sherpa.discord_id:
                    sherpa_discord = await commands.MemberConverter().convert(ctx, str(sherpa.discord_id))
                    sherpa_list.append(f"{sherpa_discord.name}#{sherpa_discord.discriminator}")
        else:
            time_played = 0

        embed = discord.Embed(
            colour=constants.BLUE,
            title=f"Total time played with a Sherpa by {member_name}",
            description=f"{time_played / 3600:.2f} hours"
        )

        if sherpa_list:
            embed.add_field(
                name="Sherpas Played With",
                value=', '.join(sherpa_list)
            )
        await manager.send_embed(embed)

    @is_registered()
    @member.command(help="Set member timezone")
    async def settimezone(self, ctx):
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        member_db = await self.bot.database.get(Member, discord_id=ctx.author.id)
        if member_db.timezone:
            res = await manager.send_message_react(
                f"Your current timezone is set to `{member_db.timezone}`, would you like to change it?",
                reactions=[constants.EMOJI_CHECKMARK, constants.EMOJI_CROSSMARK],
                clean=False
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
                f"Is the timezone `{timezone}` correct?",
                reactions=[constants.EMOJI_CHECKMARK, constants.EMOJI_CROSSMARK],
                clean=False
            )

            if res == constants.EMOJI_CROSSMARK:
                await manager.send_message("Canceling change")
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
