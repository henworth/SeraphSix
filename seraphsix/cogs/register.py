import asyncio
import discord
import logging
import pickle

from discord.ext import commands
from peewee import DoesNotExist
from seraphsix import constants
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.database import Member, Role, Guild
from seraphsix.models.destiny import User
from seraphsix.tasks.activity import execute_pydest

log = logging.getLogger(__name__)


async def register(ctx, manager, extra_message='', confirm_message=''):
    if not confirm_message:
        confirm_message = "Registration Complete"

    auth_url = (
        f"https://{ctx.bot.config.bungie.redirect_host}/oauth?state={ctx.author.id}"
    )

    if not isinstance(ctx.channel, discord.abc.PrivateChannel):
        await manager.send_message(f"{extra_message} Registration instructions have been messaged to you.".strip())

    # Prompt user with link to Bungie.net OAuth authentication
    e = discord.Embed(colour=constants.BLUE)
    e.title = "Click Here to Register"
    e.url = auth_url
    e.description = (
        "Click the above link to register your Bungie.net account with Seraph Six. "
        "Registering will allow Seraph Six to access your connected Destiny 2"
        "accounts. At no point will Seraph Six have access to your password."
    )
    registration_msg = await manager.send_private_embed(e)

    # Wait for user info from the web server via Redis
    res = await ctx.bot.redis.subscribe(ctx.author.id)

    tsk = asyncio.create_task(wait_for_msg(res[0]))
    try:
        user_info = await asyncio.wait_for(tsk, timeout=constants.TIME_MIN_SECONDS)
    except asyncio.TimeoutError:
        log.debug(f"Timed out waiting for {str(ctx.author)} ({ctx.author.id}) to register")
        await manager.send_private_message("I'm not sure where you went. We can try this again later.")
        await registration_msg.delete()
        await manager.clean_messages()
        await ctx.bot.redis.unsubscribe(ctx.author.id)
        return (None, None)
    await ctx.author.dm_channel.trigger_typing()

    # Send confirmation of successful registration
    e = discord.Embed(
        colour=constants.BLUE,
        title=confirm_message
    )
    embed = await manager.send_private_embed(e)
    await ctx.bot.redis.unsubscribe(ctx.author.id)

    return embed, user_info


async def wait_for_msg(ch):
    """Wait for a message on the specified Redis channel"""
    while (await ch.wait_message()):
        pickled_msg = await ch.get()
        return pickle.loads(pickled_msg)


class RegisterCog(commands.Cog, name="Register"):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def register(self, ctx):  # noqa TODO
        """Register your Destiny 2 account with Seraph Six

        This command will let Seraph Six know which Destiny 2 profile to associate
        with your Discord profile. Registering is a prerequisite to using any
        commands that require knowledge of your Destiny 2 profile.
        """
        manager = MessageManager(ctx)

        embed, user_info = await register(ctx, manager, confirm_message="Initial Registration Complete...")
        if not user_info:
            await manager.send_private_message("Oops, something went wrong during registration. Please try again.")
            return await manager.clean_messages()

        bungie_access_token = user_info.get('access_token')

        # Fetch platform specific display names and membership IDs
        try:
            res = await execute_pydest(
                self.bot.destiny.api.get_membership_current_user(bungie_access_token),
                self.bot.redis
            )
        except Exception as e:
            log.exception(e)
            await manager.send_private_message("I can't seem to connect to Bungie right now. Try again later.")
            return await manager.clean_messages()

        if res['ErrorCode'] != 1:
            await manager.send_private_message("Oops, something went wrong during registration. Please try again.")
            return await manager.clean_messages()

        if not self.user_has_connected_accounts(res):
            await manager.send_private_message(
                "Oops, you don't have any public accounts attached to your Bungie.net profile.")
            return await manager.clean_messages()

        bungie_user = User(res['Response'])

        member_ids = [
            (bungie_user.memberships.xbox.id, constants.PLATFORM_XBOX),
            (bungie_user.memberships.psn.id, constants.PLATFORM_PSN),
            (bungie_user.memberships.steam.id, constants.PLATFORM_STEAM),
            (bungie_user.memberships.stadia.id, constants.PLATFORM_STADIA),
            (bungie_user.memberships.blizzard.id, constants.PLATFORM_BLIZZARD),
            (bungie_user.memberships.bungie.id, constants.PLATFORM_BUNGIE)
        ]

        try:
            member_db = await self.bot.database.get_member_by_platform(
                bungie_user.memberships.bungie.id, constants.PLATFORM_BUNGIE)
        except DoesNotExist:
            # Create a list of member id with their respective platforms, if the id is not null
            member_id_list = ((member_id, platform_id) for member_id, platform_id in member_ids if member_id)
            # Grab the first one and craft the query data
            member_id, platform_id = next(member_id_list)
            query_data = dict(
                member_id=member_id,
                platform_id=platform_id
            )

            # Query for that member, if that fails create a skeleton entry
            try:
                member_db = await self.bot.database.get_member_by_platform(**query_data)
            except DoesNotExist:
                member_db = await self.bot.database.create(Member)

        # Save OAuth credentials and Bungie User data
        for key, value in bungie_user.to_dict().items():
            setattr(member_db, key, value)

        member_db.discord_id = ctx.author.id
        member_db.bungie_access_token = bungie_access_token
        member_db.bungie_refresh_token = user_info.get('refresh_token')

        await self.bot.database.update(member_db)

        e = discord.Embed(
            colour=constants.BLUE,
            title="Full Registration Complete"
        )

        emojis = []
        # Update platform roles to match connected accounts
        if ctx.guild:
            guild_query = Role.select(Role).join(Guild).where(Guild.guild_id == ctx.guild.id)
            guild_roles_db = await self.bot.database.execute(guild_query)
            member_platforms = [platform_id for member_id, platform_id in member_ids if member_id]

            guild_roles = [
                discord.utils.get(ctx.guild.roles, id=role_db.role_id)
                for role_db in guild_roles_db
                if role_db.platform_id in member_platforms
            ]

            await ctx.author.add_roles(*guild_roles)

            platform_names = list(constants.PLATFORM_MAP.keys())
            platform_ids = list(constants.PLATFORM_MAP.values())

            platform_emojis = [
                constants.PLATFORM_EMOJI_MAP.get(platform_names[platform_ids.index(platform)])
                for platform in member_platforms
            ]

            message = f"User {str(ctx.author)} ({ctx.author.id}) has registered"

            if platform_emojis:
                emojis = [str(self.bot.get_emoji(emoji)) for emoji in platform_emojis if emoji]
                e.add_field(
                    name="Platforms Connected",
                    value=' '.join(emojis)
                )
                message = f"{message} with platforms {' '.join(emojis)}"

            await embed.edit(embed=e)
            await self.bot.reg_channel.send(message)

        return await manager.clean_messages()

    def user_has_connected_accounts(self, json):
        """Return true if user has connected destiny accounts"""
        if len(json['Response']['destinyMemberships']):
            return True


def setup(bot):
    bot.add_cog(RegisterCog(bot))
