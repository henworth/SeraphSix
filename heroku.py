import asyncio
import json
import os
import logging
import peony
import pydest
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='psycopg2')

from discord.ext.commands import Bot

from trent_six.bot import TrentSix
from trent_six.database import Database, Member


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('aiohttp.client').setLevel(logging.ERROR)

    config = None
    try:
        with open('config.json', encoding='utf-8', mode='r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logging.info("Config file config.json does not exist. Creating...")
    except json.decoder.JSONDecodeError:
        logging.info("Config file config.json format is invalid. Creating...")

    if not config:
        config = {
            'bungie_api_key': os.environ.get('BUNGIE_API_KEY'),
            'bungie_group_id': os.environ.get('GROUP_ID'),
            'database_url': os.environ.get('DATABASE_URL'),
            'discord_api_key': os.environ.get('DISCORD_API_KEY'),
            'iron_cache_creds': {
                'project_id': os.environ.get('IRON_CACHE_PROJECT_ID'),
                'token': os.environ.get('IRON_CACHE_TOKEN')
            },
            'twitter_creds': {
                'consumer_key': os.environ.get('CONSUMER_KEY'),
                'consumer_secret': os.environ.get('CONSUMER_SECRET'),
                'access_token': os.environ.get('ACCESS_TOKEN'),
                'access_token_secret': os.environ.get('ACCESS_TOKEN_SECRET')
            }
        }
        with open('config.json', encoding='utf-8', mode='w') as f:
            json.dump(config, f, indent=4, sort_keys=True, separators=(',', ':')) 

    loop = asyncio.new_event_loop()

    database = Database(config['database_url'], loop=loop)
    database.initialize()

    destiny = pydest.Pydest(config['bungie_api_key'], loop=loop)

    twitter = peony.PeonyClient(loop=loop, **config['twitter_creds'])

    bot = TrentSix(
        loop=loop, command_prefix='?',
        destiny=destiny, database=database, config=config, twitter=twitter
    )
    bot.run(config['discord_api_key'])

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        destiny.close()
        database.close()
    loop.close()
