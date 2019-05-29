from seraphsix.bot import SeraphSix
from seraphsix.database import Database
from seraphsix.tasks import config

import asyncio
import logging
import warnings

from peony import PeonyClient
from pydest import Pydest
from the100 import The100

warnings.filterwarnings('ignore', category=UserWarning, module='psycopg2')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('aiohttp.client').setLevel(logging.ERROR)
    logging.getLogger('aioredis').setLevel(logging.DEBUG)
    logging.getLogger('backoff').setLevel(logging.DEBUG)

    config = config.load()

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

    bot = SeraphSix(loop=loop, config=config, destiny=destiny,
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
