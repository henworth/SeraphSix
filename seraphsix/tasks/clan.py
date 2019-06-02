import asyncio
import jsonpickle
import logging

from peewee import DoesNotExist
from seraphsix import constants
from seraphsix.models.destiny import Member

logging.getLogger(__name__)


async def sort_members(database, member_list):
    clans = {}
    for member_hash in member_list:
        clan_id, platform_id, member_id = map(int, member_hash.split('-'))

        member_db = await database.get_member_by_naive_id(member_id)
        if platform_id == constants.PLATFORM_BLIZ:
            username = member_db.blizzard_username
        elif platform_id == constants.PLATFORM_XBOX:
            username = member_db.xbox_username
        elif platform_id == constants.PLATFORM_PSN:
            username = member_db.psn_username

        clan_db = await database.get_clan(clan_id)
        if not clans.get(clan_db.name):
            clans[clan_db.name] = [username]
        else:
            clans[clan_db.name].append(username)

        for clan, usernames in clans.items():
            clans[clan] = sorted(usernames, key=lambda s: s.lower())

    return clans


async def get_all_members(destiny, group_id):
    group = await destiny.api.get_group_members(group_id)
    group_members = group['Response']['results']
    for member in group_members:
        yield Member(member)


async def get_bungie_members(destiny, clan_id):
    members = {}
    async for member in get_all_members(destiny, clan_id):  # pylint: disable=not-an-iterable
        members[f'{clan_id}-{member}'] = member
        # dict(
        #     bungie_id=member.memberships.bungie.id,
        #     bungie_username=member.memberships.bungie.username,
        #     join_date=member.join_date,
        #     blizzard_id=member.memberships.blizzard.id,
        #     blizzard_username=member.memberships.blizzard.username,
        #     psn_id=member.memberships.psn.id,
        #     psn_username=member.memberships.psn.username,
        #     xbox_id=member.memberships.xbox.id,
        #     xbox_username=member.memberships.xbox.username,
        #     platform_id=member.platform_id
        # )
    return members


async def get_database_members(database, clan_id):
    members = {}
    for member in await database.get_clan_members(clan_id):
        if member.clanmember.platform_id == constants.PLATFORM_BLIZ:
            member_id = member.blizzard_id
        elif member.clanmember.platform_id == constants.PLATFORM_XBOX:
            member_id = member.xbox_id
        elif member.clanmember.platform_id == constants.PLATFORM_PSN:
            member_id = member.psn_id
        member_hash = f'{clan_id}-{member.clanmember.platform_id}-{member_id}'
        members[member_hash] = member
    return members


async def member_sync(database, destiny, guild_id, loop, cache=None):
    member_changes = {'added': [], 'removed': [], 'changed': []}
    clan_dbs = await database.get_clans_by_guild(guild_id)

    bungie_members = {}
    db_members = {}

    bungie_tasks = []
    db_tasks = []

    # Generate a dict of all members from both Bungie and the database
    for clan_db in clan_dbs:
        clan_id = clan_db.clan_id
        bungie_tasks.append(get_bungie_members(destiny, clan_id))
        db_tasks.append(get_database_members(database, clan_id))

    results = await asyncio.gather(*bungie_tasks, *db_tasks, loop=loop)

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
            member_db = await database.create_member(member_info)

        await database.create_clan_member(
            member_db,
            clan_id,
            join_date=member_info.join_date,
            platform_id=member_info.platform_id,
            is_active=True,
            member_type=member_info.member_type,
            last_active=member_info.last_online_status_change
        )

    # Figure out if there are any members to remove
    members_removed = db_member_set - bungie_member_set
    for member_hash in members_removed:
        clan_id, platform_id, member_id = map(int, member_hash.split('-'))
        try:
            member_db = await database.get_member_by_platform(member_id, platform_id)
        except DoesNotExist:
            logging.info(member_id)
            continue
        clanmember_db = await database.get_clan_member(member_db.id)
        await database.delete(clanmember_db)

    # Figure out if any usernames of existing users have been changed
    # members_changed = []
    # for member_id in db_member_set:
    #     member_db = await database.get_member_by_platform(*member_id.split('-'))

    #     bungie_xbox_username = bungie_members[member_id]['xbox_username']
    #     database_xbox_username = member_db.xbox_username
    #     if bungie_xbox_username != database_xbox_username:
    #         members_changed.append(member_xbox_id)
    #         member_db.xbox_username = bungie_xbox_username
    #         await database.update(member_db)

    #     bungie_xbox_username = bungie_members[member_id]['xbox_username']
    #     database_xbox_username = member_db.xbox_username
    #     if bungie_xbox_username != database_xbox_username:
    #         members_changed.append(member_xbox_id)
    #         member_db.xbox_username = bungie_xbox_username
    #         await database.update(member_db)

    #     bungie_xbox_username = bungie_members[member_id]['xbox_username']
    #     database_xbox_username = member_db.xbox_username
    #     if bungie_xbox_username != database_xbox_username:
    #         members_changed.append(member_xbox_id)
    #         member_db.xbox_username = bungie_xbox_username
    #         await database.update(member_db)

    if cache:
        members = [
            jsonpickle.encode(member)
            for member in await database.get_clan_members_by_guild_id(guild_id)
        ]
        cache.put('members', members)

    if len(members_added) > 0:
        member_changes['added'] = await sort_members(database, members_added)
        logging.info(f"Added members {member_changes['added']}")

    if len(members_removed) > 0:
        member_changes['removed'] = await sort_members(database, members_removed)
        logging.info(f"Removed members {member_changes['removed']}")

    # if len(members_changed) > 0:
    #     member_changes['changed'] = await sort_members(database, members_changed)
    #     logging.info(f"Changed members {member_changes['changed']}")

    return member_changes
