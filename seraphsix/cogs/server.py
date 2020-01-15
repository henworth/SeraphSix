import discord
import logging

from discord.ext import commands
from peewee import DoesNotExist
from seraphsix import constants
from seraphsix.cogs.utils.checks import twitter_enabled, clan_is_linked
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.database import TwitterChannel, Clan, Guild, Role
from seraphsix.tasks.activity import execute_pydest
from seraphsix.tasks.discord import store_sherpas

log = logging.getLogger(__name__)


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

        res = await execute_pydest(self.bot.destiny.api.get_group(clan_id), self.bot.redis)
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
                await manager.send_message(f"*{clan_name} [{callsign}]** is already linked to another server.")
                return await manager.clean_messages()
            else:
                guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)
                clan_db.guild = guild_db
                clan_db.name = clan_name
                clan_db.callsign = callsign
                await self.bot.database.update(clan_db)

        await manager.send_message(f"Server **{ctx.message.guild.name}** linked to **{clan_name} [{callsign}]**")
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
            message = f"Server **{ctx.message.guild.name}** unlinked from **{clan_db.name} [{clan_db.callsign}]**"

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

        platform_id = constants.PLATFORM_MAP.get(platform)
        if not platform_id:
            message = f"Platform must be one of `{', '.join(constants.PLATFORM_MAP.keys()).title()}`.`"
        else:
            clan_dbs = await self.bot.database.get_clans_by_guild(ctx.guild.id)
            for clan_db in clan_dbs:
                clan_db.platform = platform_id
            await self.bot.database.bulk_update(clan_dbs, ['platform'])
            message = f"Platform has been set to `{platform}`"

        await manager.send_message(message)
        return await manager.clean_messages()

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setsherparoles(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)

        roles = []
        cont = True
        while cont:
            name = await manager.send_and_get_response(
                f"Enter the name of a role that denotes a \"sherpa\" "
                f"(enter `stop` to enter `cancel` to cancel command)")
            if name.lower() == 'cancel':
                await manager.send_message("Canceling command")
                roles = []
                return await manager.clean_messages()
            elif name.lower() == 'stop':
                cont = False
            else:
                role_obj = discord.utils.get(ctx.guild.roles, name=name)
                if role_obj:
                    roles.append((guild_db.id, role_obj.id, True))
                else:
                    await manager.send_message(f"Could not find a role with name `{name}`")

        if roles:
            await self.bot.database.execute(
                Role.insert_many(roles, fields=[Role.guild, Role.role_id, Role.is_sherpa]))
            await manager.send_message("Sherpa roles have been set")
        return await manager.clean_messages()

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def showsherparoles(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)

        roles = []
        query = Role.select().join(Guild).where((Guild.id == guild_db.id) & (Role.is_sherpa))
        roles_db = await self.bot.database.execute(query)
        for role in roles_db:
            role_obj = discord.utils.get(ctx.guild.roles, id=role.role_id)
            roles.append(role_obj.name)

        base_embed = discord.Embed(
            color=constants.BLUE,
            title=f"Sherpa Roles for {ctx.guild.name}",
            description=', '.join(roles)
        )

        await manager.send_embed(base_embed, clean=True)

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def syncsherpas(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)

        added, removed = await store_sherpas(self.bot, guild_db)
        embed = discord.Embed(
            color=constants.BLUE,
            title=f"Sherpas synced for {ctx.guild.name}"
        )
        embed.add_field(name="Added", value=added)
        embed.add_field(name="Removed", value=removed)

        await manager.send_embed(embed, clean=True)

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setplatformroles(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)

        roles = []
        for role, emoji in constants.PLATFORM_EMOJI_MAP.items():
            name = await manager.send_and_get_response(
                f"Enter the name of the role to assign for {self.bot.get_emoji(emoji)} "
                f"(enter `cancel` to cancel command)")
            if name.lower() == 'cancel':
                await manager.send_message("Canceling command")
                roles = []
                return await manager.clean_messages()
            else:
                role_obj = discord.utils.get(ctx.guild.roles, name=name)
                if role_obj:
                    roles.append((guild_db.id, role_obj.id, constants.PLATFORM_MAP[role]))
                else:
                    await manager.send_message(f"Could not find a role with name `{name}`")

        if roles:
            await self.bot.database.execute(
                Role.insert_many(roles, fields=[Role.guild, Role.role_id, Role.platform_id]))
            await manager.send_message("Platforms have been set")
        return await manager.clean_messages()

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def showplatformroles(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)

        base_embed = discord.Embed(
            color=constants.BLUE,
            title=f"Platform Roles for {ctx.guild.name}"
        )

        for role, emoji in constants.PLATFORM_EMOJI_MAP.items():
            try:
                role_db = await self.bot.database.get(
                    Role, guild_id=guild_db.id, platform_id=constants.PLATFORM_MAP[role]
                )
            except DoesNotExist:
                role_name = "None"
            else:
                role_obj = discord.utils.get(ctx.guild.roles, id=role_db.role_id)
                role_name = role_obj.name
            kwargs = dict(
                name=self.bot.get_emoji(emoji),
                value=role_name,
                inline=True
            )
            base_embed.add_field(**kwargs)

        await manager.send_embed(base_embed, clean=True)

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def clearplatformroles(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        await ctx.trigger_typing()
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)

        base_embed = discord.Embed(
            color=constants.BLUE,
            title=f"Platform Roles for {ctx.guild.name}"
        )

        for role, emoji in constants.PLATFORM_EMOJI_MAP.items():
            role_db = await self.bot.database.get(Role, guild_id=guild_db.id, platform_id=constants.PLATFORM_MAP[role])
            role_obj = discord.utils.get(ctx.guild.roles, id=role_db.role_id)
            kwargs = dict(
                name=self.bot.get_emoji(emoji),
                value=role_obj.name,
                inline=True
            )
            base_embed.add_field(**kwargs)

        await manager.send_embed(base_embed, clean=True)

        clear_reactions = {
            constants.EMOJI_CHECKMARK: 'clear',
            constants.EMOJI_CROSSMARK: ''
        }
        clear = await manager.send_message_react(
            message_text="Clear platform roles?",
            reactions=clear_reactions.keys(),
            clean=False,
            with_cancel=True
        )

        if not clear:
            await manager.send_message("Canceling command")
            return await manager.clean_messages()

        role_query = Role.delete().join(Guild).where(Guild.guild_id == guild_db.id)
        await self.bot.database.execute(role_query)

        await manager.send_message("Platform roles cleared")
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
        """Set a channel for particular twitter messages"""
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
            await ctx.send(f"{message} now enabled and will post to **#{ctx.message.channel.name}**.")
        else:
            channel = self.bot.get_channel(channel_db.channel_id)
            await ctx.send(f"{message} is already enabled in {channel.mention}.")


def setup(bot):
    bot.add_cog(ServerCog(bot))
