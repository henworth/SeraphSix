import asyncio
import logging
import pytz

from datetime import datetime, timedelta
from peewee import (
    Model, CharField, BigIntegerField, IntegerField,
    ForeignKeyField, Proxy, BooleanField, DoesNotExist,
    Check, SQL, fn, Case)
from peewee_async import Manager
from peewee_asyncext import PooledPostgresqlExtDatabase
from playhouse.postgres_ext import DateTimeTZField
from seraphsix import constants
from urllib.parse import urlparse

logging.getLogger(__name__)

database_proxy = Proxy()


class BaseModel(Model):
    class Meta:
        database = database_proxy


class Guild(BaseModel):
    guild_id = BigIntegerField(unique=True)
    prefix = CharField(max_length=5, null=True, default='?')
    clear_spam = BooleanField(default=False)
    aggregate_clans = BooleanField(default=True)


class Clan(BaseModel):
    clan_id = BigIntegerField(unique=True)
    guild = ForeignKeyField(Guild)
    name = CharField()
    callsign = CharField(max_length=4)
    platform = IntegerField(
        null=True,
        constraints=[Check(
            f'platform in ({constants.PLATFORM_XBOX}, {constants.PLATFORM_PSN}, {constants.PLATFORM_BLIZ})'
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

    the100_id = BigIntegerField(unique=True, null=True)
    the100_username = CharField(unique=True, null=True)

    timezone = CharField(null=True)

    bungie_access_token = CharField(max_length=360, unique=True, null=True)
    bungie_refresh_token = CharField(max_length=360, unique=True, null=True)

    class Meta:
        indexes = (
            (('discord_id', 'bungie_id', 'xbox_id',
              'psn_id', 'blizzard_id', 'the100_id'), True),
        )


class ClanMember(BaseModel):
    clan = ForeignKeyField(Clan)
    member = ForeignKeyField(Member)
    platform_id = IntegerField()
    join_date = DateTimeTZField()
    is_active = BooleanField(default=True)
    last_active = DateTimeTZField(null=True)
    member_type = IntegerField(
        null=True,
        constraints=[Check(
            f'member_type in ({constants.CLAN_MEMBER_NONE}, {constants.CLAN_MEMBER_BEGINNER},'
            f'{constants.CLAN_MEMBER_MEMBER}, {constants.CLAN_MEMBER_ADMIN}, '
            f'{constants.CLAN_MEMBER_ACTING_FOUNDER}, {constants.CLAN_MEMBER_FOUNDER})'
        )]
    )


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


class ConnManager(Manager):
    database = database_proxy


class Database:

    def __init__(self, url, loop=None):
        url = urlparse(url)
        self._database = PooledPostgresqlExtDatabase(
            database=url.path[1:], user=url.username, password=url.password,
            host=url.hostname, port=url.port, max_connections=18)
        self._loop = asyncio.get_event_loop() if loop is None else loop
        self.objects = ConnManager(loop=self._loop)

    def initialize(self):
        database_proxy.initialize(self._database)
        Guild.create_table(True)

        member_indexes = self._database.get_indexes('member')
        index_names = [index.name for index in member_indexes]
        if 'member_xbox_username_lower' not in index_names:
            Member.add_index(SQL(
                'CREATE INDEX member_xbox_username_lower ON '
                'member(lower(xbox_username) varchar_pattern_ops)'
            ))

        Member.create_table(True)
        Clan.create_table(True)
        ClanMember.create_table(True)
        Game.create_table(True)
        ClanGame.create_table(True)
        GameMember.create_table(True)
        TwitterChannel.create_table(True)

    async def get_game_count(self, member_name, mode_ids):
        # select count(game.id) from game
        # join gamemember on gamemember.game_id = game.id
        # join member on member.id = gamemember.member_id
        # where gamemember.member_id = member.id
        # and game.mode_id in (37, 38, 72, 74)
        # and member.xbox_username = 'lifeinchains';
        query = Game.select().join(GameMember).join(Member).where(
            (Member.xbox_username == member_name) &
            (Game.mode_id << mode_ids)
        ).distinct()
        return await self.objects.count(query)

    async def get_all_game_count(self, mode_ids):
        query = Game.select().where(Game.mode_id << mode_ids).distinct()
        return await self.objects.count(query)

    async def get_game_members(self, instance_id):
        query = Member.select(
            Member.xbox_username
        ).join(GameMember).join(Game).where(
            Game.instance_id == instance_id
        )
        return await self.objects.execute(query)

    async def get_member_by_platform(self, member_id, platform_id):
        # pylint: disable=assignment-from-no-return
        if platform_id == constants.PLATFORM_BLIZ:
            query = Member.select().where(Member.blizzard_id == member_id)
        elif platform_id == constants.PLATFORM_BNG:
            query = Member.select().where(Member.bungie_id == member_id)
        elif platform_id == constants.PLATFORM_PSN:
            query = Member.select().where(Member.psn_id == member_id)
        elif platform_id == constants.PLATFORM_XBOX:
            query = Member.select().where(Member.xbox_id == member_id)
        return await self.objects.get(query)

    async def get_member_by_naive_id(self, member_id):
        query = Member.select().where(
            (Member.xbox_id == member_id) |
            (Member.psn_id == member_id) |
            (Member.blizzard_id == member_id) |
            (Member.discord_id == member_id) |
            (Member.the100_id == member_id) |
            (Member.bungie_id == member_id)
        )
        return await self.objects.get(query)

    async def get_member_by_xbox_username(self, username):
        query = Member.select().where(fn.LOWER(Member.xbox_username) == username.lower())
        return await self.objects.get(query)

    async def get_member_by_platform_username(self, platform_id, username):
        # pylint: disable=assignment-from-no-return
        query = Member.select()
        username = username.lower()
        if platform_id == constants.PLATFORM_BLIZ:
            query = query.where(fn.LOWER(Member.blizzard_username) == username)
        elif platform_id == constants.PLATFORM_BNG:
            query = query.where(fn.LOWER(Member.bungie_username) == username)
        elif platform_id == constants.PLATFORM_PSN:
            query = query.where(fn.LOWER(Member.psn_username) == username)
        elif platform_id == constants.PLATFORM_XBOX:
            query = query.where(fn.LOWER(Member.xbox_username) == username)
        return await self.objects.get(query)

    async def get_member_by_discord_id(self, discord_id):
        return await self.objects.get(Member, discord_id=discord_id)

    async def get_member_by_bungie_id(self, bungie_id):
        return await self.get_member_by_platform(bungie_id, constants.PLATFORM_BNG)

    async def get_member_by_xbox_id(self, xbox_id):
        return await self.get_member_by_platform(xbox_id, constants.PLATFORM_XBOX)

    async def get_member_by_the100_id(self, the100_id):
        return await self.objects.get(Member, the100_id=the100_id)

    async def get_game(self, instance_id):
        return await self.objects.get(Game, instance_id=instance_id)

    async def get_games(self):
        return await self.objects.execute(Game.select())

    async def create_game(self, game):
        return await self.objects.create(Game, **game)

    async def update_game_bulk(self, game_list, fields, batch_size):
        query = Game.bulk_update(
            game_list, fields=fields, batch_size=batch_size)
        try:
            return await self.objects.execute(query)
        except AttributeError:
            return True

    async def create_twitter_channel(self, guild_id, channel_id, twitter_id):
        details = {
            'guild_id': guild_id, 'channel_id': channel_id, 'twitter_id': twitter_id}
        return await self.objects.create(TwitterChannel, **details)

    async def get_twitter_channel_by_guild_id(self, guild_id, twitter_id):
        # pylint: disable=assignment-from-no-return
        query = TwitterChannel.select().where(
            TwitterChannel.guild_id == guild_id,
            TwitterChannel.twitter_id == twitter_id
        )
        return await self.objects.get(query)

    async def get_twitter_channels(self, twitter_id):
        # pylint: disable=assignment-from-no-return
        query = TwitterChannel.select().where(
            TwitterChannel.twitter_id == twitter_id
        )
        return await self.objects.execute(query)

    async def get_guild(self, guild_id):
        return await self.objects.get(Guild, guild_id=guild_id)

    async def create_guild(self, guild_id):
        return await self.objects.create(Guild, **{'guild_id': guild_id})

    async def get_guilds(self):
        return await self.objects.execute(Guild.select())

    async def get_clan(self, clan_id):
        return await self.objects.get(Clan, clan_id=clan_id)

    async def create_clan(self, guild_id, **clan_details):
        guild = await self.get_guild(guild_id)
        clan_details.update({'guild': guild})
        return await self.objects.create(Clan, **clan_details)

    async def create_clan_member(self, member_db, clan_id, **member_details):
        clan = await self.get_clan(clan_id)
        return await self.objects.create(
            ClanMember, clan=clan, member=member_db, **member_details)

    async def get_clan_members(self, clan_ids, sorted_by=None):
        username = Case(ClanMember.platform_id, (
            (1, Member.xbox_username),
            (2, Member.psn_username),
            (4, Member.blizzard_username))
        )

        query = Member.select(Member, ClanMember, Clan, username.alias('username')).join(
            ClanMember).join(Clan).where(Clan.clan_id << clan_ids)

        if sorted_by == 'join_date':
            query = query.order_by(ClanMember.join_date)
        elif sorted_by == 'username':
            query = query.order_by(username)
        return await self.objects.execute(query)

    async def get_clan_members_by_guild_id(self, guild_id, as_dict=False):
        if as_dict:
            query = Member.select(Member, ClanMember).join(ClanMember).join(Clan).join(Guild).where(
                Guild.guild_id == guild_id,
            ).dicts()
        else:
            query = Member.select(Member, ClanMember).join(ClanMember).join(Clan).join(Guild).where(
                Guild.guild_id == guild_id,
            )
        return await self.objects.execute(query)

    async def get_clan_member_by_discord_id(self, discord_id, clan_id):
        return await self.objects.get(
            Member.select(Member, ClanMember).join(ClanMember).join(Clan).where(
                Clan.id == clan_id,
                Member.discord_id == discord_id
            )
        )

    async def get_clan_member_by_platform(self, member_id, platform_id, clan_id):
        if platform_id == constants.PLATFORM_BLIZ:
            query = Member.select(Member, ClanMember).join(ClanMember).where(
                ClanMember.clan_id == clan_id,
                Member.blizzard_id == member_id
            )
        elif platform_id == constants.PLATFORM_PSN:
            query = Member.select(Member, ClanMember).join(ClanMember).where(
                ClanMember.clan_id == clan_id,
                Member.psn_id == member_id
            )
        elif platform_id == constants.PLATFORM_XBOX:
            query = Member.select(Member, ClanMember).join(ClanMember).where(
                ClanMember.clan_id == clan_id,
                Member.xbox_id == member_id
            )
        return await self.objects.get(query)

    async def get_clans_by_guild(self, guild_id):
        query = Clan.select().join(Guild).where(
            Guild.guild_id == guild_id
        )
        return await self.objects.execute(query)

    async def get_clan_by_member(self, member_id):
        query = Clan.select().join(ClanMember).join(Member).where(
            Member.id == member_id
        )
        return await self.objects.get(query)

    async def create_clan_game(self, clan_id, game_id):
        return await self.objects.create(ClanGame, game=game_id, clan=clan_id)

    async def create_clan_game_members(self, clan_id, game_id, member_dbs):
        for member_db in member_dbs:
            platform_id = member_db.clanmember.platform_id

            if platform_id == constants.PLATFORM_BLIZ:
                membership_id = member_db.blizzard_id
            elif platform_id == constants.PLATFORM_PSN:
                membership_id = member_db.psn_id
            elif platform_id == constants.PLATFORM_XBOX:
                membership_id = member_db.xbox_id

            try:
                member_db = await self.get_clan_member_by_platform(
                    membership_id, platform_id, clan_id)
            except DoesNotExist:
                logging.info((membership_id, platform_id, clan_id))
                raise
            await self.objects.create(GameMember, member=member_db.id, game=game_id)

    async def create_member(self, member_details):
        return await self.objects.create(Member, **member_details)

    async def get_members(self, is_active=False):
        return await self.objects.execute(Member.select().where(Member.is_active == is_active))

    async def get_clan_member(self, member_id):
        return await self.objects.get(
            ClanMember.select().where(
                ClanMember.member_id == member_id
            )
        )

    async def get_clan_member_by_the100_id(self, the100_id):
        query = Member.select(Member, ClanMember, Clan, Guild).join(ClanMember).join(
            Clan).join(Guild).where(Member.the100_id == the100_id)
        return await self.objects.get(query)

    async def update(self, db_object):
        return await self.objects.update(db_object)

    async def delete(self, db_object):
        return await self.objects.delete(db_object)

    async def get_clan_members_active(self, clan_id, **kwargs):
        if not kwargs:
            kwargs = dict(hours=1)
        query = Member.select(Member, ClanMember).join(ClanMember).join(Clan).where(
            Clan.id == clan_id,
            ClanMember.last_active > datetime.now(
                pytz.utc) - timedelta(**kwargs)
        )
        return await self.objects.execute(query)

    def close(self):
        asyncio.ensure_future(self.objects.close())
