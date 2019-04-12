#!/usr/bin/env python3.7
import ast
import asyncio
import discord
import logging
import os
import pydest
import pytz

from datetime import datetime

from discord.errors import HTTPException
from discord.ext.commands import Bot, MemberConverter
from discord.ext.commands.errors import BadArgument, CommandNotFound, CommandInvokeError
from iron_cache import IronCache
from peewee import DoesNotExist

from bot_activity import get_member_history, store_member_history
from constants import *
from database import Database, Member
from members import get_all

logging.basicConfig(level=logging.INFO)
logging.getLogger('aiohttp.client').setLevel(logging.ERROR)

loop = asyncio.new_event_loop()
bot = Bot(loop=loop, command_prefix='?')
database = Database(DATABASE_URL, loop=loop)
database.initialize()

cache = IronCache(name='bot', project_id=CACHE_PROJECT_ID, token=CACHE_TOKEN)

destiny = pydest.Pydest(BUNGIE_API_KEY, loop=loop)


async def store_all_games(game_mode: str):
    while True:
        logging.info(f"background: Finding all {game_mode} games for all members")
        members = ast.literal_eval(cache.get('members').value)
        for member in members:
            count = await store_member_history(database, destiny, member, game_mode)
            logging.info(f"background: Found {count} {game_mode} games for {member}")
        logging.info(f"background: Found all {game_mode} games for all members")
        await asyncio.sleep(3600)


@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user.name} ({bot.user.id})")
    logging.info(f"Invite: https://discordapp.com/oauth2/authorize?client_id={bot.user.id}&scope=bot")
    try:
        members = cache.get('members')
    except Exception:
        members = [member.xbox_username for member in await database.get_members()]
        cache.put('members', members)
    bot.loop.create_task(store_all_games('raid'))
    bot.loop.create_task(store_all_games('gambit'))
    bot.loop.create_task(store_all_games('pvp'))
    bot.loop.create_task(store_all_games('strike'))


@bot.command()
async def greet(ctx):
    await ctx.send(":wave: Hello, there! :smiley:")


@bot.group()
async def member(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send(f"Invalid command `{ctx.message.content}`")

@member.command()
async def info(ctx, *args):
    member_name = ' '.join(args)

    if not member_name:
        member_name = ctx.message.author

    try:
        member_discord = await MemberConverter().convert(ctx, str(member_name))
    except Exception:
        return

    async with ctx.typing():
        try:
            member_db = await database.get_member_by_discord(member_discord.id)
        except DoesNotExist:
            await ctx.send(f"Discord username \"{member_name}\" does not match a valid member")
            return
        member_discord = await MemberConverter().convert(ctx, str(member_discord.id))

    the100_link = None
    if member_db.the100_username:
        the100_link = f"[{member_db.the100_username}](https://www.the100.io/users/{member_db.the100_username})"

    bungie_link = None
    if member_db.bungie_id:
        bungie_info = await destiny.api.get_membership_data_by_id(member_db.bungie_id)
        membership_info = bungie_info['Response']['destinyMemberships'][0]
        bungie_member_id = membership_info['membershipId']
        bungie_member_type = membership_info['membershipType']
        bungie_member_name = membership_info['displayName']
        bungie_link = f"[{bungie_member_name}](https://www.bungie.net/en/Profile/{bungie_member_type}/{bungie_member_id})"

    timezone = None
    if member_db.timezone:
        timezone = datetime.now(pytz.timezone(member_db.timezone)).strftime('UTC%z')

    embed = discord.Embed(
        title=f"Member Info for {member_discord.display_name}"   
    )
    embed.add_field(name="Xbox Gamertag", value=member_db.xbox_username)
    embed.add_field(name="Discord Username", value=f"{member_discord.name}#{member_discord.discriminator}")
    embed.add_field(name="Bungie Username", value=bungie_link)
    embed.add_field(name="The100 Username", value=the100_link)
    embed.add_field(name="Join Date", value=member_db.join_date.strftime('%Y-%m-%d %H:%M:%S'))
    embed.add_field(name="Time Zone", value=timezone)

    await ctx.send(embed=embed)

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
        member_discord = await MemberConverter().convert(ctx, discord_username)
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
            member_discord = await MemberConverter().convert(ctx, str(member_db.discord_id))
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
        member_discord = await MemberConverter().convert(ctx, str(ctx.message.author))
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
            member_discord = await MemberConverter().convert(ctx, str(member_db.discord_id))
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
                member_db = await database.get_member_by_bungie(member_bungie_id)
            except DoesNotExist:
                await database.create_member(bungie_members[member_bungie_id].__dict__)
            
            if not member_db.is_active:
                try:
                    member_db.is_active = True
                    member_db.join_date = bungie_members[member_bungie_id].join_date
                    await database.update_member(member_db)
                except Exception:
                    logging.exception(f"Could update member \"{member_db.xbox_username}\"")
                    return

        for member in purged_members:
            member_db = db_members[member]
            member_db.is_active = False
            await database.update_member(member_db)

        members = [member.xbox_username for member in await database.get_members()]
        cache.put('members', members)

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

    game_modes = ['gambit', 'raid', 'pvp-quick', 'pvp-comp', 'pvp', 'strike']
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
            logging.info(f"Getting {game_mode} games by Discord id {discord_id} for {ctx.author.display_name}")
        else:
            try:
                member_db = await database.get_member(member_name)
            except DoesNotExist:
                await ctx.send(f"Invalid member name {member_name}")
                return
            logging.info(f"Getting {game_mode} games by Gamertag {member_name} for {ctx.author.display_name}")

        game_counts = await get_member_history(database, destiny, member_db.xbox_username, game_mode)

    embed = discord.Embed(
        title=f"Eligible {game_mode.title()} Games for {member_db.xbox_username}",
    )

    total_count = 0
    for game, count in game_counts.items():
        embed.add_field(name=game.title(), value=str(count))
        total_count += count

    embed.description=str(total_count)

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
