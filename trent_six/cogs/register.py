import aioredis
import asyncio
import discord
import logging
import pickle

from discord.ext import commands
from trent_six.cogs.utils import constants
from trent_six.cogs.utils.message_manager import MessageManager
from trent_six.destiny.models import User

logging.getLogger(__name__)


class RegisterCog(commands.Cog, name='Register'):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize Redis connection when bot loads"""
        self.redis = await aioredis.create_redis(self.bot.config['redis_url'])

    @commands.command()
    @commands.cooldown(rate=2, per=5, type=commands.BucketType.user)
    async def register(self, ctx):
        """Register your Destiny 2 account with the bot

        This command will let the bot know which Destiny 2 profile to associate
        with your Discord profile. Registering is a prerequisite to using any
        commands that require knowledge of your Destiny 2 profile.
        """
        manager = MessageManager(ctx)
        auth_url = (
            f'https://{self.bot.config["bungie"]["redirect_host"]}'
            f'/oauth?state={ctx.author.id}'
        )

        if not isinstance(ctx.channel, discord.abc.PrivateChannel):
            await manager.send_message(
                "Registration instructions have been messaged to you.")

        # Prompt user with link to Bungie.net OAuth authentication
        e = discord.Embed(colour=constants.BLUE)
        e.title = "Click Here to Register"
        e.url = auth_url
        e.description = (
            "Click the above link to register your Bungie.net account with Trent-Six. "  # noqa
            "Registering will allow Trent-Six to access your connected Destiny "  # noqa
            "2 accounts."
        )
        registration_msg = await manager.send_private_embed(e)

        # Wait for user info from the web server via Redis
        res = await self.redis.subscribe(ctx.author.id)
        tsk = asyncio.create_task(self.wait_for_msg(res[0]))
        try:
            user_info = await asyncio.wait_for(tsk, timeout=30)
        except asyncio.TimeoutError:
            await manager.send_private_message("I'm not sure where you went. We can try this again later.")
            await registration_msg.delete()
            return await manager.clean_messages()
        await ctx.author.dm_channel.trigger_typing()

        # Save OAuth credentials and Bungie ID
        member_db = await self.bot.database.get_member_by_discord_id(ctx.author.id)
        member_db.bungie_id = user_info.get('membership_id')
        member_db.bungie_access_token = user_info.get('access_token')
        member_db.bungie_refresh_token = user_info.get('refresh_token')

        # Fetch platform specific display names and membership IDs
        try:
            res = await self.bot.destiny.api.get_membership_data_by_id(member_db.bungie_id)
        except Exception:
            await manager.send_private_message(
                "I can't seem to connect to Bungie right now. Try again later.")
            await registration_msg.delete()
            return await manager.clean_messages()

        if res['ErrorCode'] != 1:
            await manager.send_private_message(
                "Oops, something went wrong during registration. Please try again.")
            await registration_msg.delete()
            return await manager.clean_messages()

        if not self.user_has_connected_accounts(res):
            await manager.send_private_message(
                "Oops, you don't have any public accounts attached to your Bungie.net profile.")
            await registration_msg.delete()
            return await manager.clean_messages()

        bungie_user = User(res['Response'])
        member_db.bungie_username = bungie_user.memberships.bungie.username
        if hasattr(bungie_user.memberships, 'xbox'):
            member_db.xbox_username = bungie_user.memberships.xbox.username

        await self.bot.database.update_member(member_db)

        # Send confirmation of successful registration
        e = discord.Embed(
            colour=constants.BLUE,
            title="Registration Complete"
        )
        registered_msg = await manager.send_private_embed(e)

        await registered_msg.delete()
        await registration_msg.delete()

        return await manager.clean_messages()

    def user_has_connected_accounts(self, json):
        """Return true if user has connected destiny accounts"""
        if len(json['Response']['destinyMemberships']):
            return True

    async def wait_for_msg(self, ch):
        """Wait for a message on the specified Redis channel"""
        while (await ch.wait_message()):
            pickled_msg = await ch.get()
            return pickle.loads(pickled_msg)


def setup(bot):
    bot.add_cog(RegisterCog(bot))
