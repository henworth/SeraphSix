#!/usr/bin/env python3.7
import asyncio
import discord
import logging
import os
import pydest

from discord.errors import HTTPException
from discord.ext.commands import Bot, UserConverter
from discord.ext.commands.errors import BadArgument, CommandNotFound, CommandInvokeError

from peewee import DoesNotExist, IntegrityError

from bot_activity import get_member_history
from database import Database, Member, GameSession
from members import get_all

DATABASE_URL = os.environ.get('DATABASE_URL')
BUNGIE_API_KEY = os.environ.get('BUNGIE_API_KEY')
DISCORD_API_KEY = os.environ.get('DISCORD_API_KEY')
GROUP_ID = os.environ.get('GROUP_ID')

logging.basicConfig(level=logging.INFO)
logging.getLogger('aiohttp.client').setLevel(logging.ERROR)

loop = asyncio.new_event_loop()
bot = Bot(loop=loop, command_prefix='?')
database = Database(DATABASE_URL, loop=loop)
database.initialize()

destiny = pydest.Pydest(BUNGIE_API_KEY, loop=loop)


async def get_all_games(game_mode: str):
    while True:
        logging.info(f"background: Finding all {game_mode} games for all members")
        for member in await database.get_members():
            count = await get_member_history(database, destiny, member.xbox_username, game_mode, check_date=False)
            logging.info(f"background: Found {count} {game_mode} games for {member.xbox_username}")
        logging.info(f"background: Found all {game_mode} games for all members")
        await asyncio.sleep(3600)


@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user.name} ({bot.user.id})")
    logging.info(f"Invite: https://discordapp.com/oauth2/authorize?client_id={bot.user.id}&scope=bot")
    bot.loop.create_task(get_all_games('raid'))
    bot.loop.create_task(get_all_games('gambit'))
    bot.loop.create_task(get_all_games('pvp'))

@bot.command()
async def greet(ctx):
    await ctx.send(":wave: Hello, there! :smiley:")


@bot.group()
async def member(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send(f"Invalid command `{ctx.message.content}`")


@member.command()
async def link_other(ctx, xbox_username: str, discord_username: str):
    is_admin = False
    for role in ctx.message.author.roles:
        if role.permissions.administrator:
            is_admin = True
            break

    if not is_admin:
        await ctx.send(f"Linking for other users is only for users with an Administrator role")
        return

    try:
        member_discord = await UserConverter().convert(ctx, discord_username)
    except BadArgument:
        await ctx.send(f"Discord user \"{discord_username}\" not found")
        return

    async with ctx.typing():
        try:
            member_db = await database.get_member(xbox_username)
        except DoesNotExist:
            await ctx.send(f"Gamertag \"{xbox_username}\" does not match a valid member")
            return
        if member_db.discord_id:
            member_discord = await UserConverter().convert(ctx, str(member_db.discord_id))
            await ctx.send(f"Gamertag \"{xbox_username}\" already linked to Discord user \"{member_discord.display_name}\"")
            return

        member_db.discord_id = member_discord.id
        try:
            await database.update_member(member_db)
        except Exception:
            logging.exception(f"Could not link member \"{xbox_username}\" to Discord user \"{member_discord.display_name}\" (id:{member_discord.id}")
            return
        await ctx.send(f"Linked Gamertag \"{xbox_username}\" to Discord user \"{member_discord.display_name}\"")


@member.command()
async def link(ctx, *, xbox_username: str):
    try:
        member_discord = await UserConverter().convert(ctx, str(ctx.message.author))
    except Exception:
        return

    async with ctx.typing():
        xbox_username = xbox_username.replace('"', '')
        try:
            member_db = await database.get_member(xbox_username)
        except DoesNotExist:
            await ctx.send(f"Gamertag \"{xbox_username}\" does not match a valid member")
            return
        if member_db.discord_id:
            member_discord = await UserConverter().convert(ctx, str(member_db.discord_id))
            await ctx.send(f"Gamertag \"{xbox_username}\" already linked to Discord user \"{member_discord.display_name}\"")
            return

        member_db.discord_id = member_discord.id
        try:
            await database.update_member(member_db)
        except Exception:
            logging.exception(f"Could not link member \"{xbox_username}\" to Discord user \"{member_discord.display_name}\" (id:{member_discord.id}")
            return
        await ctx.send(f"Linked Gamertag \"{xbox_username}\" to Discord user \"{member_discord.display_name}\"")


@member.command()
async def games_all(ctx, game_mode: str):
    is_admin = False
    for role in ctx.message.author.roles:
        if role.permissions.administrator:
            is_admin = True
            break

    if not is_admin:
        await ctx.send(f"This command is only for users with an Administrator role")
        return

    game_modes = ['gambit', 'raid', 'pvp-quick', 'pvp-comp', 'pvp']

    if game_mode not in game_modes:
        await ctx.send(f"Invalid game mode `{game_mode}`, supported are `{', '.join(game_modes)}`")
        return

    logging.info(f"Finding all {game_mode} games for all members")
    members_db = await database.get_members()
    for member in members_db:
        count = await get_member_history(database, destiny, member.xbox_username, game_mode)
        logging.info(f"Found {count} games of {game_mode} for {member.xbox_username}")
    logging.info(f"Found all {game_mode} games for all members")


@member.command()
async def sync(ctx):
    is_admin = False
    for role in ctx.message.author.roles:
        if role.permissions.administrator:
            is_admin = True
            break

    if not is_admin:
        await ctx.send(f"This command is only for users with an Administrator role")
        return

    async with ctx.typing():
        bungie_members = {}
        async for member in get_all(destiny, GROUP_ID): # pylint: disable=not-an-iterable
            bungie_members[member.bungie_id] = member

        bungie_member_set = set(
            [member for member in bungie_members.keys()]
        )

        db_members = {}
        for member in await database.get_members():
            db_members[member.bungie_id] = member

        db_member_set = set(
            [member for member in db_members.keys()]
        )

        new_members = bungie_member_set - db_member_set
        purged_members = db_member_set - bungie_member_set

        for member_bungie_id in new_members:
            try:
                await database.create_member(bungie_members[member_bungie_id].__dict__)
            except IntegrityError:
                member_db = await database.get_member_by_bungie(member_bungie_id)
                member_db.is_active = True
                member_db.join_date = bungie_members[member_bungie_id].join_date
                await database.update_member(member_db)

        for member in purged_members:
            member_db = db_members[member]
            member_db.is_active = False
            await database.update_member(member_db)

    embed = discord.Embed(
        title="Membership Changes"
    )

    if len(new_members) > 0:
        new_member_usernames = []
        for bungie_id in new_members:
            member_db = await database.get_member_by_bungie(bungie_id)
            new_member_usernames.append(member_db.xbox_username)
        added = sorted(new_member_usernames, key=lambda s: s.lower())
        embed.add_field(name="Members Added", value=', '.join(added), inline=False)
        logging.info(f"Added members {added}")

    if len(purged_members) > 0:
        purged_member_usernames = []
        for bungie_id in purged_members:
            member_db = await database.get_member_by_bungie(bungie_id)
            purged_member_usernames.append(member_db.xbox_username)
        purged = sorted(purged_member_usernames, key=lambda s: s.lower())
        embed.add_field(name="Members Purged", value=', '.join(purged), inline=False)
        logging.info(f"Purged members {purged}")

    if len(purged_members) == 0 and len(new_members) == 0:
        embed.description = "None"

    try:
        await ctx.send(embed=embed)
    except HTTPException:
        embed.clear_fields()
        embed.add_field(name="Members Added", value=len(new_members), inline=False)
        embed.add_field(name="Members Purged", value=len(purged_members), inline=False)
        await ctx.send(embed=embed)


@member.command()
async def games(ctx, *, command: str):
    command = command.split()
    game_mode = command[0]
    member_name = ' '.join(command[1:])

    game_modes = ['gambit', 'raid', 'pvp-quick', 'pvp-comp', 'pvp']
    if game_mode not in game_modes:
        await ctx.send(f"Invalid game mode `{game_mode}`, supported are `{', '.join(game_modes)}`")
        return

    async with ctx.typing():
        if not member_name:
            discord_id = ctx.author.id
            try:
                member_db = await database.get_member_by_discord(discord_id)
            except DoesNotExist:
                await ctx.send(f"User {ctx.author.display_name} has not been linked a Gamertag or is not a clan member")
                return
            logging.info(f"Getting {game_mode} games for {ctx.author.display_name} by Discord id {discord_id}")
        else:
            try:
                member_db = await database.get_member(member_name)
            except DoesNotExist:
                await ctx.send(f"Invalid member name {member_name}")
                return
            logging.info(f"Getting {game_mode} games for {ctx.author.display_name} by Gamertag {member_name}")

        game_count = await get_member_history(database, destiny, member_db.xbox_username, game_mode)

    embed = discord.Embed(
        title=f"Eligible {game_mode.capitalize()} Games for {member_db.xbox_username}",
        description=str(game_count)
    )

    await ctx.send(embed=embed)


bot.run(DISCORD_API_KEY)


try:
    loop.run_forever()
except KeyboardInterrupt:
    pass
finally:
    destiny.close()
    database.close()
loop.close()
