import logging

from discord.ext import commands
from peewee import DoesNotExist
from trent_six.cogs.utils.message_manager import MessageManager
from trent_six.cogs.utils.checks import twitter_enabled, clan_is_linked
from trent_six.destiny.constants import PLATFORM_MAP

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
                await self.bot.database.get_twitter_channel(
                    self.bot.TWITTER_XBOX_SUPPORT)
            except DoesNotExist:
                await self.bot.database.create_twitter_channel(
                    channel_id, self.bot.TWITTER_XBOX_SUPPORT)
                await ctx.send((
                    f"{message} now enabled and will post to "
                    f"**#{ctx.message.channel.name}**."))
            else:
                await ctx.send(f"{message} is already enabled.")

    @server.command()
    @twitter_enabled()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def dtg(self, ctx):
        channel_id = ctx.message.channel.id
        message = (
            f"Destiny the Game Subreddit Posts "
            f"for **{ctx.message.guild.name}**"
        )

        async with ctx.typing():
            try:
                await self.bot.database.get_twitter_channel(
                    self.bot.TWITTER_DTG)
            except DoesNotExist:
                await self.bot.database.create_twitter_channel(
                    channel_id, self.bot.TWITTER_DTG)
                await ctx.send((
                    f"{message} now enabled and will post to "
                    f"**#{ctx.message.channel.name}**."))
            else:
                await ctx.send(f"{message} is already enabled.")

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        """
        Initial setup of the server (Admin only)
        """
        manager = MessageManager(ctx)
        await self.bot.database.create_guild(ctx.guild.id)
        await manager.send_message(
            f"Server **{ctx.message.guild.name}** setup")
        return await manager.clean_messages()

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clanlink(self, ctx, clan_id=None):
        """
        Link this server to a Bungie clan (Admin only)
        """
        manager = MessageManager(ctx)
        if not clan_id:
            await manager.send_message(
                "Command must include the Bungie clan ID")
            return await manager.clean_messages()

        res = await self.bot.destiny.api.get_group(clan_id)
        clan_name = res['Response']['detail']['name']
        callsign = res['Response']['detail']['clanInfo']['clanCallsign']

        try:
            clan_db = await self.bot.database.get_clan(clan_id)
        except DoesNotExist:
            await self.bot.database.create_clan(
                ctx.guild.id, clan_id=clan_id, name=clan_name, callsign=callsign)
        else:
            if clan_db.guild_id:
                await manager.send_message(
                    f"*{clan_name} [{callsign}]** is already linked to another server.")
                return await manager.clean_messages()
            else:
                guild_db = await self.bot.database.get_guild(ctx.guild.id)
                clan_db.guild = guild_db
                clan_db.name = clan_name
                clan_db.callsign = callsign
                await self.bot.database.update(clan_db)

        await manager.send_message((
            f"Server **{ctx.message.guild.name}** "
            f"linked to **{clan_name} [{callsign}]**"))
        return await manager.clean_messages()

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clanunlink(self, ctx):
        """
        Change the server's command prefix (Admin only)
        """
        manager = MessageManager(ctx)

        try:
            clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)
        except DoesNotExist:
            await manager.send_message("No clan linked to this server.")
            return await manager.clean_messages()

        clan_db.guild_id = None
        await self.bot.database.update(clan_db)
        await manager.send_message((
            f"Server **{ctx.message.guild.name}** "
            f"unlinked from **{clan_db.name} [{clan_db.callsign}]**"))
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
            await manager.send_message(
                "Prefix must be less than 6 characters.")
            return await manager.clean_messages()

        guild_db = await self.bot.database.get_guild(ctx.guild.id)
        guild_db.prefix = new_prefix
        await self.bot.database.update(guild_db)
        await manager.send_message(f"Command prefix has been changed to `{new_prefix}`")
        return await manager.clean_messages()

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setplatform(self, ctx, platform):
        """
        Change the server's default platform (Manage Server only)
        """
        manager = MessageManager(ctx)

        if platform not in PLATFORM_MAP.keys():
            await manager.send_message(
                f"Platform must be one of `{', '.join(PLATFORM_MAP.keys()).title()}`.`")
            return await manager.clean_messages()

        clan_db = await self.bot.database.get_clan_by_guild(ctx.guild.id)
        clan_db.platform = PLATFORM_MAP[platform]
        await self.bot.database.update(clan_db)
        await manager.send_message(f"Platform has been set to `{platform}`")
        return await manager.clean_messages()


def setup(bot):
    bot.add_cog(ServerCog(bot))
