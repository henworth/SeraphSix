import discord
import logging

from tortoise.expressions import Subquery

from seraphsix.models.database import ClanMember, Guild, Role


log = logging.getLogger(__name__)


async def convert_sherpas(bot, sherpas):
    for sherpa in sherpas:
        yield await bot.fetch_user(sherpa)


async def find_sherpas(bot, guild):
    sherpas = []
    guild_obj = bot.get_guild(guild.guild_id)
    for role in await Role.filter(guild_id=guild.id, is_sherpa=True).all():
        role_obj = discord.utils.get(guild_obj.roles, id=role.role_id)
        sherpas.extend(role_obj.members)
    return sherpas


async def store_sherpas(bot, guild):
    discord_guild = await bot.fetch_guild(guild.guild_id)
    sherpas_discord = await find_sherpas(bot, guild)
    sherpas_discord_ids = [sherpa.id for sherpa in sherpas_discord]

    sherpas_db = await ClanMember.filter(
        is_sherpa=True, clan__guild_id=guild.id
    ).prefetch_related('member')
    sherpas_db_ids = [sherpa_db.member.discord_id for sherpa_db in sherpas_db]

    discord_set = set(sherpas_discord_ids)
    db_set = set(sherpas_db_ids)

    sherpas_added = list(discord_set - db_set)
    sherpas_removed = list(db_set - discord_set)

    added = removed = []
    if sherpas_added:
        members = ClanMember.filter(member__discord_id__in=sherpas_added)
        await ClanMember.filter(id__in=Subquery(members)).update(is_sherpa=True)

        added = [sherpa async for sherpa in convert_sherpas(bot, sherpas_added)]
        message_added = [f"{str(sherpa)} {sherpa.id}" for sherpa in added]
        log.info(f"Sherpas added in {str(discord_guild)} ({guild.guild_id}): {message_added}")

    if sherpas_removed:
        members = ClanMember.filter(member__discord_id__in=sherpas_removed)
        await ClanMember.filter(id__in=Subquery(members)).update(is_sherpa=False)

        removed = [sherpa async for sherpa in convert_sherpas(bot, sherpas_removed)]
        message_removed = [f"{str(sherpa)} {sherpa.id}" for sherpa in removed]
        log.info(f"Sherpas removed in {str(discord_guild)} ({guild.guild_id}): {message_removed}")

    return (added, removed)


async def update_sherpa(bot, before, after):
    before_role_ids = set([role.id for role in before.roles])
    after_role_ids = set([role.id for role in after.roles])

    if before_role_ids == after_role_ids:
        return

    guild_db = await Guild.get(guild_id=after.guild.id)
    if not guild_db.track_sherpas:
        log.debug(
            f"Cannot check for sherpa role updates on user {str(after)} ({after.id}) "
            f"because sherpa tracking is disabled in {str(after.guild)} ({after.guild.id})"
        )
        return

    log.debug(
        f"Checking for sherpa role updates on user {str(after)} ({after.id}) "
        f"in {str(after.guild)} ({after.guild.id})"
    )

    roles_db = await Role.filter(
        guild__guild_id=after.guild.id, is_sherpa=True
    )
    role_db_ids = set([role.role_id for role in roles_db])

    member_db = await ClanMember.get_or_none(member__discord_id=after.id)
    if not member_db:
        log.info(
            f"Clan member for user {str(after)} ({after.id}) "
            f"in {str(after.guild)} ({after.guild.id}) not found"
        )
        return

    if not after_role_ids:
        member_is_sherpa = False
    elif after_role_ids.intersection(role_db_ids):
        member_is_sherpa = True
    else:
        member_is_sherpa = False

    if member_is_sherpa != member_db.is_sherpa:
        log.info(
            f"Sherpa role changed from {member_db.is_sherpa} to {member_is_sherpa} "
            f"for user {str(after)} ({after.id}) "
            f"in {str(after.guild)} ({after.guild.id}) "
        )
        member_db.is_sherpa = member_is_sherpa
        await member_db.save()
