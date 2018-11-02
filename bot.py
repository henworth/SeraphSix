#!/usr/bin/env python3.7
import asyncio
import discord
import logging
import os
import pydest

from discord.errors import HTTPException
from discord.ext.commands import Bot, UserConverter 
from discord.ext.commands.errors import BadArgument, CommandNotFound, CommandInvokeError

from peewee import DoesNotExist

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
async def link(ctx, xbox_username: str, discord_username: str=None):
    if not discord_username:
        discord_username = str(ctx.message.author)

    try:
        member_discord = await UserConverter().convert(ctx, discord_username)
    except BadArgument as e:
        await ctx.send(e)
        return

    async with ctx.typing():
        member_db = await database.get_member(xbox_username)
        member_db.discord_id = member_discord.id
        await database.update_member(member_db)
        await ctx.send(f"Linked Gamertag {xbox_username} to Discord user {discord_username}")


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
            bungie_members[member.xbox_username] = member

        bungie_member_set = set(
            [member for member in bungie_members.keys()]
        )

        db_members = {}
        for member in await database.get_members():
            db_members[member.xbox_username] = member

        db_member_set = set(
            [member for member in db_members.keys()]
        )

        new_members = bungie_member_set - db_member_set
        purged_members = db_member_set - bungie_member_set

        for member in new_members:
            await database.create_member(bungie_members[member].__dict__)

        for member in purged_members:
            member_db = db_members[member]
            member_db.is_active = False
            await database.update_member(member_db)

    embed = discord.Embed(
        title="Membership Changes"
    )

    if len(new_members) > 0:
        added = sorted(new_members, key=lambda s: s.lower())
        embed.add_field(name="Members Added", value=', '.join(added), inline=False)

    if len(purged_members) > 0:
        purged = sorted(purged_members, key=lambda s: s.lower())
        embed.add_field(name="Members Purged", value=', '.join(purged), inline=False)

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
async def games(ctx, game_mode: str, member_name: str=None):
    game_modes = ['gambit', 'raid', 'pvp-quick', 'pvp-comp', 'pvp']

    if not member_name:
        member_name = str(ctx.message.author).split('#')[0]

    if game_mode not in game_modes:
        await ctx.send(f"Invalid game mode `{game_mode}`, supported are `{', '.join(game_modes)}`")
        return

    try:
        await database.get_member(member_name)
    except DoesNotExist:
        await ctx.send(f"Invalid member name {member_name}")
        return

    async with ctx.typing():
        game_count = await get_member_history(database, destiny, member_name, game_mode)

    embed = discord.Embed(
        title=f"Eligible {game_mode.capitalize()} Games for {member_name}", 
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