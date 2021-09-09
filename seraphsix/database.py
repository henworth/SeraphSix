import asyncio
import logging

from datetime import timedelta
from seraphsix import constants
from seraphsix.tasks.parsing import member_hash
from seraphsix.models.database import (
    Member,
    Clan,
    ClanMember,
    GameMember,
    Game,
    ClanGame,
)

from urllib.parse import urlparse

from tortoise import Tortoise
from tortoise.exceptions import IntegrityError
from tortoise.functions import Lower
from tortoise.query_utils import Q
from tortoise import timezone

log = logging.getLogger(__name__)


class Database(object):
    def __init__(self, url, max_connections=constants.DB_MAX_CONNECTIONS):
        self.url = urlparse(url)
        self.max_size = max_connections

    async def initialize(self):
        await Tortoise.init(
            config={
                "connections": {
                    "default": {
                        "engine": "tortoise.backends.asyncpg",
                        "credentials": {
                            "host": self.url.hostname,
                            "port": self.url.port,
                            "user": self.url.username,
                            "password": self.url.password,
                            "database": self.url.path[1:],
                            "max_size": self.max_size,
                        },
                    }
                },
                "apps": {
                    "seraphsix": {
                        "models": ["seraphsix.models.database"],
                    }
                },
            }
        )

    async def get_member_by_platform(self, member_id, platform_id):
        if platform_id == constants.PLATFORM_BUNGIE:
            query = Member.get_or_none(bungie_id=member_id)
        elif platform_id == constants.PLATFORM_PSN:
            query = Member.get_or_none(psn_id=member_id)
        elif platform_id == constants.PLATFORM_XBOX:
            query = Member.get_or_none(xbox_id=member_id)
        elif platform_id == constants.PLATFORM_BLIZZARD:
            query = Member.get_or_none(blizzard_id=member_id)
        elif platform_id == constants.PLATFORM_STEAM:
            query = Member.get_or_none(steam_id=member_id)
        elif platform_id == constants.PLATFORM_STADIA:
            query = Member.get_or_none(stadia_id=member_id)
        return await query

    async def get_member_by_naive_username(self, username, include_clan=True):
        username = username.lower()

        if include_clan:
            member_db = (
                await ClanMember.annotate(
                    bungie_username_lo=Lower("member__bungie_username"),
                    xbox_username_lo=Lower("member__xbox_username"),
                    psn_username_lo=Lower("member__psn_username"),
                    blizzard_username_lo=Lower("member__blizzard_username"),
                    steam_username_lo=Lower("member__steam_username"),
                    stadia_username_lo=Lower("member__stadia_username"),
                )
                .get_or_none(
                    Q(bungie_username_lo=username)
                    | Q(xbox_username_lo=username)
                    | Q(psn_username_lo=username)
                    | Q(blizzard_username_lo=username)
                    | Q(steam_username_lo=username)
                    | Q(stadia_username_lo=username)
                )
                .prefetch_related("clan", "member")
            )
        else:
            member_db = await Member.annotate(
                bungie_username_lo=Lower("bungie_username"),
                xbox_username_lo=Lower("xbox_username"),
                psn_username_lo=Lower("psn_username"),
                blizzard_username_lo=Lower("blizzard_username"),
                steam_username_lo=Lower("steam_username"),
                stadia_username_lo=Lower("stadia_username"),
            ).get_or_none(
                Q(bungie_username_lo=username)
                | Q(xbox_username_lo=username)
                | Q(psn_username_lo=username)
                | Q(blizzard_username_lo=username)
                | Q(steam_username_lo=username)
                | Q(stadia_username_lo=username)
            )

        return member_db

    async def create_member_by_platform(self, name, membership_id, platform_id):
        # pylint: disable=assignment-from-no-return
        query = Member.create()
        if platform_id == constants.PLATFORM_BUNGIE:
            query = Member.create(name=name, bungie_id=membership_id)
        elif platform_id == constants.PLATFORM_PSN:
            query = Member.create(name=name, psn_id=membership_id)
        elif platform_id == constants.PLATFORM_XBOX:
            query = Member.create(name=name, xbox_id=membership_id)
        elif platform_id == constants.PLATFORM_BLIZZARD:
            query = Member.create(name=name, blizzard_id=membership_id)
        elif platform_id == constants.PLATFORM_STEAM:
            query = Member.create(name=name, steam_id=membership_id)
        elif platform_id == constants.PLATFORM_STADIA:
            query = Member.create(name=name, stadia_id=membership_id)
        return await query

    async def get_member_by_platform_username(self, username, platform_id):
        username = username.lower()

        if platform_id == constants.PLATFORM_BUNGIE:
            username_field = "bungie_username"
        elif platform_id == constants.PLATFORM_PSN:
            username_field = "psn_username"
        elif platform_id == constants.PLATFORM_XBOX:
            username_field = "xbox_username"
        elif platform_id == constants.PLATFORM_BLIZZARD:
            username_field = "blizzard_username"
        elif platform_id == constants.PLATFORM_STEAM:
            username_field = "steam_username"
        elif platform_id == constants.PLATFORM_STADIA:
            username_field = "stadia_username"

        query = (
            await Member.annotate(name_lo=Lower(username_field))
            .get_or_none(name_lo=username)
            .prefetch_related("clans")
        )
        return query

    async def get_member_by_discord_id(self, discord_id, include_clan=True):
        if include_clan:
            query = ClanMember.get_or_none(
                member__discord_id=discord_id
            ).prefetch_related("member", "clan")
        else:
            query = Member.get_or_none(discord_id=discord_id)
        return await query

    async def get_clan_members(self, clan_ids):
        return await ClanMember.filter(clan__clan_id__in=clan_ids).prefetch_related(
            "member", "clan"
        )

    async def get_clan_members_by_guild_id(self, guild_id):
        return await ClanMember.filter(clan__guild__guild_id=guild_id).prefetch_related(
            "member", "clan", "clan__guild"
        )

    async def get_clan_member_by_platform(self, member_id, platform_id, clan_ids):
        if platform_id == constants.PLATFORM_PSN:
            query = ClanMember.get(clan_id__in=clan_ids, member__psn_id=member_id)
        elif platform_id == constants.PLATFORM_XBOX:
            query = ClanMember.get(clan_id__in=clan_ids, member__xbox_id=member_id)
        elif platform_id == constants.PLATFORM_BLIZZARD:
            query = ClanMember.get(clan_id__in=clan_ids, member__blizzard_id=member_id)
        elif platform_id == constants.PLATFORM_STEAM:
            query = ClanMember.get(clan_id__in=clan_ids, member__steam_id=member_id)
        elif platform_id == constants.PLATFORM_STADIA:
            query = ClanMember.get(clan_id__in=clan_ids, member__stadia_id=member_id)
        return await query.prefetch_related("member")

    async def get_clans_by_guild(self, guild_id):
        return await Clan.filter(guild__guild_id=guild_id).prefetch_related("guild")

    async def get_clan_members_active(self, clan_db, **kwargs):
        if not kwargs:
            kwargs = dict(hours=1)
        return await ClanMember.filter(
            last_active__gt=timezone.now() - timedelta(**kwargs), clan=clan_db
        ).prefetch_related("member")

    async def get_clan_members_inactive(self, clan_db, **kwargs):
        if not kwargs:
            kwargs = dict(days=30)
        return await ClanMember.filter(
            last_active__lt=timezone.now() - timedelta(**kwargs), clan=clan_db
        ).prefetch_related("member")

    async def create_game(self, game):
        game_db = await Game.create(**vars(game))
        log.info(f"Game {game_db.instance_id} created")
        return game_db

    async def create_clan_game(self, game_db, game, clan_id):
        data = dict(clan_id=clan_id, game=game_db)
        _, is_created = await ClanGame.get_or_create(**data)
        if is_created:
            tasks = [
                self.create_game_member(player, game_db, clan_id)
                for player in game.clan_players
            ]
            await asyncio.gather(*tasks)

    async def create_game_member(self, player, game_db, clan_id, player_db=None):
        if not player_db:
            clanmember_db = await self.get_clan_member_by_platform(
                player.membership_id, player.membership_type, [clan_id]
            )
            player_db = clanmember_db.member
        try:
            # Create the game member
            await GameMember.create(
                member=player_db,
                game=game_db,
                completed=player.completed,
                time_played=player.time_played,
            )
        except IntegrityError:
            # If one already exists, we can assume this is due to a drop/re-join event so
            # increment the time played and set the completion flag
            game_member_db = await GameMember.get(game=game_db, member=player_db)
            game_member_db.time_played += player.time_played

            if (
                not game_member_db.completed
                or game_member_db.completed != player.completed
            ):
                game_member_db.completed = player.completed
            await game_member_db.save()

        log.info(
            f"Player {member_hash(player)} created in game id {game_db.instance_id}"
        )

    async def close(self):
        await Tortoise.close_connections()
