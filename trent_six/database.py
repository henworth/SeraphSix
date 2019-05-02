import asyncio

from datetime import datetime, timezone
from peewee import fn, Model, CharField, BigIntegerField, IntegerField, ForeignKeyField, Proxy, BooleanField, CompositeKey
from peewee_async import Manager
from peewee_asyncext import PostgresqlExtDatabase
from playhouse.postgres_ext import DateTimeTZField
from urllib.parse import urlparse

database_proxy = Proxy()


class BaseModel(Model):
    class Meta:
        database = database_proxy


class Member(BaseModel):
    bungie_id = BigIntegerField(unique=True)
    bungie_username = CharField(null=True)
    discord_id = BigIntegerField(null=True, index=True)
    join_date = DateTimeTZField()
    xbox_username = CharField(unique=True)
    is_active = BooleanField(default=True)
    the100_username = CharField(null=True)
    timezone = CharField(null=True)
    bungie_access_token = CharField(unique=True, null=True)
    bungie_refresh_token = CharField(unique=True, null=True)

    class Meta:
        indexes = (
            (('bungie_id', 'xbox_username'), True),
        )


class GameSession(BaseModel):
    member = ForeignKeyField(Member, backref='gamesessions')
    game_mode_id = IntegerField(index=True)
    count = IntegerField()
    last_updated = DateTimeTZField(default=datetime.now(timezone.utc))

    class Meta:
        indexes = (
            (('member_id', 'game_mode_id'), True),
        )


class Game(BaseModel):
    mode_id = IntegerField()
    instance_id = BigIntegerField(unique=True)
    date = DateTimeTZField()


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

    class Meta:
        indexes = (
            (('channel_id', 'twitter_id'), True),
        )


class ConnManager(Manager):
    database = database_proxy


class Database:

    def __init__(self, url, loop=None):
        url = urlparse(url)
        self._database = PostgresqlExtDatabase(
            database=url.path[1:], user=url.username, password=url.password,
            host=url.hostname, port=url.port)
        self._loop = asyncio.get_event_loop() if loop is None else loop
        self.objects = ConnManager(loop=self._loop)

    def initialize(self):
        database_proxy.initialize(self._database)
        Member.create_table(True)
        Game.create_table(True)
        GameMember.create_table(True)
        GameSession.create_table(True)
        TwitterChannel.create_table(True)

    async def get_game_session(self, member_name, game_mode_id):
        query = GameSession.select().join(Member).where(
            GameSession.game_mode_id == game_mode_id,
            Member.xbox_username == member_name
        )
        return await self.objects.get(query)

    async def create_game_session(self, member_name, game_details):
        member = await self.get_member(member_name)
        return await self.objects.create(GameSession, **{'member': member, **game_details})

    async def update_game_session(self, member_name, game_mode_id, count):
        game_session = await self.get_game_session(member_name, game_mode_id)
        game_session.count = game_session.count + count
        game_session.last_updated = datetime.now(timezone.utc)
        return await self.objects.update(game_session)

    async def get_game_sessions(self, member_name):
        query = GameSession.select().join(Member).where(Member.xbox_username == member_name)
        return await self.objects.get(query)

    async def get_game_session_sum(self, member_name, mode_ids):
        query = GameSession.select(
                fn.SUM(GameSession.game_mode_id)
            ).join(Member).where(
                (Member.xbox_username == member_name) &
                (GameSession.game_mode_id << mode_ids)
            )
        return await self.objects.get(query)

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

    async def get_member(self, member_name):
        return await self.objects.get(Member, xbox_username=member_name)

    async def get_member_by_discord(self, discord_id):
        return await self.objects.get(Member, discord_id=discord_id)

    async def get_member_by_bungie(self, bungie_id):
        return await self.objects.get(Member, bungie_id=bungie_id)

    async def create_member(self, member_details):
        return await self.objects.create(Member, **member_details)

    async def update_member(self, member):
        return await self.objects.update(member)

    async def get_members(self, active_only=True):
        return await self.objects.execute(
            Member.select().where(Member.is_active == active_only)
        )

    async def get_game(self, instance_id):
        return await self.objects.get(Game, instance_id=instance_id)

    async def create_game(self, game_details, members):
        game = await self.objects.create(Game, **game_details)
        for member in members:
            member_db = await self.get_member(member)
            await self.objects.create(GameMember, member=member_db.id, game=game.id)

    async def create_twitter_channel(self, channel_id, twitter_id):
        return await self.objects.create(
            TwitterChannel, **{'channel_id': channel_id, 'twitter_id': twitter_id})

    async def get_twitter_channel(self, twitter_id):
        return await self.objects.get(TwitterChannel, twitter_id=twitter_id)

    def close(self):
        asyncio.ensure_future(self.objects.close())
