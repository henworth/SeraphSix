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


class ServerCog(commands.Cog, name="Server"):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def server(self, ctx):
        """Server Specific Commands (Admin only)"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    async def twitter_channel(self, ctx, twitter_id, message):
        """Set a channel for particular twitter messages"""
        manager = MessageManager(ctx)

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
            message = f"{message} now enabled and will post to **#{ctx.message.channel.name}**."
        else:
            channel = self.bot.get_channel(channel_db.channel_id)
            message = f"{message} is already enabled in {channel.mention}."
        return await manager.send_and_clean(message)

    @server.command()
    @twitter_enabled()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def xboxsupport(self, ctx):
        """Enable sending tweets from XboxSupport to the current channel (Admin only)"""
        message = f"Xbox Support Information for **{ctx.message.guild.name}**"
        self.bot.loop.create_task(self.twitter_channel(ctx, self.bot.TWITTER_XBOX_SUPPORT, message))

    @server.command()
    @twitter_enabled()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def destinyreddit(self, ctx):
        """Enable sending tweets from r/DestinyTheGame to the current channel (Admin only)"""
        message = f"Destiny the Game Subreddit Posts for **{ctx.message.guild.name}**"
        self.bot.loop.create_task(self.twitter_channel(ctx, self.bot.TWITTER_DESTINY_REDDIT, message))

    @server.command(help="Trigger initial setup of this server (Admin only)")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        """Initial setup of the server (Admin only)"""
        manager = MessageManager(ctx)
        await self.bot.database.create_guild(ctx.guild.id)
        return await manager.send_and_clean(f"Server **{ctx.message.guild.name}** setup")

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clanlink(self, ctx, clan_id=None):
        """Link this server to a Bungie clan (Admin only)"""
        manager = MessageManager(ctx)

        if not clan_id:
            return await manager.send_and_clean("Command must include the Bungie clan ID")

        res = await execute_pydest(self.bot.destiny.api.get_group, clan_id)
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
                return await manager.send_and_clean(
                    f"**{clan_name} [{callsign}]** is already linked to another server.")
            else:
                guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)
                clan_db.guild = guild_db
                clan_db.name = clan_name
                clan_db.callsign = callsign
                await self.bot.database.update(clan_db)

        return await manager.send_and_clean(
            f"Server **{ctx.message.guild.name}** linked to **{clan_name} [{callsign}]**")

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clanunlink(self, ctx):
        """Unlink this server from a linked Bungie clan (Admin only)"""
        manager = MessageManager(ctx)

        try:
            clan_db = await self.bot.database.get_clans_by_guild(ctx.guild.id)
        except DoesNotExist:
            message = "No clan linked to this server."
        else:
            clan_db.guild_id = None
            await self.bot.database.update(clan_db)
            message = f"Server **{ctx.message.guild.name}** unlinked from **{clan_db.name} [{clan_db.callsign}]**"

        return await manager.send_and_clean(message)

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx, new_prefix):
        """Change the server's command prefix (Manage Server only)"""
        manager = MessageManager(ctx)

        if len(new_prefix) > 5:
            message = "Prefix must be less than 6 characters."
        else:
            guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)
            guild_db.prefix = new_prefix
            await self.bot.database.update(guild_db)
            message = f"Command prefix has been changed to `{new_prefix}`"

        return await manager.send_and_clean(message)

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setplatform(self, ctx, platform):
        """Change the server's default platform (Manage Server only)"""
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

        return await manager.send_and_clean(message)

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setsherparoles(self, ctx):
        """Set server roles that distinguish sherpas (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)

        roles = []
        cont = True
        while cont:
            name = await manager.send_and_get_response(
                "Enter the name of a role that denotes a 'sherpa' "
                "(enter `stop` to enter `cancel` to cancel command)")
            if name.lower() == 'cancel':
                return await manager.send_and_clean('Canceling command')
            elif name.lower() == 'stop':
                cont = False
            else:
                role_obj = discord.utils.get(ctx.guild.roles, name=name)
                if role_obj:
                    roles.append((guild_db.id, role_obj.id, True))
                else:
                    return await manager.send_and_clean(f"Could not find a role with name `{name}`")

        if roles:
            await self.bot.database.execute(
                Role.insert_many(roles, fields=[Role.guild, Role.role_id, Role.is_sherpa]))

        return await manager.send_and_cleans("Sherpa roles have been set")

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def showsherparoles(self, ctx):
        """Show server roles that distinguish sherpas (Manage Server only)"""
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
        """Sync server member sherpa role state (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)
        if not guild_db.track_sherpas:
            return await manager.send_message(
                f"Sherpa tracking is not enabled on this server. "
                f"Please run `{ctx.prefix}server sherpatracking` first.",
                mention=False, clean=False)

        added, removed = await store_sherpas(self.bot, guild_db)
        embed = discord.Embed(
            color=constants.BLUE,
            title=f"Sherpas synced for {ctx.guild.name}"
        )
        embed.add_field(name="Added", value=', '.join([str(sherpa) for sherpa in added]) or 'None')
        embed.add_field(name="Removed", value=', '.join([str(sherpa) for sherpa in removed]) or 'None')

        await manager.send_embed(embed, clean=True)

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def sherpatracking(self, ctx):
        """Set server sherpa role tracking state (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)

        reactions = {
            constants.EMOJI_CHECKMARK: 'True',
            constants.EMOJI_CROSSMARK: 'False'
        }
        react = await manager.send_message_react(
            f"Enable sherpa role tracking for {ctx.guild.name}?",
            reactions=reactions.keys(),
            clean=False,
            with_cancel=True
        )

        if not react:
            return await manager.send_and_clean("Canceling command")

        track = reactions[react] == 'True'
        query = Guild.update(track_sherpas=track).where(Guild.id == guild_db.id)
        await self.bot.database.execute(query)

        message = "Sherpa tracking has been"
        if track:
            message = f"{message} **Enabled**"
        else:
            message = f"{message} **Disabled**"

        return await manager.send_message(message, mention=False, clean=False)

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setplatformroles(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)

        roles = []
        for role, emoji in constants.PLATFORM_EMOJI_MAP.items():
            name = await manager.send_and_get_response(
                f"Enter the name of the role to assign for {self.bot.get_emoji(emoji)} "
                f"(enter `cancel` to cancel command)")
            if name.lower() == 'cancel':
                return await manager.send_and_clean("Canceling command")
            else:
                role_obj = discord.utils.get(ctx.guild.roles, name=name)
                if role_obj:
                    roles.append((guild_db.id, role_obj.id, constants.PLATFORM_MAP[role]))
                else:
                    return await manager.send_and_clean(f"Could not find a role with name `{name}`")

        if roles:
            await self.bot.database.execute(
                Role.insert_many(roles, fields=[Role.guild, Role.role_id, Role.platform_id]))

        return await manager.send_and_clean("Platforms have been set")

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def showplatformroles(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
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
            "Clear platform roles?",
            reactions=clear_reactions.keys(),
            clean=False,
            with_cancel=True
        )

        if not clear:
            return await manager.send_and_clean("Canceling command")

        role_query = Role.delete().join(Guild).where(Guild.guild_id == guild_db.id)
        await self.bot.database.execute(role_query)

        return await manager.send_and_clean("Platform roles cleared")

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def aggregateclans(self, ctx):
        """Aggregate all connected clan data (Admin only)"""
        manager = MessageManager(ctx)

        guild_db = await self.bot.database.get(Guild, guild_id=ctx.guild.id)
        if guild_db.aggregate_clans:
            guild_db.aggregate_clans = False
        else:
            guild_db.aggregate_clans = True

        message = f"Clan aggregation has been {'enabled' if guild_db.aggregate_clans else 'disabled'}."
        await self.bot.database.update(guild_db)
        return await manager.send_and_clean(message)


def setup(bot):
    bot.add_cog(ServerCog(bot))
