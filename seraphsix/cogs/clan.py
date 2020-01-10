import discord
import logging
import pickle
import pydest
import pytz

from datetime import datetime
from discord.ext import commands
from peewee import DoesNotExist

from seraphsix import constants
from seraphsix.cogs.register import register
from seraphsix.cogs.utils.checks import is_clan_admin, is_valid_game_mode, clan_is_linked
from seraphsix.cogs.utils.helpers import bungie_date_as_utc
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.cogs.utils.paginator import FieldPages, EmbedPages
from seraphsix.database import Member, ClanMember, Clan, Guild
from seraphsix.errors import InvalidAdminError
from seraphsix.models.destiny import Member as DestinyMember
from seraphsix.tasks.activity import get_game_counts, execute_pydest
from seraphsix.tasks.clan import info_sync, member_sync

logging.getLogger(__name__)


class ClanCog(commands.Cog, name='Clan'):
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

        clan_db = await self.get_admin_group(ctx)
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

        clan_db = await self.get_admin_group(ctx)
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
    async def info(self, ctx, *args):
        """Show information for all connected clans"""
        await ctx.trigger_typing()
        clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)

        if not clan_dbs:
            return await ctx.send("No connected clans found")

        embeds = []
        clan_info_redis = await self.bot.redis.get(f'{ctx.guild.id}-clan-info')
        if clan_info_redis and '-nocache' not in args:
            await self.bot.redis.expire(f'{ctx.guild.id}-clan-info', constants.TIME_HOUR_MILLI)
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
                embeds.append(embed)
            await self.bot.redis.set(
                f'{ctx.guild.id}-clan-info', pickle.dumps(embeds), expire=constants.TIME_HOUR_MILLI)

        if len(embeds) > 1:
            paginator = EmbedPages(ctx, embeds)
            await paginator.paginate()
        else:
            await ctx.send(embed=embeds[0])

    @clan.command()
    @clan_is_linked()
    @commands.guild_only()
    async def roster(self, ctx, *args):
        """Show roster for all connected clans"""
        await ctx.trigger_typing()
        clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)

        if not clan_dbs:
            return await ctx.send("No connected clans found")

        members = []
        members_redis = await self.bot.redis.lrange(f'{ctx.guild.id}-clan-roster', 0, -1)
        if members_redis and '-nocache' not in args:
            await self.bot.redis.expire(f'{ctx.guild.id}-clan-roster', constants.TIME_HOUR_MILLI)
            for member in members_redis:
                members.append(pickle.loads(member))
        else:
            members_db = await self.bot.database.get_clan_members(
                [clan_db.clan_id for clan_db in clan_dbs], sorted_by='username')
            for member in members_db:
                await self.bot.redis.rpush(f'{ctx.guild.id}-clan-roster', pickle.dumps(member))
            await self.bot.redis.expire(f'{ctx.guild.id}-clan-roster', constants.TIME_HOUR_MILLI)
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
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.get_admin_group(ctx)

        try:
            members = await execute_pydest(
                self.bot.destiny.api.get_group_pending_members(
                    clan_db.clan_id,
                    access_token=member_db.bungie_access_token
                ),
                self.bot.redis
            )
        except pydest.PydestTokenException:
            tokens = await execute_pydest(
                self.bot.destiny.api.refresh_oauth_token(member_db.bungie_refresh_token),
                self.bot.redis
            )

            if 'error' in tokens:
                logging.warning(f"{tokens['error_description']} Registration is needed.")
                user_info = await register(
                    ctx, manager, "Your registration token has expired and re-registration is needed.")
                if not user_info:
                    return await manager.clean_messages()
                tokens = {token: user_info.get(token) for token in ['access_token', 'refresh_token']}

            members = await execute_pydest(
                self.bot.destiny.api.get_group_pending_members(
                    clan_db.clan_id,
                    access_token=tokens['access_token']
                ),
                self.bot.redis
            )
            member_db.bungie_access_token = tokens['access_token']
            member_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(member_db)

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

        await ctx.send(embed=embed)

    @clan.command()
    @is_clan_admin()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def approve(self, ctx, *args):
        """Approve a pending member (Admin only, requires registration)"""
        await ctx.trigger_typing()
        gamertag, platform_id, platform_name = (None,)*3

        if args[-1] == '-platform':
            await ctx.send(f"Platform must be specified like `-platform ['psn', 'stadia', 'steam', 'xbox']`")
            return

        if '-platform' in args:
            platform_name = args[-1].lower()
            gamertag = ' '.join(args[0:-2])
            platform_id = constants.PLATFORM_MAP.get(platform_name)
            if not platform_id:
                await ctx.send(f"Invalid platform `{platform_name}` was specified")
                return
        else:
            gamertag = ' '.join(args)

        if not gamertag:
            await ctx.send(f"Gamertag is required")
            return

        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.get_admin_group(ctx)

        if not platform_id and not clan_db.platform:
            await ctx.send("Platform was not specified and clan default platform is not set")
            return
        else:
            platform_id = clan_db.platform

        try:
            player = await execute_pydest(
                self.bot.destiny.api.search_destiny_player(platform_id, gamertag),
                self.bot.redis,
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
            res = await execute_pydest(
                self.bot.destiny.api.group_approve_pending_member(
                    group_id=clan_db.clan_id,
                    membership_type=platform_id,
                    membership_id=membership_id,
                    message=f"Welcome to {clan_db.name}!",
                    access_token=member_db.bungie_access_token
                ),
                self.bot.redis
            )
        except pydest.PydestTokenException:
            tokens = await execute_pydest(
                self.bot.destiny.api.refresh_oauth_token(member_db.bungie_refresh_token),
                self.bot.redis
            )
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
    @is_clan_admin()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def invited(self, ctx):
        """Show a list of invited members (Admin only, requires registration)"""
        await ctx.trigger_typing()
        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.get_admin_group(ctx)

        try:
            members = await execute_pydest(
                self.bot.destiny.api.get_group_invited_members(
                    clan_db.clan_id,
                    access_token=member_db.bungie_access_token
                ),
                self.bot.redis
            )
        except pydest.PydestTokenException:
            tokens = await execute_pydest(
                self.bot.destiny.api.refresh_oauth_token(member_db.bungie_refresh_token),
                self.bot.redis
            )
            members = await execute_pydest(
                self.bot.destiny.api.get_group_invited_members(
                    clan_db.clan_id,
                    access_token=tokens['access_token']
                ),
                self.bot.redis
            )
            member_db.bungie_access_token = tokens['access_token']
            member_db.bungie_refresh_token = tokens['refresh_token']
            await self.bot.database.update(member_db)

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

        await ctx.send(embed=embed)

    @clan.command()
    @is_clan_admin()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def invite(self, ctx, *args):
        """Invite a member by gamertag (Admin only, requires registration)"""
        await ctx.trigger_typing()
        gamertag, platform_id, platform_name = (None,)*3

        if args[-1] == '--platform':
            await ctx.send(f"Platform must be specified like `--platform ['psn', 'stadia', 'steam', 'xbox']`")
            return

        if '--platform' in args:
            platform_name = args[-1].lower()
            gamertag = ' '.join(args[0:-2])
            platform_id = constants.PLATFORM_MAP.get(platform_name)
            if not platform_id:
                await ctx.send(f"Invalid platform `{platform_name}` was specified")
                return
        else:
            gamertag = ' '.join(args)

        if not gamertag:
            await ctx.send(f"Gamertag is required")
            return

        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.get_admin_group(ctx)

        if not platform_id and not clan_db.platform:
            await ctx.send("Platform was not specified and clan default platform is not set")
            return
        else:
            platform_id = clan_db.platform

        try:
            player = await execute_pydest(
                self.bot.destiny.api.search_destiny_player(platform_id, gamertag),
                self.bot.redis
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
            res = await execute_pydest(
                self.bot.destiny.api.group_invite_member(
                    group_id=clan_db.clan_id,
                    membership_type=platform_id,
                    membership_id=membership_id,
                    message=f"Join my clan {clan_db.name}!",
                    access_token=member_db.bungie_access_token
                ),
                self.bot.redis
            )
        except pydest.PydestTokenException:
            tokens = await execute_pydest(
                self.bot.destiny.api.refresh_oauth_token(member_db.bungie_refresh_token),
                self.bot.redis
            )
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
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx):
        """Sync member list with Bungie (Admin only)"""
        await ctx.trigger_typing()
        member_changes = await member_sync(self.bot.database, self.bot.destiny, self.bot.redis, ctx.guild.id)
        clan_info_changes = await info_sync(self.bot.database, self.bot.destiny, self.bot.redis, ctx.guild.id)

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
                    value="-"
                )

            if added:
                if len(added) > 10:
                    members_value = f"Too many to list: {len(added)} total"
                else:
                    members_value = ", ".join(added)
                embed.add_field(
                    name="Members Added",
                    value=members_value,
                    inline=False
                )

            if removed:
                if len(removed) >= 10:
                    members_value = f"Too many to list: {len(removed)} total"
                else:
                    members_value = ", ".join(removed)
                embed.add_field(
                    name="Members Removed",
                    value=members_value,
                    inline=False
                )

            if changed:
                embed.add_field(
                    name="Members Changed",
                    value=", ".join(changed),
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
            await ctx.send(embed=embeds[0])

    @clan.command(
        usage=f"<{', '.join(constants.SUPPORTED_GAME_MODES.keys())}>"
    )
    @clan_is_linked()
    @is_valid_game_mode()
    @commands.guild_only()
    async def games(self, ctx, game_mode: str):
        """Show totals of all eligible clan games for all members"""
        await ctx.trigger_typing()
        logging.info(f"Finding all {game_mode} games for all members")

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
        await ctx.send(embed=embed)

    @clan.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def activitytracking(self, ctx):
        """Enable activity tracking on all connected clans (Admin only)"""
        await ctx.trigger_typing()
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
            await manager.send_message(message)

        return await manager.clean_messages()

    async def get_all_members(self, group_id):
        group = await execute_pydest(self.bot.destiny.api.get_group_members(group_id), self.bot.redis)
        group_members = group['Response']['results']
        for member in group_members:
            yield DestinyMember(member)


def setup(bot):
    bot.add_cog(ClanCog(bot))
