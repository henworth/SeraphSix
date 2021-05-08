import asyncio
import functools
import logging
import psycopg2
import pytz

from datetime import datetime, timedelta
from peewee import (
    Model, CharField, BigIntegerField, IntegerField, FloatField,
    ForeignKeyField, Proxy, BooleanField, Check, SQL, fn, Case,
    InterfaceError, OperationalError, IntegrityError, DoesNotExist, JOIN)
from peewee_async import Manager
from peewee_asyncext import PooledPostgresqlExtDatabase
from playhouse.postgres_ext import DateTimeTZField
from seraphsix import constants
from seraphsix.tasks.parsing import member_hash
from tenacity import AsyncRetrying, RetryError, wait_exponential, before_sleep_log
from urllib.parse import urlparse

log = logging.getLogger(__name__)

database_proxy = Proxy()


def reconnect(function):
    @functools.wraps(function)
    async def wrapper(db, *args, **kwargs):
        try:
            return await function(db, *args, **kwargs)
        except (InterfaceError, OperationalError, psycopg2.InterfaceError, psycopg2.OperationalError):
            try:
                async for attempt in AsyncRetrying(
                        wait=wait_exponential(multiplier=1, min=2, max=10),
                        before_sleep=before_sleep_log(log, logging.ERROR)):
                    with attempt:
                        db._objects.database._connect()
            except RetryError:
                pass
            else:
                return await function(db, *args, **kwargs)
    return wrapper


class BaseModel(Model):
    class Meta:
        database = database_proxy


class Guild(BaseModel):
    guild_id = BigIntegerField(unique=True)
    prefix = CharField(max_length=5, null=True, default='?')
    clear_spam = BooleanField(default=False)
    aggregate_clans = BooleanField(default=True)
    track_sherpas = BooleanField(default=False)
    admin_channel = BigIntegerField(unique=True, null=True)
    announcement_channel = BigIntegerField(unique=True, null=True)


class Clan(BaseModel):
    clan_id = BigIntegerField(unique=True)
    guild = ForeignKeyField(Guild)
    name = CharField()
    callsign = CharField(max_length=4)
    platform = IntegerField(
        null=True,
        constraints=[Check(
            f"platform in ({constants.PLATFORM_XBOX}, {constants.PLATFORM_PSN}, "
            f"{constants.PLATFORM_BLIZZARD}, {constants.PLATFORM_STEAM}, {constants.PLATFORM_STADIA})"
        )]
    )
    the100_group_id = IntegerField(unique=True, null=True)
    activity_tracking = BooleanField(default=True)


class Member(BaseModel):
    discord_id = BigIntegerField(null=True)
    bungie_id = BigIntegerField(null=True)
    bungie_username = CharField(null=True)
    xbox_id = BigIntegerField(null=True)
    xbox_username = CharField(unique=True, null=True)
    psn_id = BigIntegerField(null=True)
    psn_username = CharField(unique=True, null=True)
    blizzard_id = BigIntegerField(null=True)
    blizzard_username = CharField(unique=True, null=True)
    steam_id = BigIntegerField(null=True)
    steam_username = CharField(unique=True, null=True)
    stadia_id = BigIntegerField(null=True)
    stadia_username = CharField(unique=True, null=True)
    the100_id = BigIntegerField(unique=True, null=True)
    the100_username = CharField(unique=True, null=True)
    timezone = CharField(null=True)
    bungie_access_token = CharField(max_length=360, unique=True, null=True)
    bungie_refresh_token = CharField(max_length=360, unique=True, null=True)
    is_cross_save = BooleanField(default=False)
    primary_membership_id = BigIntegerField(unique=True, null=True)

    class Meta:
        indexes = (
            (('discord_id', 'bungie_id', 'xbox_id', 'psn_id', 'blizzard_id',
              'steam_id', 'stadia_id', 'the100_id'), True),
        )


class MemberPlatform(BaseModel):
    member = ForeignKeyField(Member)
    platform_id = IntegerField()
    username = CharField(unique=True, null=True)

    class Meta:
        indexes = (
            (('member', 'platform_id'), True),
        )


class ClanMember(BaseModel):
    clan = ForeignKeyField(Clan)
    member = ForeignKeyField(Member)
    platform_id = IntegerField()
    join_date = DateTimeTZField()
    is_active = BooleanField(default=True)
    last_active = DateTimeTZField(null=True)
    is_sherpa = BooleanField(default=False)
    member_type = IntegerField(
        null=True,
        constraints=[Check(
            f"member_type in ({constants.CLAN_MEMBER_NONE}, {constants.CLAN_MEMBER_BEGINNER},"
            f"{constants.CLAN_MEMBER_MEMBER}, {constants.CLAN_MEMBER_ADMIN}, "
            f"{constants.CLAN_MEMBER_ACTING_FOUNDER}, {constants.CLAN_MEMBER_FOUNDER})"
        )]
    )


class ClanMemberApplication(BaseModel):
    guild = ForeignKeyField(Guild)
    member = ForeignKeyField(Member)
    approved = BooleanField(default=False)
    approved_by = ForeignKeyField(Member, null=True)
    message_id = BigIntegerField(unique=True)


class Game(BaseModel):
    mode_id = IntegerField()
    instance_id = BigIntegerField(unique=True)
    date = DateTimeTZField()
    reference_id = BigIntegerField(null=True)

    class Meta:
        indexes = (
            (('mode_id', 'reference_id'), False),
        )


class ClanGame(BaseModel):
    clan = ForeignKeyField(Clan)
    game = ForeignKeyField(Game)

    class Meta:
        indexes = (
            (('clan', 'game'), True),
        )


class GameMember(BaseModel):
    member = ForeignKeyField(Member)
    game = ForeignKeyField(Game)
    time_played = FloatField(null=True)
    completed = BooleanField(null=True)

    class Meta:
        indexes = (
            (('member', 'game'), True),
        )


class TwitterChannel(BaseModel):
    channel_id = BigIntegerField()
    twitter_id = BigIntegerField()
    guild_id = BigIntegerField()

    class Meta:
        indexes = (
            (('channel_id', 'twitter_id', 'guild_id'), True),
        )


class Role(BaseModel):
    guild = ForeignKeyField(Guild)
    role_id = BigIntegerField()
    platform_id = IntegerField(null=True)
    is_sherpa = BooleanField(null=True)
    is_clanmember = BooleanField(null=True)
    is_new_clanmember = BooleanField(null=True)
    is_non_clanmember = BooleanField(null=True)
    is_protected_clanmember = BooleanField(null=True)

    class Meta:
        indexes = (
            (('guild', 'role_id'), True),
        )


class ConnManager(Manager):
    database = database_proxy


class Database(object):

    def __init__(self, url, max_connections=constants.DB_MAX_CONNECTIONS):
        url = urlparse(url)
        self._database = PooledPostgresqlExtDatabase(
            database=url.path[1:], user=url.username, password=url.password,
            host=url.hostname, port=url.port, max_connections=max_connections)
        self._loop = asyncio.get_event_loop()
        self._objects = ConnManager(loop=self._loop)

    def initialize(self):
        database_proxy.initialize(self._database)
        Guild.create_table(True)

        index_names = [index.name for index in self._database.get_indexes('member')]
        for platform in constants.PLATFORM_MAP.keys():
            index_name = f"member_{platform}_username_lower"
            if index_name not in index_names:
                Member.add_index(SQL(
                    f"CREATE INDEX {index_name} ON member(lower({platform}_username) varchar_pattern_ops)"
                ))

        Member.create_table(True)
        MemberPlatform.create_table(True)
        Clan.create_table(True)
        ClanMember.create_table(True)
        Game.create_table(True)
        ClanGame.create_table(True)
        GameMember.create_table(True)
        TwitterChannel.create_table(True)
        Role.create_table(True)
        ClanMemberApplication.create_table(True)

    @reconnect
    async def create(self, model, **data):
        return await self._objects.create(model, **data)

    @reconnect
    async def get(self, source, *args, **kwargs):
        return await self._objects.get(source, *args, **kwargs)

    @reconnect
    async def update(self, db_object, only=None):
        return await self._objects.update(db_object, only)

    @reconnect
    async def delete(self, db_object, recursive=False, delete_nullable=False):
        return await self._objects.delete(db_object, recursive, delete_nullable)

    @reconnect
    async def execute(self, query):
        return await self._objects.execute(query)

    @reconnect
    async def scalar(self, query):
        return await self._objects.scalar(query)

    @reconnect
    async def count(self, query, clear_limit=False):
        return await self._objects.count(query, clear_limit)

    async def bulk_update(self, model_list, fields, batch_size=None):
        model = type(model_list[0])
        query = model.bulk_update(model_list, fields=fields, batch_size=batch_size)
        try:
            return await self.execute(query)
        except AttributeError:
            return False

    async def get_member_by_platform(self, member_id, platform_id):
        # pylint: disable=assignment-from-no-return
        query = Member.select(Member, ClanMember).join(ClanMember, JOIN.LEFT_OUTER)
        if platform_id == constants.PLATFORM_BUNGIE:
            query = query.where(Member.bungie_id == member_id)
        elif platform_id == constants.PLATFORM_PSN:
            query = query.where(Member.psn_id == member_id)
        elif platform_id == constants.PLATFORM_XBOX:
            query = query.where(Member.xbox_id == member_id)
        elif platform_id == constants.PLATFORM_BLIZZARD:
            query = query.where(Member.blizzard_id == member_id)
        elif platform_id == constants.PLATFORM_STEAM:
            query = query.where(Member.steam_id == member_id)
        elif platform_id == constants.PLATFORM_STADIA:
            query = query.where(Member.stadia_id == member_id)
        return await self.get(query)

    async def get_member_by_naive_username(self, username, include_clan=True):
        username = username.lower()
        if include_clan:
            query = Member.select(Member, ClanMember, Clan).join(ClanMember).join(Clan)
        else:
            query = Member.select(Member)

        query = query.where(
            (fn.LOWER(Member.bungie_username) == username) |
            (fn.LOWER(Member.xbox_username) == username) |
            (fn.LOWER(Member.psn_username) == username) |
            (fn.LOWER(Member.blizzard_username) == username) |
            (fn.LOWER(Member.steam_username) == username) |
            (fn.LOWER(Member.stadia_username) == username)
        )
        return await self.get(query)

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
        return await self.execute(query)

    async def get_member_by_platform_username(self, username, platform_id):
        # pylint: disable=assignment-from-no-return
        query = Member.select()
        username = username.lower()
        if platform_id == constants.PLATFORM_BUNGIE:
            query = query.where(fn.LOWER(Member.bungie_username) == username)
        elif platform_id == constants.PLATFORM_PSN:
            query = query.where(fn.LOWER(Member.psn_username) == username)
        elif platform_id == constants.PLATFORM_XBOX:
            query = query.where(fn.LOWER(Member.xbox_username) == username)
        elif platform_id == constants.PLATFORM_BLIZZARD:
            query = query.where(fn.LOWER(Member.blizzard_username) == username)
        elif platform_id == constants.PLATFORM_STEAM:
            query = query.where(fn.LOWER(Member.steam_username) == username)
        elif platform_id == constants.PLATFORM_STADIA:
            query = query.where(fn.LOWER(Member.stadia_username) == username)
        return await self.get(query)

    async def get_member_by_discord_id(self, discord_id, include_clan=True):
        if include_clan:
            query = Member.select(Member, ClanMember, Clan).join(ClanMember).join(Clan)
        else:
            query = Member.select(Member)

        query = query.where(Member.discord_id == discord_id)
        return await self.get(query)

    async def get_clan_members(self, clan_ids, sorted_by=None):
        username = Case(ClanMember.platform_id, (
            (constants.PLATFORM_XBOX, Member.xbox_username),
            (constants.PLATFORM_PSN, Member.psn_username),
            (constants.PLATFORM_BLIZZARD, Member.psn_username),
            (constants.PLATFORM_STEAM, Member.steam_username),
            (constants.PLATFORM_STADIA, Member.stadia_username))
        )

        query = Member.select(Member, ClanMember, Clan, username.alias('username')).join(
            ClanMember).join(Clan).where(Clan.clan_id << clan_ids)

        if sorted_by == 'join_date':
            query = query.order_by(ClanMember.join_date)
        elif sorted_by == 'username':
            query = query.order_by(username)
        return await self.execute(query)

    async def get_clan_members_by_guild_id(self, guild_id, as_dict=False):
        if as_dict:
            query = Member.select(Member, ClanMember).join(ClanMember).join(Clan).join(Guild).where(
                Guild.guild_id == guild_id,
            ).dicts()
        else:
            query = Member.select(Member, ClanMember).join(ClanMember).join(Clan).join(Guild).where(
                Guild.guild_id == guild_id,
            )
        return await self.execute(query)

    async def get_clan_member_by_platform(self, member_id, platform_id, clan_ids):
        if platform_id == constants.PLATFORM_PSN:
            query = Member.select(Member, ClanMember).join(ClanMember).where(
                ClanMember.clan_id << clan_ids,
                Member.psn_id == member_id
            )
        elif platform_id == constants.PLATFORM_XBOX:
            query = Member.select(Member, ClanMember).join(ClanMember).where(
                ClanMember.clan_id << clan_ids,
                Member.xbox_id == member_id
            )
        elif platform_id == constants.PLATFORM_BLIZZARD:
            query = Member.select(Member, ClanMember).join(ClanMember).where(
                ClanMember.clan_id << clan_ids,
                Member.blizzard_id == member_id
            )
        elif platform_id == constants.PLATFORM_STEAM:
            query = Member.select(Member, ClanMember).join(ClanMember).where(
                ClanMember.clan_id << clan_ids,
                Member.steam_id == member_id
            )
        elif platform_id == constants.PLATFORM_STADIA:
            query = Member.select(Member, ClanMember).join(ClanMember).where(
                ClanMember.clan_id << clan_ids,
                Member.stadia_id == member_id
            )
        return await self.get(query)

    async def get_clans_by_guild(self, guild_id):
        query = Clan.select().join(Guild).where(
            Guild.guild_id == guild_id
        )
        return await self.execute(query)

    async def get_clan_members_active(self, clan_id, **kwargs):
        if not kwargs:
            kwargs = dict(hours=1)
        query = Member.select(Member, ClanMember).join(ClanMember).join(Clan).where(
            Clan.id == clan_id,
            ClanMember.last_active > datetime.now(pytz.utc) - timedelta(**kwargs)
        )
        return await self.execute(query)

    async def get_clan_members_inactive(self, clan_id, **kwargs):
        if not kwargs:
            kwargs = dict(days=30)
        query = Member.select(Member, ClanMember).join(ClanMember).join(Clan).where(
            Clan.id == clan_id,
            ClanMember.last_active < datetime.now(pytz.utc) - timedelta(**kwargs)
        )
        return await self.execute(query)

    async def create_game(self, game):
        try:
            game_db = await self.create(Game, **vars(game))
        except IntegrityError:
            # Mitigate possible race condition when multiple parallel jobs try to
            # do the same thing. Likely when there are multiple people in the same
            # game instance.
            # TODO: Figure out a better way to 'lock' things
            return
        log.info(f"Game {game_db.instance_id} created")
        return game_db

    async def create_clan_game(self, game_db, game, clan_id):
        try:
            await self.get(ClanGame, clan=clan_id, game=game_db.id)
        except DoesNotExist:
            await self.create(ClanGame, clan=clan_id, game=game_db.id)
            tasks = [
                self.create_game_member(player, game_db, clan_id)
                for player in game.clan_players
            ]
            await asyncio.gather(*tasks)

    async def create_game_member(self, player, game_db, clan_id, player_db=None):
        if not player_db:
            player_db = await self.get_clan_member_by_platform(
                player.membership_id, player.membership_type, [clan_id])

        try:
            # Create the game member
            await self.create(
                GameMember, member=player_db.id, game=game_db.id,
                completed=player.completed, time_played=player.time_played)
        except IntegrityError:
            # If one already exists, we can assume this is due to a drop/re-join event so
            # increment the time played and set the completion flag
            game_member_db = await self.get(GameMember, game=game_db.id, member=player_db.id)
            game_member_db.time_played += player.time_played

            if not game_member_db.completed or game_member_db.completed != player.completed:
                game_member_db.completed = player.completed
            await self.update(game_member_db)

        log.info(f"Player {member_hash(player)} created in game id {game_db.instance_id}")

    async def close(self):
        await self._objects.close()
