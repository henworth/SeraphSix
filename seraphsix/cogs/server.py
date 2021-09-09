import discord
import logging

from discord.ext import commands
from tortoise.exceptions import DoesNotExist
from seraphsix import constants
from seraphsix.cogs.utils.checks import twitter_enabled, clan_is_linked
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.models.database import TwitterChannel, Clan, Guild, Role
from seraphsix.models.destiny import DestinyGroupResponse
from seraphsix.tasks.core import execute_pydest
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

    @server.group(name="set", invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def server_set(self, ctx):
        """Server Set Commands (Admin only)"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @server.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def role(self, ctx):
        """Server Role Specific Commands (Admin only)"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @role.group(name="set", invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def role_set(self, ctx):
        """Server Role Set Commands (Admin only)"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @role.group(name="show", invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def role_show(self, ctx):
        """Server Role Show Commands (Admin only)"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @role.group(name="clear", invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def role_clear(self, ctx):
        """Server Role Clear Commands (Admin only)"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @server.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def channel(self, ctx):
        """Server Channel Specific Commands (Admin only)"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    @channel.group(name="set", invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def set_channel(self, ctx):
        """Server Channel Set Commands (Admin only)"""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound()

    async def twitter_channel(self, ctx, twitter_id, message):
        """Set a channel for particular twitter messages"""
        manager = MessageManager(ctx)

        channel_db = await TwitterChannel.get_or_none(
            guild_id=ctx.message.guild.id, twitter_id=twitter_id
        )
        if not channel_db:
            details = {
                "guild_id": ctx.message.guild.id,
                "channel_id": ctx.message.channel.id,
                "twitter_id": twitter_id,
            }
            await TwitterChannel.create(**details)
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
        self.bot.loop.create_task(
            self.twitter_channel(ctx, self.bot.TWITTER_XBOX_SUPPORT, message)
        )

    @server.command()
    @twitter_enabled()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def destinyreddit(self, ctx):
        """Enable sending tweets from r/DestinyTheGame to the current channel (Admin only)"""
        message = f"Destiny the Game Subreddit Posts for **{ctx.message.guild.name}**"
        self.bot.loop.create_task(
            self.twitter_channel(ctx, self.bot.TWITTER_DESTINY_REDDIT, message)
        )

    @server.command(help="Trigger initial setup of this server (Admin only)")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        """Initial setup of the server (Admin only)"""
        manager = MessageManager(ctx)
        await self.bot.database.create_guild(ctx.guild.id)
        return await manager.send_and_clean(
            f"Server **{ctx.message.guild.name}** setup"
        )

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clanlink(self, ctx, clan_id=None):
        """Link this server to a Destiny clan (Admin only)"""
        manager = MessageManager(ctx)

        if not clan_id:
            return await manager.send_and_clean(
                "Command must include the Destiny clan ID"
            )

        group = await execute_pydest(
            self.bot.destiny.api.get_group, clan_id, return_type=DestinyGroupResponse
        )
        clan_name = group.response.detail.name
        callsign = group.response.detail.clan_info.clan_callsign

        clan_db = await Clan.get_or_none(clan_id=clan_id)
        if not clan_db:
            guild_db = await Guild.get(guild_id=ctx.guild.id)
            await Clan.create(
                clan_id=clan_id, name=clan_name, callsign=callsign, guild=guild_db
            )
        else:
            if clan_db.guild_id:
                return await manager.send_and_clean(
                    f"**{clan_name} [{callsign}]** is already linked to another server."
                )
            else:
                guild_db = await Guild.get(guild_id=ctx.guild.id)
                clan_db.guild = guild_db
                clan_db.name = clan_name
                clan_db.callsign = callsign
                await clan_db.save()

        return await manager.send_and_clean(
            f"Server **{ctx.message.guild.name}** linked to **{clan_name} [{callsign}]**"
        )

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clanunlink(self, ctx):
        """Unlink this server from a linked Destiny clan (Admin only)"""
        manager = MessageManager(ctx)

        try:
            clan_db = await self.bot.database.get_clans_by_guild(ctx.guild.id)
        except DoesNotExist:
            message = "No clan linked to this server."
        else:
            clan_db.guild_id = None
            await clan_db.save()
            message = f"Server **{ctx.message.guild.name}** unlinked from **{clan_db.name} [{clan_db.callsign}]**"

        return await manager.send_and_clean(message)

    @server_set.command(name="prefix")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx, new_prefix):
        """Change the server's command prefix (Manage Server only)"""
        manager = MessageManager(ctx)

        if len(new_prefix) > 5:
            message = "Prefix must be less than 6 characters."
        else:
            guild_db = await Guild.get(guild_id=ctx.guild.id)
            guild_db.prefix = new_prefix
            await guild_db.save()
            message = f"Command prefix has been changed to `{new_prefix}`"

        return await manager.send_and_clean(message)

    @server_set.command(name="platform")
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
            await clan_dbs.update(platform=platform_id)
            message = f"Platform has been set to `{platform}`"

        return await manager.send_and_clean(message)

    @set_channel.command(name="admin")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def channelsetadmin(self, ctx, channel_id: int):
        """Set the channel for admin notifications (Manage Server only)"""
        manager = MessageManager(ctx)

        if not channel_id:
            message = "Channel ID must be provided"
        else:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                message = f"Channel ID {channel_id} not found"
            else:
                guild_db = await Guild.get(guild_id=ctx.guild.id)
                guild_db.admin_channel = channel_id
                await guild_db.save()
                message = f"Channel for Admin Notifications set to {str(channel)} ({channel_id})"

        return await manager.send_and_clean(message)

    @role_set.command(name="sherpa")
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def rolesetsherpa(self, ctx):
        """Set server roles that distinguish sherpas (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await Guild.get(guild_id=ctx.guild.id)

        roles = []
        cont = True
        while cont:
            name = await manager.send_and_get_response(
                "Enter the name of one or more roles that denote(s) a 'sherpa', one per line. "
                "(enter `stop` when done, or enter `cancel` to cancel command entirely)"
            )
            if name.lower() == "cancel":
                return await manager.send_and_clean("Canceling command")
            elif name.lower() == "stop":
                cont = False
            else:
                role_obj = discord.utils.get(ctx.guild.roles, name=name)
                if role_obj:
                    roles.append(
                        Role(guild=guild_db, role_id=role_obj.id, is_sherpa=True)
                    )
                else:
                    return await manager.send_and_clean(
                        f"Could not find a role with name `{name}`"
                    )

        if roles:
            await Role.bulk_create(roles)

        return await manager.send_and_clean("Sherpa roles have been set")

    @role_show.command(name="sherpa")
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def roleshowsherpa(self, ctx):
        """Show server roles that distinguish sherpas (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await Guild.get(guild_id=ctx.guild.id)

        roles = []
        roles_db = await Role.filter(guild=guild_db, is_sherpa=True)
        for role in roles_db:
            role_obj = discord.utils.get(ctx.guild.roles, id=role.role_id)
            roles.append(role_obj.name)

        base_embed = discord.Embed(
            color=constants.BLUE,
            title=f"Sherpa Roles for {ctx.guild.name}",
            description=", ".join(roles),
        )

        await manager.send_embed(base_embed, clean=True)

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def syncsherpas(self, ctx):
        """Sync server member sherpa role state (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await Guild.get(guild_id=ctx.guild.id)
        if not guild_db.track_sherpas:
            return await manager.send_message(
                f"Sherpa tracking is not enabled on this server. "
                f"Please run `{ctx.prefix}server sherpatracking` first.",
                mention=False,
                clean=False,
            )

        added, removed = await store_sherpas(self.bot, guild_db)
        embed = discord.Embed(
            color=constants.BLUE, title=f"Sherpas synced for {ctx.guild.name}"
        )
        embed.add_field(
            name="Added", value=", ".join([str(sherpa) for sherpa in added]) or "None"
        )
        embed.add_field(
            name="Removed",
            value=", ".join([str(sherpa) for sherpa in removed]) or "None",
        )

        await manager.send_embed(embed, clean=True)

    @server.command()
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def sherpatracking(self, ctx):
        """Set server sherpa role tracking state (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await Guild.get(guild_id=ctx.guild.id)

        reactions = {
            constants.EMOJI_CHECKMARK: "True",
            constants.EMOJI_CROSSMARK: "False",
        }
        react = await manager.send_message_react(
            f"Enable sherpa role tracking for {ctx.guild.name}?",
            reactions=reactions.keys(),
            clean=False,
            with_cancel=True,
        )

        if not react:
            return await manager.send_and_clean("Canceling command")

        track = reactions[react] == "True"
        await guild_db.update(track_sherpas=track)

        message = "Sherpa tracking has been"
        if track:
            message = f"{message} **Enabled**"
        else:
            message = f"{message} **Disabled**"

        return await manager.send_message(message, mention=False, clean=False)

    @role_set.command(name="platforms")
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def rolesetplatform(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await Guild.get(guild_id=ctx.guild.id)

        roles = []
        for role, emoji in constants.PLATFORM_EMOJI_MAP.items():
            name = await manager.send_and_get_response(
                f"Enter the name of the role to assign for {self.bot.get_emoji(emoji)} "
                f"(enter `cancel` to cancel command)"
            )
            if name.lower() == "cancel":
                return await manager.send_and_clean("Canceling command")
            else:
                role_obj = discord.utils.get(ctx.guild.roles, name=name)
                if role_obj:
                    roles.append(
                        Role(
                            guild=guild_db,
                            role_id=role_obj.id,
                            platform_id=constants.PLATFORM_MAP[role],
                        )
                    )
                else:
                    return await manager.send_and_clean(
                        f"Could not find a role with name `{name}`"
                    )

        if roles:
            await Role.bulk_create(roles)

        return await manager.send_and_clean("Platforms have been set")

    @role_show.command(name="platform")
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def roleshowplatform(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await Guild.get(guild_id=ctx.guild.id)

        base_embed = discord.Embed(
            color=constants.BLUE, title=f"Platform Roles for {ctx.guild.name}"
        )

        for role, emoji in constants.PLATFORM_EMOJI_MAP.items():
            role_db = await Role.get_or_none(
                guild=guild_db, platform_id=constants.PLATFORM_MAP[role]
            )
            if not role_db:
                role_name = "None"
            else:
                role_obj = discord.utils.get(ctx.guild.roles, id=role_db.role_id)
                role_name = role_obj.name
            kwargs = dict(name=self.bot.get_emoji(emoji), value=role_name, inline=True)
            base_embed.add_field(**kwargs)

        await manager.send_embed(base_embed, clean=True)

    @role_clear.command(name="platform")
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def roleclearplatform(self, ctx):
        """Map server roles to game platforms (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await Guild.get(guild_id=ctx.guild.id)

        base_embed = discord.Embed(
            color=constants.BLUE, title=f"Platform Roles for {ctx.guild.name}"
        )

        for role, emoji in constants.PLATFORM_EMOJI_MAP.items():
            role_db = await Role.get(
                guild=guild_db, platform_id=constants.PLATFORM_MAP[role]
            )
            role_obj = discord.utils.get(ctx.guild.roles, id=role_db.role_id)
            kwargs = dict(
                name=self.bot.get_emoji(emoji), value=role_obj.name, inline=True
            )
            base_embed.add_field(**kwargs)

        await manager.send_embed(base_embed, clean=True)

        clear_reactions = {
            constants.EMOJI_CHECKMARK: "clear",
            constants.EMOJI_CROSSMARK: "",
        }
        clear = await manager.send_message_react(
            "Clear platform roles?",
            reactions=clear_reactions.keys(),
            clean=False,
            with_cancel=True,
        )

        if not clear:
            return await manager.send_and_clean("Canceling command")

        await Role.filter(guild=guild_db).delete()
        return await manager.send_and_clean("Platform roles cleared")

    @role_set.command(name="protectedmember")
    @clan_is_linked()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def rolesetprotectedmember(self, ctx):
        """Set server roles that distinguish protected members (Manage Server only)"""
        manager = MessageManager(ctx)
        guild_db = await Guild.get(guild_id=ctx.guild.id)

        roles = []
        cont = True
        while cont:
            name = await manager.send_and_get_response(
                "Enter the name of one or more roles that denote(s) a 'protected member', one per line. "
                "(enter `stop` when done, or enter `cancel` to cancel command entirely)"
            )
            if name.lower() == "cancel":
                return await manager.send_and_clean("Canceling command")
            elif name.lower() == "stop":
                cont = False
            else:
                role_obj = discord.utils.get(ctx.guild.roles, name=name)
                if role_obj:
                    roles.append(
                        Role(
                            guild=guild_db,
                            role_id=role_obj.id,
                            is_protected_clanmember=True,
                        )
                    )
                else:
                    return await manager.send_and_clean(
                        f"Could not find a role with name `{name}`"
                    )

        if roles:
            await Role.bulk_create(roles)

        return await manager.send_and_clean("Protected member roles have been set")

    @server.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def aggregateclans(self, ctx):
        """Aggregate all connected clan data (Admin only)"""
        manager = MessageManager(ctx)
        guild_db = await Guild.get(guild_id=ctx.guild.id)

        if guild_db.aggregate_clans:
            guild_db.aggregate_clans = False
        else:
            guild_db.aggregate_clans = True

        message = f"Clan aggregation has been {'enabled' if guild_db.aggregate_clans else 'disabled'}."
        await guild_db.save()
        return await manager.send_and_clean(message)


def setup(bot):
    bot.add_cog(ServerCog(bot))
