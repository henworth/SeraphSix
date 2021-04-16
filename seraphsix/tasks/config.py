import os
import pytz

from arq.connections import RedisSettings
from dataclasses import dataclass, asdict
from datetime import datetime
from get_docker_secret import get_docker_secret
from seraphsix.constants import LOG_FORMAT_MSG, DESTINY_DATE_FORMAT, DB_MAX_CONNECTIONS, ROOT_LOG_LEVEL


def log_config(root_log_level: str = ROOT_LOG_LEVEL) -> dict:
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'seraphsix': {
                '()': 'seraphsix.utils.UTCFormatter',
                'fmt': LOG_FORMAT_MSG,
                'datefmt': DESTINY_DATE_FORMAT
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'seraphsix'
            }
        },
        'root': {'handlers': ['console'], 'level': root_log_level},
        'loggers': {
            'aiohttp.client': {'handlers': ['console'], 'level': 'ERROR'},
            'aioredis': {'handlers': ['console'], 'level': 'INFO'},
            'arq': {'handlers': ['console'], 'level': 'INFO'},
            'backoff': {'handlers': ['console'], 'level': 'DEBUG'},
            'bot': {'handlers': ['console'], 'level': 'DEBUG'},
            'peewee': {'handlers': ['console'], 'level': 'ERROR'},
            'discord': {'handlers': ['console'], 'level': 'INFO'}
        }
    }


@dataclass
class DestinyConfig:
    api_key: str
    client_id: str
    client_secret: str
    redirect_host: str

    def __init__(self):
        self.api_key = get_docker_secret('bungie_api_key')
        self.client_id = get_docker_secret('bungie_client_id')
        self.client_secret = get_docker_secret('bungie_client_secret')
        self.redirect_host = get_docker_secret('bungie_redirect_host')


@dataclass
class The100Config:
    api_key: str
    base_url: str

    def __init__(self):
        self.api_key = get_docker_secret('the100_api_key')
        self.base_url = get_docker_secret('the100_api_url')


@dataclass
class TwitterConfig:
    consumer_key: str
    consumer_secret: str
    access_token: str
    access_token_secret: str

    def __init__(self):
        self.consumer_key = get_docker_secret('twitter_consumer_key')
        self.consumer_secret = get_docker_secret('twitter_consumer_secret')
        self.access_token = get_docker_secret('twitter_access_token')
        self.access_token_secret = get_docker_secret('twitter_access_token_secret')

    def asdict(self):
        return asdict(self)


@dataclass
class Config:
    destiny: DestinyConfig
    the100: The100Config
    twitter: TwitterConfig
    database_url: str
    database_conns: int
    discord_api_key: str
    redis_url: str
    arq_redis: RedisSettings
    home_server: int
    log_channel: int
    reg_channel: int
    enable_activity_tracking: bool
    activity_cutoff: str
    flask_app_key: str
    root_log_level: str

    def __init__(self):
        database_user = get_docker_secret('seraphsix_pg_db_user', default='seraphsix')
        database_password = get_docker_secret('seraphsix_pg_db_pass')
        database_host = get_docker_secret('seraphsix_pg_db_host', default='localhost')
        database_port = get_docker_secret('seraphsix_pg_db_port', default='5432')
        database_name = get_docker_secret('seraphsix_pg_db_name', default='seraphsix')
        self.database_conns = get_docker_secret('seraphsix_pg_db_conns', default=DB_MAX_CONNECTIONS, cast_to=int)

        database_auth = f"{database_user}:{database_password}"
        self.database_url = f"postgres://{database_auth}@{database_host}:{database_port}/{database_name}"

        redis_password = get_docker_secret('seraphsix_redis_pass')
        redis_host = get_docker_secret('seraphsix_redis_host', default='localhost')
        redis_port = get_docker_secret('seraphsix_redis_port', default='6379')
        self.redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}"

        self.arq_redis = RedisSettings.from_dsn(f'{self.redis_url}/1')

        self.destiny = DestinyConfig()
        self.the100 = The100Config()
        self.twitter = TwitterConfig()
        self.discord_api_key = get_docker_secret('discord_api_key')
        self.home_server = get_docker_secret('home_server', cast_to=int)
        self.log_channel = get_docker_secret('home_server_log_channel', cast_to=int)
        self.reg_channel = get_docker_secret('home_server_reg_channel', cast_to=int)
        self.enable_activity_tracking = get_docker_secret('enable_activity_tracking', cast_to=bool)

        self.flask_app_key = os.environb[b'FLASK_APP_KEY'].decode('unicode-escape').encode('latin-1')

        self.activity_cutoff = get_docker_secret('activity_cutoff')
        if self.activity_cutoff:
            self.activity_cutoff = datetime.strptime(self.activity_cutoff, '%Y-%m-%d').astimezone(tz=pytz.utc)

        self.root_log_level = get_docker_secret('root_log_level', default=ROOT_LOG_LEVEL, cast_to=str)
