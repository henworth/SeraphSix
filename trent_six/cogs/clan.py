import discord
import logging
import pydest

from datetime import datetime
from discord.ext import commands
from discord.errors import HTTPException
from peewee import DoesNotExist

from trent_six.cogs.utils import constants as util_constants
from trent_six.cogs.utils.checks import is_valid_game_mode, is_registered, clan_is_linked
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
                await self.bot.database.update_member(member_db)

        embed = discord.Embed(
            colour=util_constants.BLUE,
            title=f"Pending Clan Members"
        )

        if len(members['Response']['results']) == 0:
            embed.description = "None"
        else:
            for member in members['Response']['results']:
                bungie_name = member['destinyUserInfo']['displayName']
                bungie_member_id = member['destinyUserInfo']['membershipId']
                bungie_member_type = member['destinyUserInfo']['membershipType']
                bungie_url = f"https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id}"
                bungie_link = f"[{bungie_name}]({bungie_url})"
                date_applied = member['resolveDate']
                embed.add_field(name=bungie_link, value=date_applied)

        await ctx.send(embed=embed)

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
                await self.bot.database.update_member(member_db)

        embed = discord.Embed(
            colour=util_constants.BLUE,
            title=f"Invited Clan Members"
        )

        if len(members['Response']['results']) == 0:
            embed.description = "None"
        else:
            for member in members['Response']['results']:
                bungie_name = member['destinyUserInfo']['displayName']
                bungie_member_id = member['destinyUserInfo']['membershipId']
                bungie_member_type = member['destinyUserInfo']['membershipType']
                bungie_url = f"https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id}"
                bungie_link = f"[{bungie_name}]({bungie_url})"
                date_applied = member['resolveDate']
                embed.add_field(name=bungie_link, value=date_applied)

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
                await self.bot.destiny.api.group_invite_member(
                    group_id=clan_db.clan_id,
                    membership_type=destiny_constants.PLATFORM_XBOX,
                    membership_id=membership_id,
                    access_token=member_db.bungie_access_token
                )
            except pydest.PydestTokenException:
                tokens = await self.bot.destiny.api.refresh_oauth_token(
                    member_db.bungie_refresh_token
                )
                await self.bot.destiny.api.group_invite_member(
                    group_id=clan_db.clan_id,
                    membership_type=destiny_constants.PLATFORM_XBOX,
                    membership_id=membership_id,
                    access_token=tokens['access_token']
                )
                member_db.bungie_access_token = tokens['access_token']
                member_db.bungie_refresh_token = tokens['refresh_token']
                await self.bot.database.update_member(member_db)

        await ctx.send(f"Invited \"{gamertag}\" to clan. NOT REALLY, THIS IS A TEST")

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
            for member in await self.bot.database.get_members():
                db_members[member.xbox_id] = member

            db_member_set = set(
                [member for member in db_members.keys()]
            )

            new_members = bungie_member_set - db_member_set
            purged_members = db_member_set - bungie_member_set

            for member_xbox_id in new_members:
                try:
                    member_db = await self.bot.database.get_member_by_xbox_id(member_xbox_id)
                except DoesNotExist:
                    member_db = await self.bot.database.create_member(bungie_members[member_xbox_id])

                if not member_db.is_active:
                    try:
                        member_db.is_active = True
                        member_db.join_date = bungie_members[member_xbox_id]['join_date']
                        await self.bot.database.update_member(member_db)
                    except Exception:
                        logging.exception(
                            f"Could update member \"{member_db.xbox_username}\"")
                        return

            for member in purged_members:
                member_db = db_members[member]
                member_db.is_active = False
                await self.bot.database.update_member(member_db)

            members = [member.xbox_username for member in await self.bot.database.get_members()]
            self.bot.cache.put('members', members)

        embed = discord.Embed(
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
        async with ctx.typing():
            logging.info(f"Finding all {game_mode} games for all members")

            games = {}
            game_counts = await get_all_history(
                self.bot.database, self.bot.destiny, game_mode)

            total_count = 0
            for game, count in game_counts.items():
                if game in games.keys():
                    games[game] += count
                else:
                    games[game] = count

            embed = discord.Embed(
                colour=util_constants.BLUE,
                title=f"Eligible {game_mode.title().replace('Pvp', 'PvP')} Games for All Members"
            )

            total_count = 0
            for game, count in games.items():
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
