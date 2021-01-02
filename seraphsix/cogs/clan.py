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
from seraphsix.cogs.register import register
from seraphsix.cogs.utils.checks import is_clan_admin, is_valid_game_mode, clan_is_linked
from seraphsix.cogs.utils.helpers import bungie_date_as_utc
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.cogs.utils.paginator import FieldPages, EmbedPages
from seraphsix.database import Member, ClanMember, Clan, Guild
from seraphsix.errors import InvalidAdminError, InvalidCommandError
from seraphsix.tasks.activity import get_game_counts, execute_pydest
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
                    self.bot.destiny.api.get_membership_data_by_id(bungie_id),
                    self.bot.redis
                )
            except pydest.PydestException as e:
                log_message = f"Could not find Destiny player for {username}"
                log.error(f"{log_message}\n\n{e}\n\n{player}")
                raise InvalidCommandError(log_message)

            for membership in player['Response']['destinyMemberships']:
                if membership['membershipType'] != constants.PLATFORM_BUNGIE:
                    membership_id = membership['membershipId']
                    platform_id = membership['membershipType']
                    break
        else:
            try:
                player = await execute_pydest(
                    self.bot.destiny.api.search_destiny_player(platform_id, username),
                    self.bot.redis
                )
            except pydest.PydestException as e:
                log_message = f"Could not find Destiny player for {username}"
                log.error(f"{log_message}\n\n{e}\n\n{player}")
                raise InvalidCommandError(log_message)

            if len(player['Response']) == 1:
                membership = player['Response'][0]
                if membership['displayName'].lower() == username_lower:
                    membership_id = membership['membershipId']
                    platform_id = membership['membershipType']
            else:
                for membership in player['Response']:
                    display_name = membership['displayName'].lower()
                    membership_type = membership['membershipType']
                    if membership_type == platform_id and display_name == username_lower:
                        membership_id = membership['membershipId']
                        platform_id = membership['membershipType']
                        break

        return membership_id, platform_id

    async def refresh_admin_tokens(self, manager, admin_db):
        tokens = await execute_pydest(
            self.bot.destiny.api.refresh_oauth_token(admin_db.bungie_refresh_token),
            self.bot.redis
        )

        if 'error' in tokens:
            log.warning(f"{tokens['error_description']} Registration is needed")
            user_info = await register(manager, "Your registration token has expired and re-registration is needed.")
            if not user_info:
                raise InvalidCommandError("I'm not sure where you went. We can try this again later.")
            tokens = {token: user_info.get(token) for token in ['access_token', 'refresh_token']}

        return tokens

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
        manager = MessageManager(ctx)

        clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)

        if not clan_dbs:
            return await manager.send_and_clean("No connected clans found", mention=False)

        embeds = []
        clan_redis_key = f"{ctx.guild.id}-clan-info"
        clan_info_redis = await self.bot.redis.get(clan_redis_key)
        if clan_info_redis and '-nocache' not in args:
            await self.bot.redis.expire(clan_redis_key, constants.TIME_HOUR_SECONDS)
            embeds = pickle.loads(clan_info_redis)
        else:
            for clan_db in clan_dbs:
                res = await execute_pydest(self.bot.destiny.api.get_group(clan_db.clan_id), self.bot.redis)
                group = res['Response']
                embed = discord.Embed(
                    colour=constants.BLUE,
                    title=group['detail']['motto'],
                    description=group['detail']['about']
                )
                embed.set_author(
                    name=f"{group['detail']['name']} [{group['detail']['clanInfo']['clanCallsign']}]",
                    url=f"https://www.bungie.net/en/ClanV2?groupid={clan_db.clan_id}"
                )
                embed.add_field(
                    name="Members",
                    value=group['detail']['memberCount'],
                    inline=True
                )
                embed.add_field(
                    name="Founder",
                    value=group['founder']['bungieNetUserInfo']['displayName'],
                    inline=True
                )
                embed.add_field(
                    name="Founded",
                    value=datetime.strptime(
                        group['detail']['creationDate'],
                        '%Y-%m-%dT%H:%M:%S.%f%z').strftime('%Y-%m-%d %H:%M:%S %Z'),
                    inline=True
                )
                embeds.append(embed)
            await self.bot.redis.set(clan_redis_key, pickle.dumps(embeds), expire=constants.TIME_HOUR_SECONDS)

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
        members_redis = await self.bot.redis.lrange(f"{ctx.guild.id}-clan-roster", 0, -1)
        if members_redis and '-nocache' not in args:
            await self.bot.redis.expire(f"{ctx.guild.id}-clan-roster", constants.TIME_HOUR_SECONDS)
            for member in members_redis:
                members.append(pickle.loads(member))
        else:
            members_db = await self.bot.database.get_clan_members(
                [clan_db.clan_id for clan_db in clan_dbs], sorted_by='username')
            for member in members_db:
                await self.bot.redis.rpush(f"{ctx.guild.id}-clan-roster", pickle.dumps(member))
            await self.bot.redis.expire(f"{ctx.guild.id}-clan-roster", constants.TIME_HOUR_SECONDS)
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
                f"Join Date: {member.clanmember.join_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
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

        try:
            members = await execute_pydest(
                self.bot.destiny.api.get_group_pending_members(
                    clan_db.clan_id,
                    access_token=admin_db.bungie_access_token
                ),
                self.bot.redis
            )
        except pydest.PydestTokenException:
            tokens = await self.refresh_admin_tokens(manager, admin_db)
            members = await execute_pydest(
                self.bot.destiny.api.get_group_pending_members(
                    clan_db.clan_id,
                    access_token=tokens['access_token']
                ),
                self.bot.redis
            )
            admin_db.bungie_access_token = tokens['access_token']
            admin_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(admin_db)

        embed = discord.Embed(
            colour=constants.BLUE,
            title=f"Pending Clan Members in {clan_db.name}"
        )

        if len(members['Response']['results']) == 0:
            embed.description = "None"
        else:
            for member in members['Response']['results']:
                bungie_name = member['destinyUserInfo']['displayName']
                bungie_member_id = member['destinyUserInfo']['membershipId']
                bungie_member_type = member['destinyUserInfo']['membershipType']
                date_applied = bungie_date_as_utc(member['creationDate']).strftime('%Y-%m-%d %H:%M:%S %Z')
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

        res = None
        try:
            res = await execute_pydest(
                self.bot.destiny.api.group_approve_pending_member(
                    group_id=clan_db.clan_id,
                    membership_type=platform_id,
                    membership_id=membership_id,
                    message=f"Welcome to {clan_db.name}!",
                    access_token=admin_db.bungie_access_token
                ),
                self.bot.redis
            )
        except pydest.PydestTokenException:
            tokens = await self.refresh_admin_tokens(manager, admin_db)
            res = await execute_pydest(
                self.bot.destiny.api.group_approve_pending_member(
                    group_id=clan_db.clan_id,
                    membership_type=platform_id,
                    membership_id=membership_id,
                    message=f"Welcome to {clan_db.name}!",
                    access_token=tokens['access_token']
                ),
                self.bot.redis
            )
            admin_db.bungie_access_token = tokens['access_token']
            admin_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(admin_db)

        if not res:
            raise RuntimeError("Unexpected empty response from the Bungie API")

        if res['ErrorStatus'] != 'Success':
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

        try:
            members = await execute_pydest(
                self.bot.destiny.api.get_group_invited_members(
                    clan_db.clan_id,
                    access_token=admin_db.bungie_access_token
                ),
                self.bot.redis
            )
        except pydest.PydestTokenException:
            tokens = await self.refresh_admin_tokens(manager, admin_db)
            members = await execute_pydest(
                self.bot.destiny.api.get_group_invited_members(
                    clan_db.clan_id,
                    access_token=tokens['access_token']
                ),
                self.bot.redis
            )
            admin_db.bungie_access_token = tokens['access_token']
            admin_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(admin_db)

        embed = discord.Embed(
            colour=constants.BLUE,
            title=f"Invited Clan Members in {clan_db.name}"
        )

        if len(members['Response']['results']) == 0:
            embed.description = "None"
        else:
            for member in members['Response']['results']:
                bungie_name = member['destinyUserInfo']['displayName']
                bungie_member_id = member['destinyUserInfo']['membershipId']
                bungie_member_type = member['destinyUserInfo']['membershipType']
                date_applied = bungie_date_as_utc(member['creationDate']).strftime('%Y-%m-%d %H:%M:%S %Z')
                bungie_url = f"https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id}"
                member_info = f"Date Invited: {date_applied}\nProfile: {bungie_url}"
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

        res = None
        try:
            res = await execute_pydest(
                self.bot.destiny.api.group_invite_member(
                    group_id=clan_db.clan_id,
                    membership_type=platform_id,
                    membership_id=membership_id,
                    message=f"Join my clan {clan_db.name}!",
                    access_token=admin_db.bungie_access_token
                ),
                self.bot.redis
            )
        except pydest.PydestTokenException:
            tokens = await self.refresh_admin_tokens(manager, admin_db)
            res = await execute_pydest(
                self.bot.destiny.api.group_invite_member(
                    group_id=clan_db.clan_id,
                    membership_type=platform_id,
                    membership_id=membership_id,
                    message=f"Join my clan {clan_db.name}!",
                    access_token=tokens['access_token']
                ),
                self.bot.redis
            )
            admin_db.bungie_access_token = tokens['access_token']
            admin_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(admin_db)

        if not res:
            raise RuntimeError("Unexpected empty response from the Bungie API")

        if res['ErrorStatus'] == 'ClanTargetDisallowsInvites':
            message = f"User **{username}** has disabled clan invites"
        elif res['ErrorStatus'] != 'Success':
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
        """Sync member list with Bungie (Admin only)"""
        manager = MessageManager(ctx)

        member_changes = await member_sync(self.bot, ctx.guild.id)
        clan_info_changes = await info_sync(self.bot, ctx.guild.id)

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
