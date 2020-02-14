import asyncio

from seraphsix import constants
from seraphsix.cogs.utils.checks import is_private_channel


class MessageManager:

    def __init__(self, ctx, trigger_typing=True):
        if trigger_typing:
            asyncio.create_task(ctx.trigger_typing())

        self.ctx = ctx
        self.messages_to_clean = [ctx.message]

    def add_message_to_clean(self, message):
        """Add a message to be cleaned"""
        self.messages_to_clean.append(message)

    def remove_message_from_clean(self, message):
        """Remove a message from being cleaned"""
        self.messages_to_clean.remove(message)

    async def send_and_clean(self, message):
        await self.send_message(message)
        await self.clean_messages()

    async def clean_messages(self):
        """Delete messages marked for cleaning"""
        def message_needs_cleaning(message):
            if message.id in [m.id for m in self.messages_to_clean]:
                return True

        if not is_private_channel(self.ctx.channel):
            await asyncio.sleep(constants.CLEANUP_DELAY)
            await self.ctx.channel.purge(limit=999, check=message_needs_cleaning)

    async def get_next_message(self):
        """Get the next message sent by the user in ctx.channel
           Raises: asyncio.TimeoutError
        """
        def is_channel_message(message):
            return message.author == self.ctx.author and message.channel == self.ctx.channel
        return await self.ctx.bot.wait_for('message', check=is_channel_message, timeout=115)

    async def get_next_private_message(self):
        """Get the next private message sent by the user
           Raises: asyncio.TimeoutError
        """
        def is_private_message(message):
            return message.author.dm_channel == self.ctx.author.dm_channel
        return await self.ctx.bot.wait_for('message', check=is_private_message, timeout=120)

    async def send_embed(self, embed, content=None, clean=False):
        """Send an embed message to the user on ctx.channel"""
        if is_private_channel(self.ctx.channel):
            msg = await self.send_private_embed(embed, content)
        else:
            msg = await self.ctx.channel.send(embed=embed, content=content)
            if clean:
                self.messages_to_clean.append(msg)
        return msg

    async def send_message(self, message_text, mention=True, clean=True):
        """Send a message to the user on ctx.channel"""
        if is_private_channel(self.ctx.channel):
            msg = await self.send_private_message(message_text)
        else:
            if mention:
                msg = await self.ctx.channel.send(f"{self.ctx.author.mention}: {message_text}")
            else:
                msg = await self.ctx.channel.send(message_text)
            if clean:
                self.messages_to_clean.append(msg)
        return msg

    async def send_and_get_response(self, message_text, clean=True):
        msg = await self.send_message(message_text, clean)
        res = await self.get_next_message()
        retval = res.content
        await msg.delete()
        await res.delete()
        return retval

    async def send_private_embed(self, embed, content=None):
        """Send an private embed message to the user"""
        return await self.ctx.author.send(embed=embed, content=content)

    async def send_private_message(self, message_text):
        """Send a private message to the user"""
        return await self.ctx.author.send(message_text)

    async def send_message_react(self, message_text, reactions=[], embed=None, clean=True, with_cancel=False):  # noqa
        reactions = list(reactions)
        self.reaction_emojis = []
        if embed:
            self.msg = await self.send_embed(embed, content=message_text, clean=clean)
        if message_text and not embed:
            self.msg = await self.send_message(message_text, clean)
        if with_cancel:
            reactions.append(constants.EMOJI_STOP)
        for reaction in reactions:
            reaction_id = self.ctx.bot.get_emoji(reaction)
            if not reaction_id:
                reaction_id = reaction
            self.reaction_emojis.append(reaction_id)
            await self.msg.add_reaction(reaction_id)

        self.match = None
        self.waiting = True
        reaction = None
        retval = None
        while self.waiting:
            try:
                reaction, user = await self.ctx.bot.wait_for('reaction_add', check=self.react_check, timeout=120.0)
            except asyncio.TimeoutError:
                self.waiting = False
                try:
                    await self.message.clear_reactions()
                except Exception:
                    pass
                finally:
                    break

            try:
                await self.msg.remove_reaction(reaction, user)
            except Exception:
                pass  # can't remove it so don't bother doing so

            if reaction:
                if reaction.emoji != constants.EMOJI_STOP:
                    retval = reaction.emoji
                break

        await self.msg.delete()
        self.msg = None
        return retval

    def react_check(self, reaction, user):
        if user is None or user.id != self.ctx.author.id:
            return False

        if reaction.message.id != self.msg.id:
            return False

        for emoji in self.reaction_emojis:
            if reaction.emoji == emoji:
                self.match = emoji
                self.waiting = False
                return True
        return False
