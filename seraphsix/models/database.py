from seraphsix import constants

from tortoise.contrib.postgres.indexes import PostgreSQLIndex
from tortoise.exceptions import ValidationError
from tortoise.fields import (
    BigIntField,
    IntField,
    CharField,
    BooleanField,
    ForeignKeyRelation,
    ForeignKeyField,
    DatetimeField,
    FloatField,
    ReverseRelation,
)
from tortoise.models import Model
from tortoise.validators import Validator


class PlatformValidator(Validator):
    """
    Validates whether the given value is a valid platform id
    """

    def __call__(self, value: int):
        if value not in constants.PLATFORMS:
            raise ValidationError(f"Value '{value}' is not a valid platform")


class ClanMemberRankValidator(Validator):
    """
    Validates whether the given value is a valid platform id
    """

    def __call__(self, value: int):
        if value not in constants.CLAN_MEMBER_RANKS:
            raise ValidationError(f"Value '{value}' is not a valid clan rank")


class Member(Model):
    discord_id = BigIntField(null=True)
    bungie_id = BigIntField(null=True)
    bungie_username = CharField(max_length=255, null=True)
    xbox_id = BigIntField(null=True)
    xbox_username = CharField(max_length=255, unique=True, null=True)
    psn_id = BigIntField(null=True)
    psn_username = CharField(max_length=255, unique=True, null=True)
    blizzard_id = BigIntField(null=True)
    blizzard_username = CharField(max_length=255, unique=True, null=True)
    steam_id = BigIntField(null=True)
    steam_username = CharField(max_length=255, unique=True, null=True)
    stadia_id = BigIntField(null=True)
    stadia_username = CharField(max_length=255, unique=True, null=True)
    the100_id = BigIntField(unique=True, null=True)
    the100_username = CharField(max_length=255, unique=True, null=True)
    timezone = CharField(max_length=255, null=True)
    bungie_access_token = CharField(max_length=360, unique=True, null=True)
    bungie_refresh_token = CharField(max_length=360, unique=True, null=True)
    is_cross_save = BooleanField(default=False)
    primary_membership_id = BigIntField(unique=True, null=True)

    clan: ReverseRelation["ClanMember"]
    games: ReverseRelation["GameMember"]

    class Meta:
        indexes = [
            PostgreSQLIndex(
                fields={
                    "discord_id",
                    "bungie_id",
                    "xbox_id",
                    "psn_id",
                    "blizzard_id",
                    "steam_id",
                    "stadia_id",
                    "the100_id",
                }
            )
        ]

    # TODO: Figure out how to migrate this to Tortoise
    #     index_names = [index.name for index in self._database.get_indexes('member')]
    #     for platform in constants.PLATFORM_MAP.keys():
    #         index_name = f"member_{platform}_username_lower"
    #         if index_name not in index_names:
    #             Member.add_index(SQL(
    #                 f"CREATE INDEX {index_name} ON member(lower({platform}_username) varchar_pattern_ops)"
    #             ))


class Guild(Model):
    guild_id = BigIntField(unique=True)
    prefix = CharField(max_length=5, null=True, default="?")
    clear_spam = BooleanField(default=False)
    aggregate_clans = BooleanField(default=True)
    track_sherpas = BooleanField(default=False)
    admin_channel = BigIntField(unique=True, null=True)
    announcement_channel = BigIntField(unique=True, null=True)


class Clan(Model):
    clan_id = BigIntField(unique=True)
    name = CharField(max_length=255)
    callsign = CharField(max_length=4)
    platform = IntField(null=True, validators=[PlatformValidator()])
    the100_group_id = IntField(unique=True, null=True)
    activity_tracking = BooleanField(default=True)

    guild: ForeignKeyRelation[Guild] = ForeignKeyField(
        "seraphsix.Guild", related_name="clans", to_field="id"
    )

    members: ReverseRelation["ClanMember"]


class ClanMember(Model):
    platform_id = IntField()
    join_date = DatetimeField()
    is_active = BooleanField(default=True)
    last_active = DatetimeField(null=True)
    is_sherpa = BooleanField(default=False)
    member_type = IntField(null=True, validators=[ClanMemberRankValidator()])

    clan: ForeignKeyRelation[Clan] = ForeignKeyField(
        "seraphsix.Clan", related_name="members", to_field="id"
    )

    member: ForeignKeyRelation[Member] = ForeignKeyField(
        "seraphsix.Member", related_name="clans", to_field="id"
    )


class ClanMemberApplication(Model):
    approved = BooleanField(default=False)
    message_id = BigIntField(unique=True)

    guild: ForeignKeyRelation[Guild] = ForeignKeyField(
        "seraphsix.Guild", related_name="clanmemberapplications", to_field="id"
    )

    member: ForeignKeyRelation[Member] = ForeignKeyField(
        "seraphsix.Member", related_name="clanmemberapplications_created", to_field="id"
    )

    approved_by: ForeignKeyRelation[Member] = ForeignKeyField(
        "seraphsix.Member",
        related_name="clanmemberapplications_approved",
        to_field="id",
    )


class Game(Model):
    mode_id = IntField()
    instance_id = BigIntField(unique=True)
    date = DatetimeField()
    reference_id = BigIntField(null=True)

    class Meta:
        indexes = ("mode_id", "reference_id")


class ClanGame(Model):
    clan: ForeignKeyRelation[Clan] = ForeignKeyField(
        "seraphsix.Clan", related_name="games", to_field="id"
    )

    game: ForeignKeyRelation[Game] = ForeignKeyField(
        "seraphsix.Game", related_name="clans", to_field="id"
    )

    class Meta:
        indexes = ("clan", "game")


class GameMember(Model):
    time_played = FloatField(null=True)
    completed = BooleanField(null=True)

    member: ForeignKeyRelation[Member] = ForeignKeyField(
        "seraphsix.Member", related_name="games", to_field="id"
    )

    game: ForeignKeyRelation[Game] = ForeignKeyField(
        "seraphsix.Game", related_name="members", to_field="id"
    )

    class Meta:
        indexes = ("member", "game")


class TwitterChannel(Model):
    channel_id = BigIntField()
    twitter_id = BigIntField()
    guild_id = BigIntField()

    class Meta:
        indexes = ("channel_id", "twitter_id", "guild_id")


class Role(Model):
    role_id = BigIntField()
    platform_id = IntField(null=True)
    is_sherpa = BooleanField(null=True)
    is_clanmember = BooleanField(null=True)
    is_new_clanmember = BooleanField(null=True)
    is_non_clanmember = BooleanField(null=True)
    is_protected_clanmember = BooleanField(null=True)

    guild: ForeignKeyRelation[Guild] = ForeignKeyField(
        "seraphsix.Guild", related_name="roles", to_field="id"
    )

    class Meta:
        indexes = ("guild", "role_id")


__models__ = [
    Member,
    Guild,
    Clan,
    ClanMember,
    ClanMemberApplication,
    Game,
    ClanGame,
    GameMember,
    TwitterChannel,
    Role,
]
