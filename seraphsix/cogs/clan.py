import asyncio
import discord
import logging
import pickle
import pydest
import pytz

from datetime import datetime
from discord.ext import commands
from discord.ext.commands.errors import BadArgument
from peewee import DoesNotExist

from seraphsix import constants
from seraphsix.cogs.utils.checks import is_clan_admin, is_valid_game_mode, is_registered, clan_is_linked
from seraphsix.cogs.utils.helpers import date_as_string, get_requestor
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.cogs.utils.paginator import FieldPages, EmbedPages
from seraphsix.database import Member, ClanMember, Clan, Guild, ClanMemberApplication
from seraphsix.errors import InvalidAdminError, InvalidCommandError
from seraphsix.models.destiny import (
    DestinyMembershipResponse, DestinyMemberGroupResponse, DestinyGroupResponse, DestinyGroupPendingMembersResponse
)
from seraphsix.tasks.activity import get_game_counts, get_last_active
from seraphsix.tasks.core import execute_pydest, get_primary_membership, execute_pydest_auth
from seraphsix.tasks.clan import info_sync, member_sync

log = logging.getLogger(__name__)


class ClanCog(commands.Cog, name="Clan"):
    def __init__(self, bot):
        self.bot = bot

    async def get_admin_group(self, ctx):
        try:
            return await self.bot.database.get(
                Clan.select(Clan).join(ClanMember).join(Member).switch(Clan).join(Guild).where(
                    Guild.guild_id == ctx.message.guild.id,
                    ClanMember.member_type >= constants.CLAN_MEMBER_ADMIN,
                    Member.discord_id == ctx.author.id
                )
            )
        except DoesNotExist:
            raise InvalidAdminError

    async def get_user_details(self, args):
        username, platform_id = (None,)*2

        if not args:
            raise InvalidCommandError("Username is required")

        if args[-1] == '-platform':
            raise InvalidCommandError(
                f"Platform must be specified like `-platform {list(constants.PLATFORM_EMOJI_MAP.keys())}`")

        if '-platform' in args:
            platform_name = args[-1].lower()
            username = ' '.join(args[0:-2])
            platform_id = constants.PLATFORM_MAP.get(platform_name)
            if not platform_id:
                raise InvalidCommandError(f"Invalid platform `{platform_name}` was specified")
        else:
            username = ' '.join(args)

        if not username:
            raise InvalidCommandError("Username is required")

        return username, platform_id

    async def get_member_db(self, ctx, username):
        try:
            member_discord = await commands.MemberConverter().convert(ctx, str(username))
        except BadArgument:
            member_query = self.bot.database.get_member_by_naive_username(username, include_clan=False)
        else:
            member_query = self.bot.database.get_member_by_discord_id(member_discord.id)

        try:
            member_db = await asyncio.create_task(member_query)
        except DoesNotExist:
            member_db = None

        return member_db

    async def get_bungie_details(self, username, bungie_id=None, platform_id=None):
        membership_id = None
        username_lower = username.lower()

        if bungie_id:
            try:
                player = await execute_pydest(
                    self.bot.destiny.api.get_membership_data_by_id, bungie_id,
                    return_type=DestinyMembershipResponse
                )
            except pydest.PydestException as e:
                log_message = f"Could not find Destiny player for {username}"
                log.error(f"{log_message}\n\n{e}\n\n{player}")
                raise InvalidCommandError(log_message)

            for membership in player.response.destiny_memberships:
                if membership.membership_type != constants.PLATFORM_BUNGIE:
                    membership_id = membership.membership_id
                    platform_id = membership.membership_type
                    break
        else:
            player = await execute_pydest(
                self.bot.destiny.api.search_destiny_player, platform_id, username
            )
            if not player.response:
                log_message = f"Could not find Destiny player for {username}"
                log.error(f"{log_message}\n\n{player}")
                raise InvalidCommandError(log_message)

            if len(player.response) == 1:
                membership = player.response[0]
                if membership.display_name.lower() == username_lower and membership.membership_type == platform_id:
                    membership_id = membership.membership_id
                    platform_id = membership.membership_type
                else:
                    membership_orig = membership
                    profile = await execute_pydest(
                        self.bot.destiny.api.get_membership_data_by_id, membership.membership_id,
                        return_type=DestinyMembershipResponse
                    )
                    for membership in profile.response.destiny_memberships:
                        if membership.display_name.lower() == username_lower:
                            user_matches = True
                            break
                    if user_matches:
                        membership_id = membership_orig.membership_id
                        platform_id = membership_orig.membership_type
            else:
                for membership in player.response:
                    display_name = membership.display_name.lower()
                    membership_type = membership.membership_type
                    if membership_type == platform_id and display_name == username_lower:
                        membership_id = membership.membership_id
                        platform_id = membership.membership_type
                        break
        return membership_id, platform_id

    async def create_application_embed(self, ctx, requestor_db, guild_db):
        redis_cache = self.bot.ext_conns['redis_cache']

        if requestor_db.bungie_username:
            membership_name = requestor_db.bungie_username

        platform_id, membership_id, _ = get_primary_membership(requestor_db)

        group_id = None
        group_name = None
        groups_info = await execute_pydest(
            self.bot.destiny.api.get_groups_for_member, platform_id, membership_id,
            return_type=DestinyMemberGroupResponse
        )
        if len(groups_info.response.results) > 0:
            for group in groups_info.response.results:
                if group.member.destiny_user_info.membership_id == membership_id:
                    group_id = group.group.group_id
                    group_name = group.group.name

        if group_id and group_name:
            group_url = f'https://www.bungie.net/en/ClanV2/Index?groupId={group_id}'
            group_link = f'[{group_name}]({group_url})'
        else:
            group_link = 'None'

        last_active = await get_last_active(self.bot.ext_conns, platform_id=platform_id, member_id=membership_id)

        embed = discord.Embed(
            colour=constants.BLUE,
            title=f"Clan Application for {ctx.author.nick}"
        )

        bungie_url = f"https://www.bungie.net/en/Profile/{platform_id}/{membership_id}"
        bungie_link = f"[{membership_name}]({bungie_url})"

        if requestor_db.discord_id:
            member_discord = await commands.MemberConverter().convert(ctx, str(requestor_db.discord_id))
            discord_username = str(member_discord)

        embed.add_field(name="Last Active Date", value=date_as_string(last_active))
        embed.add_field(name="Bungie Username", value=bungie_link)
        embed.add_field(name="Current Clan", value=group_link)
        embed.add_field(name="Xbox Gamertag", value=requestor_db.xbox_username)
        embed.add_field(name="PSN Username", value=requestor_db.psn_username)
        embed.add_field(name="Steam Username", value=requestor_db.steam_username)
        embed.add_field(name="Stadia Username", value=requestor_db.stadia_username)
        embed.add_field(name="Discord Username", value=discord_username)
        embed.set_footer(text="All times shown in UTC")
        embed.set_thumbnail(url=str(ctx.author.avatar_url))

        # application = msgpack.packb(embed, default=encode_datetime)
        await redis_cache.set(
            f'{ctx.guild.id}-clan-application-{requestor_db.id}', pickle.dumps(embed))
        return embed

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
        manager = MessageManager(ctx)

        if not group_id:
            return await manager.send_and_clean("Command must include the the100 group ID")

        res = await self.bot.the100.get_group(group_id)
        if res.get('error'):
            return await manager.send_and_clean(f"Could not locate the100 group {group_id}")

        group_name = res['name']
        callsign = res['clan_tag']

        clan_db = await self.get_admin_group(ctx)
        if clan_db.the100_group_id:
            return await manager.send_and_clean(
                f"**{clan_db.name} [{clan_db.callsign}]** is already linked to another the100 group.")

        clan_db.the100_group_id = res['id']
        await self.bot.database.update(clan_db)

        message = (
            f"**{clan_db.name} [{clan_db.callsign}]** "
            f"linked to **{group_name} [{callsign}]**"
        )
        return await manager.send_message(message, mention=False, clean=False)

    @the100.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def unlink(self, ctx, group_id):
        """Unlink clan from the100 group (Admin only)"""
        manager = MessageManager(ctx)

        clan_db = await self.get_admin_group(ctx)
        if not clan_db.the100_group_id:
            return await manager.send_and_clean(
                f"**{clan_db.name} [{clan_db.callsign}]** is not linked to a the100 group.")

        res = await self.bot.the100.get_group(clan_db.the100_group_id)
        if res.get('error'):
            return await manager.send_and_clean(f"Could not locate the100 group {clan_db.the100_group_id}")

        group_name = res['name']
        callsign = res['clan_tag']

        clan_db.the100_group_id = None
        await self.bot.database.update(clan_db)

        message = (
            f"**{clan_db.name} [{clan_db.callsign}]** "
            f"unlinked from **{group_name} [{callsign}]**"
        )
        return await manager.send_message(message, mention=False, clean=False)

    @clan.command()
    @clan_is_linked()
    @commands.guild_only()
    async def info(self, ctx, *args):
        """Show information for all connected clans"""
        redis_cache = self.bot.ext_conns['redis_cache']
        manager = MessageManager(ctx)

        clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)

        if not clan_dbs:
            return await manager.send_and_clean("No connected clans found", mention=False)

        embeds = []
        clan_redis_key = f'{ctx.guild.id}-clan-info'
        clan_info_redis = await redis_cache.get(clan_redis_key)
        if clan_info_redis and '-nocache' not in args:
            log.debug(f'{clan_redis_key} {clan_info_redis}')
            await redis_cache.expire(clan_redis_key, constants.TIME_HOUR_SECONDS)
            embeds = pickle.loads(clan_info_redis)
        else:
            for clan_db in clan_dbs:
                group = await execute_pydest(
                    self.bot.destiny.api.get_group, clan_db.clan_id, return_type=DestinyGroupResponse)
                if not group.response:
                    log.error(
                        f"Could not get details for clan {clan_db.name} ({clan_db.clan_id}) - "
                        f"{group.error_status} {group.error_description}"
                    )
                    return await manager.send_and_clean(f"Clan {clan_db.name} not found", mention=False)
                else:
                    group = group.response

                embed = discord.Embed(
                    colour=constants.BLUE,
                    title=group.detail.motto,
                    description=group.detail.about
                )
                embed.set_author(
                    name=f"{group.detail.name} [{group.detail.clan_info.clan_callsign}]",
                    url=f"https://www.bungie.net/en/ClanV2?groupid={clan_db.clan_id}"
                )
                embed.add_field(
                    name="Members",
                    value=group.detail.member_count,
                    inline=True
                )
                embed.add_field(
                    name="Founder",
                    value=group.founder.bungie_net_user_info.display_name,
                    inline=True
                )
                embed.add_field(
                    name="Founded",
                    value=date_as_string(group.detail.creation_date),
                    inline=True
                )
                embeds.append(embed)
            await redis_cache.set(clan_redis_key, pickle.dumps(embeds), expire=constants.TIME_HOUR_SECONDS)

        if len(embeds) > 1:
            paginator = EmbedPages(ctx, embeds)
            await paginator.paginate()
        else:
            await manager.send_embed(embeds[0])

    @clan.command()
    @clan_is_linked()
    @commands.guild_only()
    async def roster(self, ctx, *args):
        """Show roster for all connected clans"""
        manager = MessageManager(ctx)

        clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)

        if not clan_dbs:
            return await manager.send_and_clean("No connected clans found")

        members = []
        members_redis = await self.bot.ext_conns['redis_cache'].lrange(f"{ctx.guild.id}-clan-roster", 0, -1)
        if members_redis and '-nocache' not in args:
            await self.bot.ext_conns['redis_cache'].expire(f"{ctx.guild.id}-clan-roster", constants.TIME_HOUR_SECONDS)
            for member in members_redis:
                members.append(pickle.loads(member))
        else:
            members_db = await self.bot.database.get_clan_members(
                [clan_db.clan_id for clan_db in clan_dbs], sorted_by='username')
            for member in members_db:
                await self.bot.ext_conns['redis_cache'].rpush(f"{ctx.guild.id}-clan-roster", pickle.dumps(member))
            await self.bot.ext_conns['redis_cache'].expire(f"{ctx.guild.id}-clan-roster", constants.TIME_HOUR_SECONDS)
            members = members_db

        entries = []
        for member in members:
            timezone = "Not Set"
            if member.timezone:
                tz = datetime.now(pytz.timezone(member.timezone))
                timezone = f"{tz.strftime('UTC%z')} ({tz.tzname()})"
            member_info = (
                member.username,
                f"Clan: {member.clanmember.clan.name} [{member.clanmember.clan.callsign}]\n"
                f"Join Date: {date_as_string(member.clanmember.join_date)}\n"
                f"Timezone: {timezone}"
            )
            entries.append(member_info)

        p = FieldPages(
            ctx, entries=entries,
            per_page=5,
            title="Roster for All Connected Clans",
            color=constants.BLUE
        )
        await p.paginate()

    @clan.command()
    @is_clan_admin()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def pending(self, ctx):
        """Show a list of pending members (Admin only, requires registration)"""
        manager = MessageManager(ctx)

        admin_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.get_admin_group(ctx)

        members = await execute_pydest_auth(
            self.bot.ext_conns,
            self.bot.destiny.api.get_group_pending_members,
            admin_db,
            manager,
            group_id=clan_db.clan_id,
            access_token=admin_db.bungie_access_token,
            return_type=DestinyGroupPendingMembersResponse
        )

        embed = discord.Embed(
            colour=constants.BLUE,
            title=f"Pending Clan Members in {clan_db.name}"
        )

        if len(members.response.results) == 0:
            embed.description = "None"
        else:
            for member in members.response.results:
                bungie_name = member.destiny_user_info.display_name
                bungie_member_id = member.destiny_user_info.membership_id
                bungie_member_type = member.destiny_user_info.membership_type
                date_applied = date_as_string(member.creation_date, with_tz=True)
                bungie_url = f"https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id}"
                member_info = f"Date Applied: {date_applied}\nProfile: {bungie_url}"
                embed.add_field(name=bungie_name, value=member_info)

        await manager.send_embed(embed)

    @clan.command(
        help="""
Admin only, requires registration

Approve a pending clan member based on either their Discord info or in-game username.

To approve based on Discord info, the user must be registered. Once that is done,
the command takes any Discord user info (username, nickname, id, etc.)

For in-game username if the server default platform is not set, the `-platform`
argument is required.

Examples:
?clan approve username
?clan approve username -platform xbox
""")
    @is_clan_admin()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def approve(self, ctx, *args):
        """Approve a pending member (Admin only, requires registration)"""
        manager = MessageManager(ctx)
        username, platform_id = await self.get_user_details(args)

        member_db = await self.get_member_db(ctx, username)
        admin_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.get_admin_group(ctx)

        if clan_db.platform:
            platform_id = clan_db.platform
        elif not platform_id:
            raise InvalidCommandError("Platform was not specified and clan default platform is not set")

        bungie_id = None
        if member_db:
            bungie_id = member_db.bungie_id

        membership_id, platform_id = await self.get_bungie_details(username, bungie_id, platform_id)

        res = await execute_pydest_auth(
            self.bot.ext_conns,
            self.bot.destiny.api.group_approve_pending_member,
            admin_db,
            manager,
            group_id=clan_db.clan_id,
            membership_type=platform_id,
            membership_id=membership_id,
            message=f"Welcome to {clan_db.name}!",
            access_token=admin_db.bungie_access_token
        )

        if res.error_status != 'Success':
            message = f"Could not approve **{username}**"
            log.info(f"Could not approve '{username}': {res}")
        else:
            message = f"Approved **{username}** as a member of clan **{clan_db.name}**"

        return await manager.send_message(message, mention=False, clean=False)

    @clan.command()
    @is_clan_admin()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def invited(self, ctx):
        """Show a list of invited members (Admin only, requires registration)"""
        manager = MessageManager(ctx)

        admin_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.get_admin_group(ctx)

        members = await execute_pydest_auth(
            self.bot.ext_conns,
            self.bot.destiny.api.get_group_invited_members,
            admin_db,
            manager,
            group_id=clan_db.clan_id,
            access_token=admin_db.bungie_access_token,
            return_type=DestinyGroupPendingMembersResponse
        )

        embed = discord.Embed(
            colour=constants.BLUE,
            title=f"Invited Clan Members in {clan_db.name}"
        )

        if len(members.response.results) == 0:
            embed.description = "None"
        else:
            for member in members.response.results:
                bungie_name = member.destiny_user_info.display_name
                bungie_member_id = member.destiny_user_info.membership_id
                bungie_member_type = member.destiny_user_info.membership_type
                date_invited = date_as_string(member.creation_date, with_tz=True)
                bungie_url = f"https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id}"
                member_info = f"Date Invited: {date_invited}\nProfile: {bungie_url}"
                embed.add_field(name=bungie_name, value=member_info)

        await manager.send_embed(embed)

    @clan.command(
        help="""
Admin only, requires registration

Invite a user to clan based on either their Discord info or in-game username.

To invite based on Discord info, the user must be registered. Once that is done,
the command takes any Discord user info (username, nickname, id, etc.)

For in-game username if the server default platform is not set, the `-platform`
argument is required.

Examples:
?clan invite username
?clan invite username -platform xbox
""")
    @is_clan_admin()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def invite(self, ctx, *args):
        """Invite a member by username (Admin only, requires registration)"""
        manager = MessageManager(ctx)
        username, platform_id = await self.get_user_details(args)

        member_db = await self.get_member_db(ctx, username)
        admin_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.get_admin_group(ctx)

        if not platform_id and clan_db.platform:
            platform_id = clan_db.platform
        else:
            raise InvalidCommandError("Platform was not specified and clan default platform is not set")

        bungie_id = None
        if member_db:
            bungie_id = member_db.bungie_id

        membership_id, platform_id = await self.get_bungie_details(username, bungie_id, platform_id)

        res = await execute_pydest_auth(
            self.bot.ext_conns,
            self.bot.destiny.api.group_invite_member,
            admin_db,
            manager,
            group_id=clan_db.clan_id,
            membership_type=platform_id,
            membership_id=membership_id,
            message=f"Join my clan {clan_db.name}!",
            access_token=admin_db.bungie_access_token
        )

        if res.error_status == 'ClanTargetDisallowsInvites':
            message = f"User **{username}** has disabled clan invites"
        elif res.error_status != 'Success':
            message = f"Could not invite **{username}**"
            log.info(f"Could not invite '{username}': {res}")
        else:
            message = f"Invited **{username}** to clan **{clan_db.name}**"

        return await manager.send_message(message, mention=False, clean=False)

    @clan.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx):
        """Sync member list with Destiny (Admin only)"""
        manager = MessageManager(ctx)

        member_changes = await member_sync(self.bot.ext_conns, ctx.guild.id, str(ctx.guild))
        clan_info_changes = await info_sync(self.bot.ext_conns, ctx.guild.id)

        clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)
        embeds = []
        for clan_db in clan_dbs:
            embed = discord.Embed(
                colour=constants.BLUE,
                title=f"Clan Changes for {clan_db.name}",
            )

            added, removed, changed = [
                member_changes[clan_db.clan_id][k] for k in ['added', 'removed', 'changed']]

            if not added and not removed and not changed \
                    and not clan_info_changes.get(clan_db.clan_id):
                embed.add_field(
                    name="No Changes",
                    value='-'
                )

            if added:
                if len(added) > 10:
                    members_value = f"Too many to list: {len(added)} total"
                else:
                    members_value = ', '.join(added)
                embed.add_field(
                    name="Members Added",
                    value=members_value,
                    inline=False
                )

            if removed:
                if len(removed) >= 10:
                    members_value = f"Too many to list: {len(removed)} total"
                else:
                    members_value = ', '.join(removed)
                embed.add_field(
                    name="Members Removed",
                    value=members_value,
                    inline=False
                )

            if changed:
                embed.add_field(
                    name="Members Changed",
                    value=', '.join(changed),
                    inline=False
                )

            if clan_info_changes.get(clan_db.clan_id):
                changes = clan_info_changes[clan_db.clan_id]
                if changes.get('name'):
                    embed.add_field(
                        name="Name Changed",
                        value=f"From **{changes['name']['from']}** to **{changes['name']['to']}**",
                        inline=False
                    )
                if changes.get('callsign'):
                    embed.add_field(
                        name="Callsign Changed",
                        value=f"From **{changes['callsign']['from']}** to **{changes['callsign']['to']}**",
                        inline=False
                    )
            embeds.append(embed)

        if len(embeds) > 1:
            paginator = EmbedPages(ctx, embeds)
            await paginator.paginate()
        else:
            return await manager.send_embed(embeds[0])

    @clan.command()
    @is_registered()
    @clan_is_linked()
    @commands.guild_only()
    async def apply(self, ctx):
        """Apply to be a member of the linked clan"""
        manager = MessageManager(ctx)
        requestor_db = await get_requestor(ctx)
        guild_db = await self.bot.ext_conns['database'].get(Guild, guild_id=ctx.guild.id)

        try:
            clan_app_db = await self.bot.ext_conns['database'].get(
                ClanMemberApplication, guild_id=guild_db.id, member_id=requestor_db.id
            )
        except DoesNotExist:
            embed = await self.create_application_embed(ctx, requestor_db, guild_db)
            application_embed = await manager.send_embed(embed, channel_id=guild_db.admin_channel)

            data = {
                'guild': guild_db.id,
                'member': requestor_db.id,
                'message_id': application_embed.id,
                'approved': False
            }
            await self.bot.ext_conns['database'].create(ClanMemberApplication, **data)

            await manager.send_and_clean("Your application has been submitted for admin approval.")
        else:
            if not clan_app_db.approved:
                message = "Your application is still pending for admin approval."
            else:
                message = "Your application has been approved!"
            return await manager.send_and_clean(message)

    @clan.command()
    @is_clan_admin()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def applied(self, ctx):
        redis_cache = self.bot.ext_conns['redis_cache']
        manager = MessageManager(ctx)

        admin_channel = self.bot.get_channel(self.bot.guild_map[ctx.guild.id].admin_channel)

        cursor = b'0'
        while cursor:
            cursor, keys = await redis_cache.scan(cursor, match=f'{ctx.guild.id}-clan-application-*')

        if len(keys) > 0:
            for key in keys:
                embed_packed = await redis_cache.get(key)
                member_db_id = key.decode('utf-8').split('-')[-1]
                query = ClanMemberApplication.select().join(Member).where(
                    Member.id == member_db_id
                )
                application_db = await self.bot.ext_conns['database'].get(query)
                previous_message_id = application_db.message_id

                previous_message = await admin_channel.fetch_message(previous_message_id)
                await previous_message.delete()

                new_message = await manager.send_embed(pickle.loads(embed_packed))
                application_db.message_id = new_message.id
                await self.bot.ext_conns['database'].update(application_db)
        else:
            await manager.send_and_clean("No applications found.")

    @clan.command(
        usage=f"<{', '.join(constants.SUPPORTED_GAME_MODES.keys())}>"
    )
    @clan_is_linked()
    @is_valid_game_mode()
    @commands.guild_only()
    async def games(self, ctx, game_mode: str):
        """Show totals of all eligible clan games for all members"""
        manager = MessageManager(ctx)

        log.info(f"Finding all {game_mode} games for all members")

        game_counts = await get_game_counts(self.bot.database, game_mode)

        embed = discord.Embed(
            colour=constants.BLUE,
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
        await manager.send_embed(embed)

    @clan.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def activitytracking(self, ctx):
        """Enable activity tracking on all connected clans (Admin only)"""
        manager = MessageManager(ctx)

        clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)
        for clan_db in clan_dbs:
            if clan_db.activity_tracking:
                clan_db.activity_tracking = False
            else:
                clan_db.activity_tracking = True
            await self.bot.database.update(clan_db)
            message = (
                f"Clan activity tracking has been "
                f"{'enabled' if clan_db.activity_tracking else 'disabled'} "
                f"for **{clan_db.name}**."
            )
            await manager.send_message(message, mention=False, clean=False)

        return await manager.clean_messages()


def setup(bot):
    bot.add_cog(ClanCog(bot))
