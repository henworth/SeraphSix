import discord
import logging
import pytz
import json

from datetime import datetime
from discord.ext import commands
from peewee import DoesNotExist
from trent_six.cogs.utils import constants as util_constants
from trent_six.cogs.utils.checks import clan_is_linked
from trent_six.cogs.utils.message_manager import MessageManager

logging.getLogger(__name__)


class GameCog(commands.Cog, name='Clan'):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(help="Game Specific Commands")
    async def game(self, ctx):
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @game.command(help="List games")
    @clan_is_linked()
    @commands.guild_only()
    async def list(self, ctx):
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)
        games = await self.bot.the100.get_group_gaming_sessions(clan_db.the100_group_id)

        if not games:
            await manager.send_message(
                "No the100 game sessions found")
            return await manager.clean_messages()

        for game in games:
            logging.info(json.dumps(game))
            spots_reserved = game['party_size'] - 1
            start_time = datetime.fromisoformat(
                game['start_time']).astimezone(tz=pytz.utc)

            embed = discord.Embed(
                color=util_constants.BLUE,
            )
            embed.set_thumbnail(
                url=(
                    'https://www.the100.io/assets/the-100-logo-'
                    '01d3884b844d4308fcf20f19281cc758f7b9803e2fba6baa6dc915ab8b385ba7.png'
                )
            )
            embed.add_field(
                name="Activity",
                value=f"[{game['category']}](https://www.the100.io/gaming_sessions/{game['id']})"
            )
            embed.add_field(
                name="Start Time",
                value=start_time.strftime('%m-%d %a %I:%M %p %Z')
            )
            embed.add_field(
                name='Description',
                value=game['name'],
                inline=False
            )

            primary = []
            reserve = []
            for session in game['confirmed_sessions']:
                gamertag = session['user']['gamertag']
                try:
                    member_db = await self.bot.database.get_clan_member_by_the100_id(session['user_id'])
                except DoesNotExist:
                    pass
                else:
                    if member_db.clanmember.clan.guild.guild_id == ctx.guild.id:
                        gamertag = f"{gamertag} (m)"

                if session['reserve_spot']:
                    reserve.append(gamertag)
                else:
                    primary.append(gamertag)

            embed.add_field(
                name=(
                    f"Players Joined: {game['primary_users_count']}/{game['team_size']} "
                    f"(Spots Reserved: {spots_reserved})"
                ),
                value=', '.join(primary),
                inline=False
            )
            embed.add_field(
                name='Reserves',
                value=', '.join(reserve) or 'None',
                inline=False
            )
            embed.set_footer(
                text=(
                    f"Creator: {game['creator_gamertag']} | "
                    f"Group: {game['group_name']} | "
                    f"Clan members indicated by (m)"
                )
            )
            await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(GameCog(bot))
