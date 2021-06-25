import asyncio
import logging

from seraphsix import constants
from seraphsix.cogs.utils.message_manager import MessageManager
from seraphsix.errors import InvalidAdminError
from seraphsix.models.database import Member as MemberDb, ClanMember, Clan, ClanMemberApplication
from seraphsix.models.destiny import (
    Member, DestinyGroupMembersResponse, DestinyMembershipResponse, DestinyGroupResponse
)
from seraphsix.tasks.core import execute_pydest, execute_pydest_auth, get_primary_membership

log = logging.getLogger(__name__)


async def sort_members(database, member_list):
    return_list = []
    for member_hash in member_list:
        _, platform_id, member_id = map(int, member_hash.split('-'))

        member_db = await database.get_member_by_platform(member_id, platform_id)
        if platform_id == constants.PLATFORM_XBOX:
            username = member_db.xbox_username
        elif platform_id == constants.PLATFORM_PSN:
            username = member_db.psn_username
        elif platform_id == constants.PLATFORM_BLIZZARD:
            username = member_db.blizzard_username
        elif platform_id == constants.PLATFORM_STEAM:
            username = member_db.steam_username
        elif platform_id == constants.PLATFORM_STADIA:
            username = member_db.stadia_username

        return_list.append(username)

    return sorted(return_list, key=lambda s: s.lower())


async def get_all_members(destiny, group_id):
    group = await execute_pydest(
        destiny.api.get_members_of_group, group_id, return_type=DestinyGroupMembersResponse)
    group_members = group.response.results
    for member in group_members:
        profile = await execute_pydest(
            destiny.api.get_membership_data_by_id, member.destiny_user_info.membership_id,
            return_type=DestinyMembershipResponse
        )
        yield Member(member, profile.response)


async def get_bungie_members(destiny, clan_id):
    members = {}
    async for member in get_all_members(destiny, clan_id):  # pylint: disable=not-an-iterable
        members[f'{clan_id}-{member}'] = member
    return members


async def get_database_members(database, clan_id):
    members = {}
    for clanmember in await database.get_clan_members([clan_id]):
        if clanmember.platform_id == constants.PLATFORM_XBOX:
            member_id = clanmember.member.xbox_id
        elif clanmember.platform_id == constants.PLATFORM_PSN:
            member_id = clanmember.member.psn_id
        elif clanmember.platform_id == constants.PLATFORM_BLIZZARD:
            member_id = clanmember.member.blizzard_id
        elif clanmember.platform_id == constants.PLATFORM_STEAM:
            member_id = clanmember.member.steam_id
        elif clanmember.platform_id == constants.PLATFORM_STADIA:
            member_id = clanmember.member.stadia_id
        member_hash = f'{clan_id}-{clanmember.platform_id}-{member_id}'
        members[member_hash] = clanmember
    return members


async def member_sync(ctx, guild_id, guild_name):
    clan_dbs = await ctx['database'].get_clans_by_guild(guild_id)
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
        bungie_tasks.append(get_bungie_members(ctx['destiny'], clan_id))
        db_tasks.append(get_database_members(ctx['database'], clan_id))

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
    member_added_dbs = []
    members_added = bungie_member_set - db_member_set
    for member_hash in members_added:
        member_info = bungie_members[member_hash]
        clan_id, platform_id, member_id = map(int, member_hash.split('-'))
        member_db = await ctx['database'].get_member_by_platform(member_id, platform_id)
        if not member_db:
            member_db = await MemberDb.create(**member_info.to_dict())

        clan_db = await Clan.get(clan_id=clan_id)
        member_details = dict(
            join_date=member_info.join_date,
            platform_id=member_info.platform_id,
            is_active=True,
            member_type=member_info.member_type,
            last_active=member_info.last_online_status_change
        )

        await ClanMember.create(
            clan=clan_db, member=member_db, **member_details
        )

        member_added_dbs.append(member_db)
        member_changes[clan_db.clan_id]['added'].append(member_hash)

    # Figure out if there are any members to remove
    members_removed = db_member_set - bungie_member_set
    for member_hash in members_removed:
        clan_id, platform_id, member_id = map(int, member_hash.split('-'))
        member_db = await ctx['database'].get_member_by_platform(member_id, platform_id)
        if not member_db:
            continue
        await ClanMember.filter(member=member_db).delete()
        member_changes[clan_db.clan_id]['removed'].append(member_hash)

    # Ensure we bust the member cache before queueing jobs
    # TODO: Until Tortoise has deserialization support, this has to stay disabled
    # await set_cached_members(ctx, guild_id, guild_name)

    for clan_id, changes in member_changes.items():
        if len(changes['added']):
            # Kick off activity scans for each of the added members
            for member_db in member_added_dbs:
                await ctx['redis_jobs'].enqueue_job(
                    'store_member_history', member_db.id, guild_id, guild_name, full_sync=True,
                    _job_id=f'store_member_history-{member_db.id}')

            changes['added'] = await sort_members(ctx['database'], changes['added'])
            log.info(f"Added members {changes['added']} to clan id {clan_id}")
        if len(changes['removed']):
            changes['removed'] = await sort_members(ctx['database'], changes['removed'])
            log.info(f"Removed members {changes['removed']} from clan id {clan_id}")

    return member_changes


async def info_sync(ctx, guild_id):
    clan_dbs = await ctx['database'].get_clans_by_guild(guild_id)

    clan_changes = {}
    for clan_db in clan_dbs:
        group = await execute_pydest(ctx['destiny'].api.get_group, clan_db.clan_id, return_type=DestinyGroupResponse)
        bungie_name = group.response.detail.name
        bungie_callsign = group.response.detail.clan_info.clan_callsign
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

        await clan_db.save()

    return clan_changes


async def ack_clan_application(ctx, payload):
    is_approved = payload.emoji.name == constants.EMOJI_CHECKMARK
    approver_id = payload.user_id
    message_id = payload.message_id
    approver_user = payload.member
    guild = approver_user.guild

    application_db = await ClanMemberApplication.get_or_none(
        message_id=message_id, approved=False
    ).prefetch_related("member")
    if not application_db:
        log.debug(f"Application not found for {payload}")
        return

    approver_db = await ClanMember.get_or_none(
        member_type__gte=constants.CLAN_MEMBER_ADMIN, member__discord_id=approver_id
    ).prefetch_related("member", "clan")
    if not approver_db:
        raise InvalidAdminError

    application_db.approved = is_approved
    application_db.approved_by_id = approver_db.member.id

    admin_channel = ctx.get_channel(ctx.guild_map[payload.guild_id].admin_channel)
    applicant_user = guild.get_member(application_db.member.discord_id)
    if is_approved:
        ack_message = "Approved"
    else:
        ack_message = "Denied"

    admin_message = await admin_channel.send(
        f"Application for {applicant_user.display_name} was {ack_message} by {approver_user.display_name}."
    )
    await applicant_user.send(
        f"Your application to join {approver_db.clan.name} has been {ack_message}."
    )

    if is_approved:
        admin_context = await ctx.get_context(admin_message)
        manager = MessageManager(admin_context)

        platform_id, membership_id, username = get_primary_membership(
            application_db.member
        )

        res = await execute_pydest_auth(
            ctx.ext_conns,
            ctx.ext_conns["destiny"].api.group_invite_member,
            approver_db.member,
            manager,
            group_id=approver_db.clan.clan_id,
            membership_type=platform_id,
            membership_id=membership_id,
            message=f"Join my clan {approver_db.clan.name}!",
            access_token=approver_db.member.bungie_access_token,
        )

        if res.error_status == "ClanTargetDisallowsInvites":
            message = f"User **{applicant_user.display_name}** ({username}) has disabled clan invites"
        elif res.error_status != "Success":
            message = f"Could not invite **{applicant_user.display_name}** ({username})"
            log.info(
                f"Could not invite '{applicant_user.display_name}' ({username}): {res}"
            )
        else:
            message = (
                f"Invited **{applicant_user.display_name}** ({username}) "
                f"to clan **{approver_db.clan.name}**"
            )

        await manager.send_message(message, mention=False, clean=False)

    await application_db.save()

    await ctx.ext_conns["redis_cache"].delete(
        f"{payload.guild_id}-clan-application-{application_db.member_id}"
    )
