import discord
import logging
import jsonpickle
import pydest
import pytz

from datetime import datetime
from discord.ext import commands
from discord.errors import HTTPException
from peewee import DoesNotExist

from trent_six.cogs.utils import constants as util_constants
from trent_six.cogs.utils.checks import (
    is_clan_member, is_valid_game_mode, is_registered, clan_is_linked)
from trent_six.cogs.utils.message_manager import MessageManager

from trent_six.cogs.utils.paginator import FieldPages
from trent_six.destiny import constants as destiny_constants
from trent_six.destiny.activity import get_all_history
from trent_six.destiny.models import Member

logging.getLogger(__name__)


class ClanCog(commands.Cog, name='Clan'):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    async def clan(self, ctx):
        """Clan Specific Commands"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @clan.group(invoke_without_command=True)
    async def the100(self, ctx):
        """The100 Specific Commands"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @the100.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def link(self, ctx, group_id):
        """Link clan to the100 group (Admin only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        if not group_id:
            await manager.send_message(
                "Command must include the the100 group ID")
            return await manager.clean_messages()

        res = await self.bot.the100.get_group(group_id)
        if res.get('error'):
            await manager.send_message(
                f"Could not locate the100 group {group_id}")
            return await manager.clean_messages()

        group_name = res['name']
        callsign = res['clan_tag']

        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)
        if clan_db.the100_group_id:
            await manager.send_message(
                f"**{clan_db.name} [{clan_db.callsign}]** is already linked to another the100 group.")
            return await manager.clean_messages()

        clan_db.the100_group_id = res['id']
        await self.bot.database.update(clan_db)

        await manager.send_message((
            f"**{clan_db.name} [{clan_db.callsign}]** "
            f"linked to **{group_name} [{callsign}]**"))
        return await manager.clean_messages()

    @the100.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def unlink(self, ctx, group_id):
        """Unlink clan from the100 group (Admin only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)
        if not clan_db.the100_group_id:
            await manager.send_message(
                f"**{clan_db.name} [{clan_db.callsign}]** is not linked to a the100 group.")
            return await manager.clean_messages()

        res = await self.bot.the100.get_group(clan_db.the100_group_id)
        if res.get('error'):
            await manager.send_message(
                f"Could not locate the100 group {clan_db.the100_group_id}")
            return await manager.clean_messages()

        group_name = res['name']
        callsign = res['clan_tag']

        clan_db.the100_group_id = None
        await self.bot.database.update(clan_db)

        await manager.send_message((
            f"**{clan_db.name} [{clan_db.callsign}]** "
            f"unlinked from **{group_name} [{callsign}]**"))
        return await manager.clean_messages()

    @clan.command()
    @clan_is_linked()
    @commands.guild_only()
    async def info(self, ctx):
        """Show clan information"""
        await ctx.trigger_typing()
        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)
        res = await self.bot.destiny.api.get_group(clan_db.clan_id)

        group = res['Response']
        embed = discord.Embed(
            colour=util_constants.BLUE,
            title=group['detail']['motto'],
            description=group['detail']['about']
        )
        embed.set_author(
            name=f"{group['detail']['name']} [{group['detail']['clanInfo']['clanCallsign']}]",
            url=f"https://www.bungie.net/en/ClanV2?groupid={clan_db.clan_id}"
        )
        embed.add_field(
            name='Members',
            value=group['detail']['memberCount'],
            inline=True
        )
        embed.add_field(
            name='Founder',
            value=group['founder']['bungieNetUserInfo']['displayName'],
            inline=True
        )
        embed.add_field(
            name='Founded',
            value=datetime.strptime(
                group['detail']['creationDate'],
                '%Y-%m-%dT%H:%M:%S.%f%z').strftime('%Y-%m-%d %H:%M:%S %Z'),
            inline=True
        )
        await ctx.send(embed=embed)

    @clan.command()
    @clan_is_linked()
    @commands.guild_only()
    async def roster(self, ctx):
        """Show clan roster"""
        await ctx.trigger_typing()
        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)
        clan_members = await self.bot.database.get_clan_members(clan_db.clan_id, sorted_by='xbox_username')

        members = []
        for member in clan_members:
            timezone = "Not Set"
            if member.timezone:
                tz = datetime.now(pytz.timezone(member.timezone))
                timezone = f"{tz.strftime('UTC%z')} ({tz.tzname()})"
            members.append((
                member.xbox_username,
                f"Join Date: {member.clanmember.join_date.strftime('%Y-%m-%d %H:%M:%S')}"
                f"\nTimezone: {timezone}"
            ))

        p = FieldPages(
            ctx, entries=members,
            per_page=5,
            title=f"{clan_db.name} [{clan_db.callsign}] - Clan Roster",
            color=util_constants.BLUE
        )
        await p.paginate()

    @clan.command()
    @clan_is_linked()
    @is_clan_member()
    @is_registered()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def pending(self, ctx):
        """Show a list of pending members (Admin only, requires registration)"""
        await ctx.trigger_typing()
        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)

        try:
            members = await self.bot.destiny.api.get_group_pending_members(
                clan_db.clan_id,
                access_token=member_db.bungie_access_token
            )
        except pydest.PydestTokenException:
            tokens = await self.bot.destiny.api.refresh_oauth_token(
                member_db.bungie_refresh_token
            )
            members = await self.bot.destiny.api.get_group_pending_members(
                clan_db.clan_id,
                access_token=tokens['access_token']
            )
            member_db.bungie_access_token = tokens['access_token']
            member_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(member_db)

        embed = discord.Embed(
            colour=util_constants.BLUE,
            title=f"Pending Clan Members in {clan_db.name}"
        )

        if len(members['Response']['results']) == 0:
            embed.description = "None"
        else:
            for member in members['Response']['results']:
                bungie_name = member['destinyUserInfo']['displayName']
                bungie_member_id = member['destinyUserInfo']['membershipId']
                bungie_member_type = member['destinyUserInfo']['membershipType']
                date_applied = datetime.strptime(
                    member['creationDate'], '%Y-%m-%dT%H:%M:%S%z').strftime('%Y-%m-%d %H:%M:%S %Z')
                bungie_url = f"https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id}"
                member_info = f"Date Applied: {date_applied}\nProfile: {bungie_url}"
                embed.add_field(name=bungie_name, value=member_info)

        await ctx.send(embed=embed)

    @clan.command()
    @clan_is_linked()
    @is_clan_member()
    @is_registered()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def approve(self, ctx, *args):
        """Approve a pending member (Admin only, requires registration)"""
        await ctx.trigger_typing()
        gamertag, platform_id, platform_name = (None,)*3

        if args[-1] == '--platform':
            await ctx.send(f"Platform must be specified like `--platform ['blizzard', 'psn', 'xbox']`")
            return

        if '--platform' in args:
            platform_name = args[-1].lower()
            gamertag = ' '.join(args[0:-2])
            platform_id = destiny_constants.PLATFORM_MAP.get(platform_name)
            if not platform_id:
                await ctx.send(f"Invalid platform `{platform_name}` was specified")
                return
        else:
            gamertag = ' '.join(args)

        if not gamertag:
            await ctx.send(f"Gamertag is required")
            return

        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)

        if not platform_id and not clan_db.platform:
            await ctx.send("Platform was not specified and clan default platform is not set")
            return
        else:
            platform_id = clan_db.platform

        try:
            player = await self.bot.destiny.api.search_destiny_player(platform_id, gamertag)
        except pydest.PydestException:
            await ctx.send(f"Invalid gamertag {gamertag}")
            return

        membership_id = None
        for membership in player['Response']:
            if membership['membershipType'] == platform_id and membership['displayName'] == gamertag:
                membership_id = membership['membershipId']
                break

        if not membership_id:
            await ctx.send(f"Could not find Destiny player for gamertag {gamertag}")
            return

        try:
            res = await self.bot.destiny.api.group_approve_pending_member(
                group_id=clan_db.clan_id,
                membership_type=platform_id,
                membership_id=membership_id,
                message=f"Welcome to {clan_db.name}!",
                access_token=member_db.bungie_access_token
            )
        except pydest.PydestTokenException:
            tokens = await self.bot.destiny.api.refresh_oauth_token(
                member_db.bungie_refresh_token
            )
            res = await self.bot.destiny.api.group_approve_pending_member(
                group_id=clan_db.clan_id,
                membership_type=platform_id,
                membership_id=membership_id,
                message=f"Welcome to {clan_db.name}!",
                access_token=tokens['access_token']
            )
            member_db.bungie_access_token = tokens['access_token']
            member_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(member_db)

        if res['ErrorStatus'] != 'Success':
            message = f"Could not approve **{gamertag}**"
            logging.error(f"Could not approve \"{gamertag}\": {res}")
        else:
            message = f"Approved **{gamertag}** as a member of clan **{clan_db.name}**"

        await ctx.send(message)

    @clan.command()
    @clan_is_linked()
    @is_clan_member()
    @is_registered()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def invited(self, ctx):
        """Show a list of invited members (Admin only, requires registration)"""
        await ctx.trigger_typing()
        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)

        try:
            members = await self.bot.destiny.api.get_group_invited_members(
                clan_db.clan_id,
                access_token=member_db.bungie_access_token
            )
        except pydest.PydestTokenException:
            tokens = await self.bot.destiny.api.refresh_oauth_token(
                member_db.bungie_refresh_token
            )
            members = await self.bot.destiny.api.get_group_invited_members(
                clan_db.clan_id,
                access_token=tokens['access_token']
            )
            member_db.bungie_access_token = tokens['access_token']
            member_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(member_db)

        embed = discord.Embed(
            colour=util_constants.BLUE,
            title=f"Invited Clan Members in {clan_db.name}"
        )

        if len(members['Response']['results']) == 0:
            embed.description = "None"
        else:
            for member in members['Response']['results']:
                bungie_name = member['destinyUserInfo']['displayName']
                bungie_member_id = member['destinyUserInfo']['membershipId']
                bungie_member_type = member['destinyUserInfo']['membershipType']
                date_applied = datetime.strptime(
                    member['creationDate'], '%Y-%m-%dT%H:%M:%S%z').strftime('%Y-%m-%d %H:%M:%S %Z')
                bungie_url = f"https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id}"
                member_info = f"Date Invited: {date_applied}\nProfile: {bungie_url}"
                embed.add_field(name=bungie_name, value=member_info)

        await ctx.send(embed=embed)

    @clan.command()
    @clan_is_linked()
    @is_clan_member()
    @is_registered()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def invite(self, ctx, *args):
        """Invite a member by gamertag (Admin only, requires registration)"""
        await ctx.trigger_typing()
        gamertag, platform_id, platform_name = (None,)*3

        if args[-1] == '--platform':
            await ctx.send(f"Platform must be specified like `--platform ['blizzard', 'psn', 'xbox']`")
            return

        if '--platform' in args:
            platform_name = args[-1].lower()
            gamertag = ' '.join(args[0:-2])
            platform_id = destiny_constants.PLATFORM_MAP.get(platform_name)
            if not platform_id:
                await ctx.send(f"Invalid platform `{platform_name}` was specified")
                return
        else:
            gamertag = ' '.join(args)

        if not gamertag:
            await ctx.send(f"Gamertag is required")
            return

        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)

        if not platform_id and not clan_db.platform:
            await ctx.send("Platform was not specified and clan default platform is not set")
            return
        else:
            platform_id = clan_db.platform

        try:
            player = await self.bot.destiny.api.search_destiny_player(
                platform_id, gamertag
            )
        except pydest.PydestException:
            await ctx.send(f"Invalid gamertag {gamertag}")
            return

        membership_id = None
        for membership in player['Response']:
            if membership['membershipType'] == platform_id and membership['displayName'] == gamertag:
                membership_id = membership['membershipId']
                break

        if not membership_id:
            await ctx.send(f"Could not find Destiny player for gamertag {gamertag}")
            return

        try:
            res = await self.bot.destiny.api.group_invite_member(
                group_id=clan_db.clan_id,
                membership_type=platform_id,
                membership_id=membership_id,
                message=f"Join my clan {clan_db.name}!",
                access_token=member_db.bungie_access_token
            )
        except pydest.PydestTokenException:
            tokens = await self.bot.destiny.api.refresh_oauth_token(
                member_db.bungie_refresh_token
            )
            res = await self.bot.destiny.api.group_invite_member(
                group_id=clan_db.clan_id,
                membership_type=platform_id,
                membership_id=membership_id,
                message=f"Join my clan {clan_db.name}!",
                access_token=tokens['access_token']
            )
            member_db.bungie_access_token = tokens['access_token']
            member_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(member_db)

        if res['ErrorStatus'] == 'ClanTargetDisallowsInvites':
            message = f"User **{gamertag}** has disabled clan invites"
        else:
            message = f"Invited **{gamertag}** to clan **{clan_db.name}**"

        await ctx.send(message)

    @clan.command()
    @clan_is_linked()
    @is_clan_member()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx):
        """Sync member list with Bungie (Admin only)"""
        await ctx.trigger_typing()
        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)
        bungie_members = {}
        async for member in self.get_all_members(clan_db.clan_id):  # pylint: disable=not-an-iterable
            bungie_members[member.memberships.xbox.id] = dict(
                bungie_id=member.memberships.bungie.id,
                bungie_username=member.memberships.bungie.username,
                join_date=member.join_date,
                xbox_id=member.memberships.xbox.id,
                xbox_username=member.memberships.xbox.username
            )

        bungie_member_set = set(
            [member for member in bungie_members.keys()]
        )

        db_members = {}
        for member in await self.bot.database.get_clan_members(clan_db.clan_id):
            db_members[member.xbox_id] = member

        db_member_set = set(
            [member for member in db_members.keys()]
        )

        new_members = bungie_member_set - db_member_set
        purged_members = db_member_set - bungie_member_set
        for member_xbox_id in new_members:
            member_info = bungie_members[member_xbox_id]
            try:
                member_db = await self.bot.database.get_member_by_platform(
                    member_xbox_id, destiny_constants.PLATFORM_XBOX)
            except DoesNotExist:
                member_db = await self.bot.database.create_member(member_info)

            await self.bot.database.create_clan_member(
                member_db,
                clan_db.clan_id,
                join_date=member_info['join_date'],
                platform_id=destiny_constants.PLATFORM_XBOX,
                is_active=True
            )

        for member_xbox_id in purged_members:
            member_db = await self.bot.database.get_member_by_platform(
                member_xbox_id, destiny_constants.PLATFORM_XBOX)
            clanmember_db = await self.bot.database.get_clan_member(member_db.id)
            await self.bot.database.delete(clanmember_db)

        members = [
            jsonpickle.encode(member)
            for member in await self.bot.database.get_clan_members_by_guild_id(ctx.guild.id)
        ]
        self.bot.caches[str(ctx.guild.id)].put('members', members)

        embed = discord.Embed(
            colour=util_constants.BLUE,
            title="Membership Changes"
        )

        if len(new_members) > 0:
            new_member_usernames = []
            for xbox_id in new_members:
                member_db = await self.bot.database.get_member_by_xbox_id(xbox_id)
                new_member_usernames.append(member_db.xbox_username)
            added = sorted(new_member_usernames, key=lambda s: s.lower())
            embed.add_field(name="Members Added",
                            value=', '.join(added), inline=False)
            logging.info(f"Added members {added}")

        if len(purged_members) > 0:
            purged_member_usernames = []
            for xbox_id in purged_members:
                member_db = await self.bot.database.get_member_by_xbox_id(xbox_id)
                purged_member_usernames.append(member_db.xbox_username)
            purged = sorted(purged_member_usernames, key=lambda s: s.lower())
            embed.add_field(name="Members Purged",
                            value=', '.join(purged), inline=False)
            logging.info(f"Purged members {purged}")

        if len(purged_members) == 0 and len(new_members) == 0:
            embed.description = "None"

        try:
            await ctx.send(embed=embed)
        except HTTPException:
            embed.clear_fields()
            embed.add_field(name="Members Added",
                            value=len(new_members), inline=False)
            embed.add_field(name="Members Purged", value=len(
                purged_members), inline=False)
            await ctx.send(embed=embed)

    @clan.command(
        usage=f"<{', '.join(destiny_constants.SUPPORTED_GAME_MODES.keys())}>"
    )
    @clan_is_linked()
    @is_valid_game_mode()
    @commands.guild_only()
    async def games(self, ctx, game_mode: str):
        """Show totals of all eligible clan games for all members"""
        await ctx.trigger_typing()
        logging.info(f"Finding all {game_mode} games for all members")

        game_counts = await get_all_history(
            self.bot.database, self.bot.destiny, game_mode)

        embed = discord.Embed(
            colour=util_constants.BLUE,
            title=f"Eligible {game_mode.title().replace('Pvp', 'PvP')} Games for All Members"
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

    async def get_all_members(self, group_id):
        group = await self.bot.destiny.api.get_group_members(group_id)
        group_members = group['Response']['results']
        for member in group_members:
            yield Member(member)


def setup(bot):
    bot.add_cog(ClanCog(bot))
