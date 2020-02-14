import os
import pytz

from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class BungieConfig:
    api_key: str
    client_id: str
    client_secret: str
    redirect_host: str

    def __init__(self):
        self.api_key = os.environ.get("BUNGIE_API_KEY")
        self.client_id = os.environ.get("BUNGIE_CLIENT_ID")
        self.client_secret = os.environ.get("BUNGIE_CLIENT_SECRET")
        self.redirect_host = os.environ.get("BUNGIE_REDIRECT_HOST")


@dataclass
class The100Config:
    api_key: str
    base_url: str

    def __init__(self):
        self.api_key = os.environ.get("THE100_API_KEY")
        self.base_url = os.environ.get("THE100_API_URL")


@dataclass
class TwitterConfig:
    consumer_key: str
    consumer_secret: str
    access_token: str
    access_token_secret: str

    def __init__(self):
        self.consumer_key = os.environ.get("TWITTER_CONSUMER_KEY")
        self.consumer_secret = os.environ.get("TWITTER_CONSUMER_SECRET")
        self.access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
        self.access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

    def asdict(self):
        return asdict(self)


@dataclass
class Config:
    bungie: BungieConfig
    the100: The100Config
    twitter: TwitterConfig
    database_url: str
    discord_api_key: str
    redis_url: str
    home_server: int
    log_channel: int
    reg_channel: int
    enable_activity_tracking: bool
    activity_cutoff: str

    def __init__(self):
        self.bungie = BungieConfig()
        self.the100 = The100Config()
        self.twitter = TwitterConfig()
        self.database_url = os.environ.get("DATABASE_URL")
        self.discord_api_key = os.environ.get("DISCORD_API_KEY")
        self.redis_url = os.environ.get("REDIS_URL")
        self.home_server = int(os.environ.get("HOME_SERVER"))
        self.log_channel = int(os.environ.get("HOME_SERVER_LOG_CHANNEL"))
        self.reg_channel = int(os.environ.get("HOME_SERVER_REG_CHANNEL"))
        self.enable_activity_tracking = os.environ.get("ENABLE_ACTIVITY_TRACKING") == "True"
        self.activity_cutoff = datetime.strptime(os.environ.get("ACTIVITY_CUTOFF"), "%Y-%m-%d").astimezone(tz=pytz.utc)
