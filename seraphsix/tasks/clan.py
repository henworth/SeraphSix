import asyncio
# import jsonpickle
import logging

from peewee import DoesNotExist
from seraphsix import constants
from seraphsix.database import Member as MemberDb, ClanMember, Clan
from seraphsix.models.destiny import Member

logging.getLogger(__name__)


async def sort_members(database, member_list):
    return_list = []
    for member_hash in member_list:
        clan_id, platform_id, member_id = map(int, member_hash.split('-'))

        member_db = await database.get_member_by_platform(member_id, platform_id)
        if platform_id == constants.PLATFORM_BLIZ:
            username = member_db.blizzard_username
        elif platform_id == constants.PLATFORM_XBOX:
            username = member_db.xbox_username
        elif platform_id == constants.PLATFORM_PSN:
            username = member_db.psn_username

        return_list.append(username)

    return sorted(return_list, key=lambda s: s.lower())


async def get_all_members(destiny, group_id):
    group = await destiny.api.get_group_members(group_id)
    group_members = group['Response']['results']
    for member in group_members:
        yield Member(member)


async def get_bungie_members(destiny, clan_id):
    members = {}
    async for member in get_all_members(destiny, clan_id):  # pylint: disable=not-an-iterable
        members[f'{clan_id}-{member}'] = member
    return members


async def get_database_members(database, clan_id):
    members = {}
    for member in await database.get_clan_members([clan_id]):
        if member.clanmember.platform_id == constants.PLATFORM_BLIZ:
            member_id = member.blizzard_id
        elif member.clanmember.platform_id == constants.PLATFORM_XBOX:
            member_id = member.xbox_id
        elif member.clanmember.platform_id == constants.PLATFORM_PSN:
            member_id = member.psn_id
        member_hash = f'{clan_id}-{member.clanmember.platform_id}-{member_id}'
        members[member_hash] = member
    return members


async def member_sync(database, destiny, guild_id):  # noqa
    clan_dbs = await database.get_clans_by_guild(guild_id)
    member_changes = {}
    for clan_db in clan_dbs:
        member_changes[clan_db.clan_id] = {'added': [], 'removed': [], 'changed': []}

    bungie_members = {}
    db_members = {}

    bungie_tasks = []
    db_tasks = []

    # Generate a dict of all members from both Bungie and the database
    for clan_db in clan_dbs:
        clan_id = clan_db.clan_id
        bungie_tasks.append(get_bungie_members(destiny, clan_id))
        db_tasks.append(get_database_members(database, clan_id))

    results = await asyncio.gather(*bungie_tasks, *db_tasks)

    # All Bungie results would be in the first half of the results
    for result in results[:len(results)//2]:
        bungie_members.update(result)

    # All database results are in the second half
    for result in results[len(results)//2:]:
        db_members.update(result)

    bungie_member_set = set(
        [member for member in bungie_members.keys()]
    )

    db_member_set = set(
        [member for member in db_members.keys()]
    )

    # Figure out if there are any members to add
    members_added = bungie_member_set - db_member_set
    for member_hash in members_added:
        member_info = bungie_members[member_hash]
        clan_id, platform_id, member_id = map(int, member_hash.split('-'))
        try:
            member_db = await database.get_member_by_platform(member_id, platform_id)
        except DoesNotExist:
            member_db = await database.create(MemberDb, **member_info.to_dict())

        clan_db = await database.get(Clan, clan_id=clan_id)
        member_details = dict(
            join_date=member_info.join_date,
            platform_id=member_info.platform_id,
            is_active=True,
            member_type=member_info.member_type,
            last_active=member_info.last_online_status_change
        )

        await database.create(
            ClanMember, clan=clan_db, member=member_db, **member_details)

        member_changes[clan_db.clan_id]['added'].append(member_hash)

    # Figure out if there are any members to remove
    members_removed = db_member_set - bungie_member_set
    for member_hash in members_removed:
        clan_id, platform_id, member_id = map(int, member_hash.split('-'))
        try:
            member_db = await database.get_member_by_platform(member_id, platform_id)
        except DoesNotExist:
            logging.info(member_id)
            continue
        clanmember_db = await database.get(ClanMember, member_id=member_db.id)
        await database.delete(clanmember_db)
        member_changes[clan_db.clan_id]['removed'].append(member_hash)

    for clan, changes in member_changes.items():
        if len(changes['added']):
            changes['added'] = await sort_members(database, changes['added'])
            logging.info(f"Added members {changes['added']}")
        if len(changes['removed']):
            changes['removed'] = await sort_members(database, changes['removed'])
            logging.info(f"Removed members {changes['removed']}")

    return member_changes


async def info_sync(database, destiny, guild_id):
    clan_dbs = await database.get_clans_by_guild(guild_id)

    clan_changes = {}
    for clan_db in clan_dbs:
        res = await destiny.api.get_group(clan_db.clan_id)
        group = res['Response']
        bungie_name = group['detail']['name']
        bungie_callsign = group['detail']['clanInfo']['clanCallsign']
        original_name = clan_db.name
        original_callsign = clan_db.callsign

        if clan_db.name != bungie_name:
            clan_changes[clan_db.clan_id] = {'name': {'from': original_name, 'to': bungie_name}}
            clan_db.name = bungie_name

        if clan_db.callsign != bungie_callsign:
            if not clan_changes.get(clan_db.clan_id):
                clan_changes.update(
                    {clan_db.clan_id: {'callsign': {'from': original_callsign, 'to': bungie_callsign}}})
            else:
                clan_changes[clan_db.clan_id]['callsign'] = {'from': original_callsign, 'to': bungie_callsign}
            clan_db.callsign = bungie_callsign

        await database.update(clan_db)

    return clan_changes
