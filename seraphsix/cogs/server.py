import logging

from discord.ext import commands
from peewee import DoesNotExist
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.cogs.utils.checks import twitter_enabled, clan_is_linked
from seraphsix.constants import PLATFORM_MAP
from seraphsix.database import TwitterChannel, Clan, Guild
from seraphsix.tasks.activity import execute_pydest

logging.getLogger(__name__)


class ServerCog(commands.Cog, name='Server'):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def server(self, ctx):
        """Server Specific Commands (Admin only)"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @server.command()
    @twitter_enabled()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def xboxsupport(self, ctx):
        """Enable sending tweets from XboxSupport to the current channel (Admin only)"""
        await ctx.trigger_typing()
        message = f"Xbox Support Information for **{ctx.message.guild.name}**"
        self.bot.loop.create_task(self.twitter_channel(ctx, self.bot.TWITTER_XBOX_SUPPORT, message))

    @server.command()
    @twitter_enabled()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def destinyreddit(self, ctx):
        """Enable sending tweets from r/DestinyTheGame to the current channel (Admin only)"""
        await ctx.trigger_typing()
        message = f"Destiny the Game Subreddit Posts for **{ctx.message.guild.name}**"
        self.bot.loop.create_task(self.twitter_channel(ctx, self.bot.TWITTER_DESTINY_REDDIT, message))

    @server.command(help="Trigger initial setup of this server (Admin only)")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        """Initial setup of the server (Admin only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        await self.bot.database.create_guild(ctx.guild.id)
        await manager.send_message(
            f"Server **{ctx.message.guild.name}** setup")
        return await manager.clean_messages()

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clanlink(self, ctx, clan_id=None):
        """Link this server to a Bungie clan (Admin only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        if not clan_id:
            await manager.send_message(
                "Command must include the Bungie clan ID")
            return await manager.clean_messages()

        res = await execute_pydest(self.bot.destiny.api.get_group(clan_id))
        clan_name = res['Response']['detail']['name']
        callsign = res['Response']['detail']['clanInfo']['clanCallsign']

        try:
            clan_db = await self.bot.database.get(Clan, clan_id=clan_id)
        except DoesNotExist:
            guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)
            await self.bot.database.create(
                Clan, clan_id=clan_id, name=clan_name, callsign=callsign, guild=guild_db)
        else:
            if clan_db.guild_id:
                await manager.send_message(
                    f"*{clan_name} [{callsign}]** is already linked to another server.")
                return await manager.clean_messages()
            else:
                guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)
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
        """Unlink this server from a linked Bungie clan (Admin only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        try:
            clan_db = await self.bot.database.get_clans_by_guild(ctx.guild.id)
        except DoesNotExist:
            message = "No clan linked to this server."
        else:
            clan_db.guild_id = None
            await self.bot.database.update(clan_db)
            message = (
                f"Server **{ctx.message.guild.name}** "
                f"unlinked from **{clan_db.name} [{clan_db.callsign}]**")

        await manager.send_message(message)
        return await manager.clean_messages()

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx, new_prefix):
        """Change the server's command prefix (Manage Server only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        if len(new_prefix) > 5:
            message = "Prefix must be less than 6 characters."
        else:
            guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)
            guild_db.prefix = new_prefix
            await self.bot.database.update(guild_db)
            message = f"Command prefix has been changed to `{new_prefix}`"

        await manager.send_message(message)
        return await manager.clean_messages()

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setplatform(self, ctx, platform):
        """Change the server's default platform (Manage Server only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        platform = platform.lower()

        platform_id = PLATFORM_MAP.get(platform)
        if not platform_id:
            message = f"Platform must be one of `{', '.join(PLATFORM_MAP.keys()).title()}`.`"
        else:
            clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)
            for clan_db in clan_dbs:
                clan_db.platform = platform_id
            await self.bot.database.bulk_update(clan_dbs, ['platform'])
            message = f"Platform has been set to `{platform}`"

        await manager.send_message(message)
        return await manager.clean_messages()

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def aggregateclans(self, ctx):
        """Aggregate all connected clan data (Admin only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)

        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)
        if guild_db.aggregate_clans:
            guild_db.aggregate_clans = False
        else:
            guild_db.aggregate_clans = True

        message = f"Clan aggregation has been {'enabled' if guild_db.aggregate_clans else 'disabled'}."
        await self.bot.database.update(guild_db)
        await manager.send_message(message)
        return await manager.clean_messages()

    async def twitter_channel(self, ctx, twitter_id, message):
        try:
            # pylint: disable=assignment-from-no-return
            query = TwitterChannel.select().where(
                TwitterChannel.guild_id == ctx.message.guild.id,
                TwitterChannel.twitter_id == twitter_id
            )
            channel_db = await self.bot.database.get(query)
        except DoesNotExist:
            details = {'guild_id': ctx.message.guild.id,
                       'channel_id': ctx.message.channel.id, 'twitter_id': twitter_id}
            await self.bot.database.create(TwitterChannel, **details)
            await ctx.send((
                f"{message} now enabled and will post to "
                f"**#{ctx.message.channel.name}**."))
        else:
            channel = self.bot.get_channel(channel_db.channel_id)
            await ctx.send(f"{message} is already enabled in {channel.mention}.")


def setup(bot):
    bot.add_cog(ServerCog(bot))
