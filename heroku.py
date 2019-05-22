from trent_six.bot import TrentSix
from trent_six.database import Database

import asyncio
import json
import os
import logging
import warnings

from peony import PeonyClient
from pydest import Pydest
from the100 import The100

warnings.filterwarnings('ignore', category=UserWarning, module='psycopg2')


def config_loader(filename='config.json'):
    config = None
    try:
        with open(filename, encoding='utf-8', mode='r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logging.info("Config file config.json does not exist. Creating...")
    except json.decoder.JSONDecodeError:
        logging.info("Config file config.json format is invalid. Creating...")

    if not config:
        config = {
            'bungie': {
                'api_key': os.environ.get('BUNGIE_API_KEY'),
                'client_id': os.environ.get('BUNGIE_CLIENT_ID'),
                'client_secret': os.environ.get('BUNGIE_CLIENT_SECRET'),
                'redirect_host': os.environ.get('BUNGIE_REDIRECT_HOST')
            },
            'database_url': os.environ.get('DATABASE_URL'),
            'discord_api_key': os.environ.get('DISCORD_API_KEY'),
            'iron_cache': {
                'project_id': os.environ.get('IRON_CACHE_PROJECT_ID'),
                'token': os.environ.get('IRON_CACHE_TOKEN')
            },
            'redis_url': os.environ.get('REDIS_URL'),
            'the100_api_key': os.environ.get('THE100_API_KEY'),
            'twitter': {
                'consumer_key': os.environ.get('TWITTER_CONSUMER_KEY'),
                'consumer_secret': os.environ.get('TWITTER_CONSUMER_SECRET'),
                'access_token': os.environ.get('TWITTER_ACCESS_TOKEN'),
                'access_token_secret': os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
            }
        }
        with open(filename, encoding='utf-8', mode='w') as f:
            json.dump(config, f, indent=4, sort_keys=True,
                      separators=(',', ':'))
    return config


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('aiohttp.client').setLevel(logging.ERROR)

    config = config_loader()

    loop = asyncio.new_event_loop()

    database = Database(config['database_url'], loop=loop)
    database.initialize()

    destiny = Pydest(
        api_key=config['bungie']['api_key'],
        loop=loop,
        client_id=config['bungie']['client_id'],
        client_secret=config['bungie']['client_secret']
    )

    the100 = The100(config['the100_api_key'], loop=loop)

    twitter = None
    if (config['twitter'].get('consumer_key') and
            config['twitter'].get('consumer_secret') and
            config['twitter'].get('access_token') and
            config['twitter'].get('access_token_secret')):
        twitter = PeonyClient(loop=loop, **config['twitter'])

    bot = TrentSix(loop=loop, config=config, destiny=destiny,
                   database=database, the100=the100, twitter=twitter)
    bot.run(config['discord_api_key'])

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        destiny.close()
        database.close()
        the100.close()
        if twitter:
            asyncio.ensure_future(twitter.close())
    loop.close()
