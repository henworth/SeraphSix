import asyncio
import discord
import logging
import pytz

from datetime import datetime
from discord.ext import commands
from peewee import DoesNotExist
from seraphsix import constants
from seraphsix.cogs.utils.checks import clan_is_linked
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.cogs.utils.paginator import EmbedPages

logging.getLogger(__name__)


class GameCog(commands.Cog, name='Game'):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    async def game(self, ctx):
        """Game Specific Commands"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @game.command()
    @clan_is_linked()
    @commands.guild_only()
    async def list(self, ctx):
        """List games on the100 in the linked group(s)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)
        game_tasks = []
        for clan_db in clan_dbs:
            if clan_db.the100_group_id:
                game_tasks.append(self.bot.the100.get_group_gaming_sessions(clan_db.the100_group_id))

        results = await asyncio.gather(*game_tasks, loop=self.bot.loop)

        games = []
        for result in results:
            if results.get('error'):
                logging.error(result)
                continue
            games.extend(result)

        if not games:
            await manager.send_message("No the100 game sessions found")
            return await manager.clean_messages()

        embeds = []
        for game in games:
            try:
                spots_reserved = game['party_size'] - 1
            except TypeError:
                continue

            start_time = datetime.fromisoformat(
                game['start_time']).astimezone(tz=pytz.utc)

            embed = discord.Embed(
                color=constants.BLUE,
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
                    f"(m) denotes clan member"
                )
            )

            embeds.append(embed)

        paginator = EmbedPages(ctx, embeds)
        await paginator.paginate()


def setup(bot):
    bot.add_cog(GameCog(bot))
