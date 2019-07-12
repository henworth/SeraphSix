import os
from peewee import *
from playhouse.migrate import *
from urllib.parse import urlparse
from seraphsix import constants

url = urlparse(os.environ.get('DATABASE_URL'))


db = PostgresqlDatabase(database=url.path[1:], user=url.username,
                        password=url.password, host=url.hostname, port=url.port)
migrator = PostgresqlMigrator(db)


with db.atomic():
    migrate(
        # migrator.add_column('game', 'activity_id', BigIntegerField(null=True)),
        # migrator.add_index('game', ('mode_id', 'activity_id'), False)
        # migrator.rename_column('game', 'activity_id', 'reference_id'),
        # migrator.drop_index('game', 'game_mode_id_activity_id'),
        # migrator.add_index('game', ('mode_id', 'reference_id'), False)
        # migrator.add_column('member', 'bungie_access_token', CharField(unique=True, null=True)),
        # migrator.add_column('member', 'bungie_refresh_token', CharField(unique=True, null=True))
        # migrator.drop_column('member', 'xbox_id'),
        # migrator.add_column('member', 'xbox_id',
        #                     BigIntegerField(unique=True, null=True))
        # migrator.rename_table('user', 'member')
        # migrator.rename_column('clanmember', 'user_id', 'member_id'),
        # migrator.add_column('clanmember', 'member', ForeignKeyField(Member))

        # migrator.add_column('member', 'psn_id', BigIntegerField(null=True)),
        # migrator.add_column('member', 'psn_username', CharField(unique=True, null=True)),

        # migrator.add_column('member', 'blizzard_id', BigIntegerField(null=True)),
        # migrator.add_column('member', 'blizzard_username', CharField(unique=True, null=True)),

        # migrator.add_column('member', 'the100_id', BigIntegerField(null=True)),
        # migrator.add_column('clan', 'name', CharField(default="Default Name")),
        # migrator.add_column('clan', 'callsign', CharField(
        #     max_length=4, default="TEMP")),
        # migrator.drop_not_null('member', 'bungie_id'),
        # migrator.add_column('clan', 'platform', IntegerField(
        #     null=True,
        #     constraints=[
        #         Check(
        #             f'platform in ({constants.PLATFORM_XBOX}, {constants.PLATFORM_PSN}, {constants.PLATFORM_BLIZ})'
        #         )
        #     ])
        # )
        # migrator.drop_not_null('clan', 'guild_id'),
        # migrator.add_column('clan', 'the100_group_id', IntegerField(unique=True, null=True)),
        # migrator.drop_index(
        #     'member', 'user_discord_id_bungie_id_xbox_id_psn_id_blizzard_id_the100_id'),
        # migrator.drop_column('member', 'the100_id'),
        # migrator.add_column('member', 'the100_id',
        #                     BigIntegerField(unique=True, null=True)),
        # migrator.add_index('member', ('discord_id', 'bungie_id', 'xbox_id',
        #                                'psn_id', 'blizzard_id', 'the100_id'), True)
        # Add a CHECK() constraint to enforce the price cannot be negative.
        # migrator.add_constraint(
        #     'clan',
        #     'platform',
        #     Check(f'platform in ({constants.PLATFORM_XBOX}, {constants.PLATFORM_PSN}, {constants.PLATFORM_BLIZ})')
        # )
        # migrator.drop_column('member', 'join_date'),
        # migrator.drop_column('member', 'is_active'),
        # migrator.add_column('twitterchannel', 'guild_id', BigIntegerField(default=0))
        # migrator.drop_index('twitterchannel', 'twitterchannel_channel_id_twitter_id'),
        # migrator.add_index('twitterchannel', ('channel_id', 'twitter_id', 'guild_id'), True)
        # migrator.drop_not_null('member', 'is_active'),
        # migrator.drop_not_null('member', 'join_date'),
        # migrator.add_column('clanmember', 'member_type', IntegerField(
        #         null=True,
        #         constraints=[Check(
        #             f'member_type in ({constants.CLAN_MEMBER_NONE}, {constants.CLAN_MEMBER_BEGINNER},'
        #             f'{constants.CLAN_MEMBER_MEMBER}, {constants.CLAN_MEMBER_ADMIN}, '
        #             f'{constants.CLAN_MEMBER_ACTING_FOUNDER}, {constants.CLAN_MEMBER_FOUNDER})'
        #         )]
        #     )
        # )
        migrator.add_column('guild', 'aggregate_clans', BooleanField(default=True)),
        migrator.add_column('clan', 'activity_tracking', BooleanField(default=True))
    )
