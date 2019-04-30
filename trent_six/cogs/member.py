import discord
import logging
import pytz

from datetime import datetime
from discord.errors import HTTPException
from discord.ext import commands
from discord.ext.commands.errors import BadArgument, CheckFailure
from peewee import DoesNotExist
from urllib.parse import quote

from trent_six.bot import TrentSix
from trent_six.destiny.constants import SUPPORTED_GAME_MODES
from trent_six.destiny.activity import get_member_history, store_member_history, get_all_history
from trent_six.destiny.member import get_all
from trent_six.errors import InvalidGameModeError

logging.getLogger(__name__)


def is_valid_game_mode():
    def predicate(ctx):
        game_mode = ctx.message.content.split()[-1]
        if game_mode in SUPPORTED_GAME_MODES.keys():
            return True
        raise InvalidGameModeError(game_mode, SUPPORTED_GAME_MODES.keys())
    return commands.check(predicate)


class MemberCog(commands.Cog, name='Member'):

    def __init__(self, bot):
        self.bot = bot

    @commands.group(brief="Member Commands")
    async def member(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send(f"Invalid command `{ctx.message.content}`")

    @member.command(help="Show member information")
    async def info(self, ctx, *args):
        member_name = ' '.join(args)

        if not member_name:
            member_name = ctx.message.author

        try:
            member_discord = await commands.MemberConverter().convert(ctx, str(member_name))
        except Exception:
            return

        async with ctx.typing():
            try:
                member_db = await self.bot.database.get_member_by_discord(member_discord.id)
            except DoesNotExist:
                await ctx.send(f"Discord username \"{member_name}\" does not match a valid member")
                return
            member_discord = await commands.MemberConverter().convert(ctx, str(member_discord.id))

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
            title=f"Member Info for {member_discord.display_name}"
        )
        embed.add_field(name="Xbox Gamertag", value=member_db.xbox_username)
        embed.add_field(name="Discord Username", value=f"{member_discord.name}#{member_discord.discriminator}")
        embed.add_field(name="Bungie Username", value=bungie_link)
        embed.add_field(name="The100 Username", value=the100_link)
        embed.add_field(name="Join Date", value=member_db.join_date.strftime('%Y-%m-%d %H:%M:%S'))
        embed.add_field(name="Time Zone", value=timezone)

        await ctx.send(embed=embed)

    @member.command(help="Link Discord user to Xbox Gamertag")
    async def link(self, ctx, *, xbox_username: str):
        try:
            member_discord = await commands.MemberConverter().convert(ctx, str(ctx.message.author))
        except Exception:
            return

        async with ctx.typing():
            xbox_username = xbox_username.replace('"', '')
            try:
                member_db = await self.bot.database.get_member(xbox_username)
            except DoesNotExist:
                await ctx.send(f"Gamertag \"{xbox_username}\" does not match a valid member")
                return
            if member_db.discord_id:
                member_discord = await commands.MemberConverter().convert(ctx, str(member_db.discord_id))
                await ctx.send(f"Gamertag \"{xbox_username}\" already linked to Discord user \"{member_discord.display_name}\"")
                return

            member_db.discord_id = member_discord.id
            try:
                await self.bot.database.update_member(member_db)
            except Exception:
                logging.exception(f"Could not link member \"{xbox_username}\" to Discord user \"{member_discord.display_name}\" (id:{member_discord.id}")
                return
            await ctx.send(f"Linked Gamertag \"{xbox_username}\" to Discord user \"{member_discord.display_name}\"")

    @member.command(help="Link other Discord user to Xbox Gamertag (Admin)")
    @commands.has_permissions(administrator=True)
    async def link_other(self, ctx, xbox_username: str, discord_username: str):
        try:
            member_discord = await commands.MemberConverter().convert(ctx, discord_username)
        except BadArgument:
            await ctx.send(f"Discord user \"{discord_username}\" not found")
            return

        async with ctx.typing():
            try:
                member_db = await self.bot.database.get_member(xbox_username)
            except DoesNotExist:
                await ctx.send(f"Gamertag \"{xbox_username}\" does not match a valid member")
                return
            if member_db.discord_id:
                member_discord = await commands.MemberConverter().convert(ctx, str(member_db.discord_id))
                await ctx.send(f"Gamertag \"{xbox_username}\" already linked to Discord user \"{member_discord.display_name}\"")
                return

            member_db.discord_id = member_discord.id
            try:
                await self.bot.database.update_member(member_db)
            except Exception:
                logging.exception(f"Could not link member \"{xbox_username}\" to Discord user \"{member_discord.display_name}\" (id:{member_discord.id}")
                return
            await ctx.send(f"Linked Gamertag \"{xbox_username}\" to Discord user \"{member_discord.display_name}\"")

    @member.command(help="Sync member list with Bungie (Admin)")
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx):
        async with ctx.typing():
            bungie_members = {}
            async for member in member.get_all(self.bot.destiny, self.bot.config['bungie_group_id']): # pylint: disable=not-an-iterable
                bungie_members[member.bungie_id] = member

            bungie_member_set = set(
                [member for member in bungie_members.keys()]
            )

            db_members = {}
            for member in await self.bot.database.get_members():
                db_members[member.bungie_id] = member

            db_member_set = set(
                [member for member in db_members.keys()]
            )

            new_members = bungie_member_set - db_member_set
            purged_members = db_member_set - bungie_member_set

            for member_bungie_id in new_members:
                try:
                    member_db = await self.bot.database.get_member_by_bungie(member_bungie_id)
                except DoesNotExist:
                    await self.bot.database.create_member(bungie_members[member_bungie_id].__dict__)

                if not member_db.is_active:
                    try:
                        member_db.is_active = True
                        member_db.join_date = bungie_members[member_bungie_id].join_date
                        await self.bot.database.update_member(member_db)
                    except Exception:
                        logging.exception(f"Could update member \"{member_db.xbox_username}\"")
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
            for bungie_id in new_members:
                member_db = await self.bot.database.get_member_by_bungie(bungie_id)
                new_member_usernames.append(member_db.xbox_username)
            added = sorted(new_member_usernames, key=lambda s: s.lower())
            embed.add_field(name="Members Added", value=', '.join(added), inline=False)
            logging.info(f"Added members {added}")

        if len(purged_members) > 0:
            purged_member_usernames = []
            for bungie_id in purged_members:
                member_db = await self.bot.database.get_member_by_bungie(bungie_id)
                purged_member_usernames.append(member_db.xbox_username)
            purged = sorted(purged_member_usernames, key=lambda s: s.lower())
            embed.add_field(name="Members Purged", value=', '.join(purged), inline=False)
            logging.info(f"Purged members {purged}")

        if len(purged_members) == 0 and len(new_members) == 0:
            embed.description = "None"

        try:
            await ctx.send(embed=embed)
        except HTTPException:
            embed.clear_fields()
            embed.add_field(name="Members Added", value=len(new_members), inline=False)
            embed.add_field(name="Members Purged", value=len(purged_members), inline=False)
            await ctx.send(embed=embed)

    @member.command(
        usage=f"<{', '.join(SUPPORTED_GAME_MODES.keys())}>",
        help=f"""
Show itemized list of all eligible clan games participated in
Eligiblity is simply whether the fireteam is at least half clan members.

Supported game modes: {', '.join(SUPPORTED_GAME_MODES.keys())}

Example: ?member games raid
""" )
    @is_valid_game_mode()
    async def games(self, ctx, *, command: str):
        command = command.split()
        game_mode = command[0]
        member_name = ' '.join(command[1:])

        async with ctx.typing():
            if not member_name:
                discord_id = ctx.author.id
                try:
                    member_db = await self.bot.database.get_member_by_discord(discord_id)
                except DoesNotExist:
                    await ctx.send(f"User {ctx.author.display_name} has not been linked a Gamertag or is not a clan member")
                    return
                logging.info(f"Getting {game_mode} games by Discord id {discord_id} for {ctx.author.display_name}")
            else:
                try:
                    member_db = await self.bot.database.get_member(member_name)
                except DoesNotExist:
                    await ctx.send(f"Invalid member name {member_name}")
                    return
                logging.info(f"Getting {game_mode} games by Gamertag {member_name} for {ctx.author.display_name}")

            game_counts = await get_member_history(
                self.bot.database, self.bot.destiny, member_db.xbox_username, game_mode)

        embed = discord.Embed(
            title=f"Eligible {game_mode.title().replace('Pvp', 'PvP')} Games for {member_db.xbox_username}",
        )

        total_count = 0
        if len(game_counts) == 1:
            total_count, = game_counts.values()
        else:
            for game, count in game_counts.items():
                embed.add_field(name=game.title(), value=str(count))
                total_count += count

        embed.description=str(total_count)

        await ctx.send(embed=embed)

    @member.command(
        help="Show totals of all eligible clan games for all members",
        usage=f"<{', '.join(SUPPORTED_GAME_MODES.keys())}>"
    )
    @is_valid_game_mode()
    async def games_all(self, ctx, game_mode: str):
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
                title=f"Eligible {game_mode.title().replace('Pvp', 'PvP')} Games for All Members",
            )

            total_count = 0
            for game, count in games.items():
                embed.add_field(name=game.title(), value=str(count))
                total_count += count

            embed.description=str(total_count)
            await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(MemberCog(bot))
