import discord
import logging
import jsonpickle
import pydest

from datetime import datetime
from discord.ext import commands
from discord.errors import HTTPException
from peewee import DoesNotExist

from trent_six.cogs.utils import constants as util_constants
from trent_six.cogs.utils.checks import is_clan_member, is_valid_game_mode, is_registered, clan_is_linked
from trent_six.destiny import constants as destiny_constants
from trent_six.destiny.activity import get_all_history
from trent_six.destiny.models import User, Member

logging.getLogger(__name__)


class ClanCog(commands.Cog, name='Clan'):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    async def clan(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send(f"Invalid command `{ctx.message.content}`")

    @clan.command()
    @clan_is_linked()
    @commands.guild_only()
    async def info(self, ctx):
        async with ctx.typing():
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
                    group['detail']['creationDate'], '%Y-%m-%dT%H:%M:%S.%f%z').strftime('%Y-%m-%d %H:%M:%S %Z'),
                inline=True
            )
        await ctx.send(embed=embed)

    @clan.command()
    @clan_is_linked()
    @is_clan_member()
    @is_registered()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def pending(self, ctx):
        async with ctx.typing():
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
        await ctx.trigger_typing()
        gamertag = ' '.join(args)

        if not gamertag:
            await ctx.send(f"Gamertag is required")
            return

        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)

        try:
            player = await self.bot.destiny.api.search_destiny_player(
                destiny_constants.PLATFORM_XBOX, gamertag
            )
        except pydest.PydestException:
            await ctx.send(f"Invalid gamertag {gamertag}")
            return

        membership_id = None
        for membership in player['Response']:
            if membership['membershipType'] == destiny_constants.PLATFORM_XBOX and membership['displayName'] == gamertag:
                membership_id = membership['membershipId']
                break

        if not membership_id:
            await ctx.send(f"Could not find Destiny player for gamertag {gamertag}")
            return

        try:
            res = await self.bot.destiny.api.group_approve_pending_member(
                group_id=clan_db.clan_id,
                membership_type=destiny_constants.PLATFORM_XBOX,
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
                membership_type=destiny_constants.PLATFORM_XBOX,
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
        async with ctx.typing():
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
    async def invite(self, ctx, gamertag):
        async with ctx.typing():
            member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
            clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)

            try:
                player = await self.bot.destiny.api.search_destiny_player(
                    destiny_constants.PLATFORM_XBOX, gamertag
                )
            except pydest.PydestException:
                await ctx.send(f"Invalid gamertag {gamertag}")
                return

            membership_id = None
            for membership in player['Response']:
                if membership['membershipType'] == destiny_constants.PLATFORM_XBOX and membership['displayName'] == gamertag:
                    membership_id = membership['membershipId']
                    break

            if not membership_id:
                await ctx.send(f"Could not find Destiny player for gamertag {gamertag}")
                return

            try:
                res = await self.bot.destiny.api.group_invite_member(
                    group_id=clan_db.clan_id,
                    membership_type=destiny_constants.PLATFORM_XBOX,
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
                    membership_type=destiny_constants.PLATFORM_XBOX,
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

    @clan.command(help="Sync member list with Bungie")
    @clan_is_linked()
    @is_clan_member()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx):
        async with ctx.typing():
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
                    join_date = member_info['join_date']
                    member_db = await self.bot.database.create_member(member_info)
                    await self.bot.database.create_clan_member(
                        member_db,
                        clan_db.clan_id,
                        join_date=join_date,
                        platform_id=destiny_constants.PLATFORM_XBOX,
                        is_active=True
                    )

                if not member_db.is_active:
                    try:
                        member_db.is_active = True
                        member_db.join_date = member_info['join_date']
                        await self.bot.database.update(member_db)
                    except Exception:
                        logging.exception(
                            f"Could update member \"{member_db.xbox_username}\"")
                        return

            for member in purged_members:
                member_db = db_members[member]
                member_db.is_active = False
                await self.bot.database.update(member_db)

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
        help="Show totals of all eligible clan games for all members",
        usage=f"<{', '.join(destiny_constants.SUPPORTED_GAME_MODES.keys())}>"
    )
    @clan_is_linked()
    @is_valid_game_mode()
    @commands.guild_only()
    async def games(self, ctx, game_mode: str):
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
