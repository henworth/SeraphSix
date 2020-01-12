import discord
import logging

from peewee import DoesNotExist
from seraphsix.database import Clan, ClanMember, Guild, Member, Role

logging.getLogger(__name__)


async def find_sherpas(bot, guild):
    sherpas = []
    query = Role.select().join(Guild).where((Guild.id == guild.id) & (Role.is_sherpa))
    roles = await bot.database.execute(query)

    guild_obj = bot.get_guild(guild.guild_id)
    for role in roles:
        role_obj = discord.utils.get(guild_obj.roles, id=role.role_id)
        sherpas.extend(role_obj.members)
    return sherpas


async def store_sherpas(bot, guild):
    sherpas_discord = await find_sherpas(bot, guild)
    sherpas_discord_ids = [sherpa.id for sherpa in sherpas_discord]

    query = Member.select(Member.discord_id).join(ClanMember).join(Clan).join(Guild).where(
        (ClanMember.is_sherpa) & (Guild.id == guild.id)
    )
    sherpas_db = await bot.database.execute(query)
    sherpas_db_ids = [sherpa_db.discord_id for sherpa_db in sherpas_db]

    discord_set = set(sherpas_discord_ids)
    db_set = set(sherpas_db_ids)

    sherpas_added = list(discord_set - db_set)
    sherpas_removed = list(db_set - discord_set)

    base_member_query = ClanMember.select(ClanMember.id).join(Member)
    if sherpas_added:
        logging.info(f"Sherpas added for {guild.guild_id}: {sherpas_added}")
        members = base_member_query.where(Member.discord_id << sherpas_added)
        query = ClanMember.update(is_sherpa=True).from_(members).where(ClanMember.id << members)
        await bot.database.execute(query)

    if sherpas_removed:
        logging.info(f"Sherpas removed for {guild.guild_id}: {sherpas_removed}")
        members = base_member_query.where(Member.discord_id << sherpas_removed)
        query = ClanMember.update(is_sherpa=False).from_(members).where(ClanMember.id << members)
        await bot.database.execute(query)


async def update_sherpa(bot, before, after):
    role_ids = set([role.id for role in after.roles])

    roles_query = Role.select(Role).join(Guild).where(
        (Guild.guild_id == after.guild.id) & (Role.is_sherpa)
    )
    roles_db = await bot.database.execute(roles_query)
    role_db_ids = set([role.role_id for role in roles_db])

    try:
        member_query = ClanMember.select(ClanMember).join(Member).where(Member.discord_id == after.id)
        member_db = await bot.database.get(member_query)
    except DoesNotExist:
        return

    if role_ids.intersection(role_db_ids):
        member_db.is_sherpa = True
    else:
        member_db.is_sherpa = False
    await bot.database.update(member_db)
