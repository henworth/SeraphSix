import discord
import logging

from discord.ext import commands
from peewee import DoesNotExist

logging.getLogger(__name__)


class ServerCog(commands.Cog, name='Server'):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    async def server(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send(f"Invalid command `{ctx.message.content}`")

    @server.command()
    @commands.has_permissions(administrator=True)
    async def xbox_support(self, ctx):
        channel_id = ctx.message.channel.id
        message = f"Xbox Support Information for **{ctx.message.guild.name}**"

        async with ctx.typing():
            try:
                await self.bot.database.get_twitter_channel(self.bot.TWITTER_XBOX_SUPPORT)
            except DoesNotExist:
                await self.bot.database.create_twitter_channel(channel_id, self.bot.TWITTER_XBOX_SUPPORT)
                await ctx.send(f"{message} now enabled and will post to **#{ctx.message.channel.name}**.")
            else:
                await ctx.send(f"{message} is already enabled.")

    @server.command()
    @commands.has_permissions(administrator=True)
    async def dtg(self, ctx):
        channel_id = ctx.message.channel.id
        message = f"Destiny the Game Subreddit Posts for **{ctx.message.guild.name}**"

        async with ctx.typing():
            try:
                await self.bot.database.get_twitter_channel(self.bot.TWITTER_DTG)
            except DoesNotExist:
                await self.bot.database.create_twitter_channel(channel_id, self.bot.TWITTER_DTG)
                await ctx.send(f"{message} now enabled and will post to **#{ctx.message.channel.name}**.")
            else:
                await ctx.send(f"{message} is already enabled.")

def setup(bot):
    bot.add_cog(ServerCog(bot))
