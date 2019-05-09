import discord
import logging

from discord.ext import commands
from peewee import DoesNotExist
from trent_six.cogs.utils.message_manager import MessageManager
from trent_six.cogs.utils.checks import twitter_enabled

logging.getLogger(__name__)


class ServerCog(commands.Cog, name='Server'):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def server(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send(f"Invalid command `{ctx.message.content}`")

    @server.command()
    @twitter_enabled()
    @commands.guild_only()
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
    @twitter_enabled()
    @commands.guild_only()
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

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        """
        Change the server's command prefix (Admin only)
        """
        manager = MessageManager(ctx)
        # if len(new_prefix) > 5:
        #     await manager.send_message("Prefix must be less than 6 characters.")
        #     return await manager.clean_messages()

        await self.bot.database.create_guild(ctx.guild.id)
        await manager.send_message(f"Server **{ctx.message.guild.name}** setup")
        return await manager.clean_messages()

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clanlink(self, ctx, group_id):
        """
        Change the server's command prefix (Admin only)
        """
        manager = MessageManager(ctx)
        if not group_id:
            await manager.send_message("Command must include the Bungie group ID")
            return await manager.clean_messages()

        res = await self.bot.destiny.api.get_group(group_id)
        group_name = res['Response']['detail']['name']
        callsign = res['Response']['detail']['clanInfo']['clanCallsign']

        await self.bot.database.create_clan(ctx.guild.id, clan_id=group_id, name=group_name, callsign=callsign)
        await manager.send_message(f"Server **{ctx.message.guild.name}** linked to Clan **{group_name}**")
        return await manager.clean_messages()

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx, new_prefix):
        """
        Change the server's command prefix (Manage Server only)
        """
        manager = MessageManager(ctx)
        if len(new_prefix) > 5:
            await manager.send_message("Prefix must be less than 6 characters.")
            return await manager.clean_messages()

        guild_db = await self.bot.database.get_guild(ctx.guild.id)
        guild_db.prefix = new_prefix
        await self.bot.database.update_guild(guild_db)
        await manager.send_message(f"Command prefix has been changed to `{new_prefix}`")
        return await manager.clean_messages()


def setup(bot):
    bot.add_cog(ServerCog(bot))
