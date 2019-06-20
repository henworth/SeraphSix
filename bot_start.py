from seraphsix.bot import SeraphSix
from seraphsix.constants import LOG_FORMAT_MSG, LOG_FORMAT_TIME
from seraphsix.tasks.config import load_config

import logging
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='psycopg2')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT_MSG, datefmt=LOG_FORMAT_TIME)
    logging.getLogger('aiohttp.client').setLevel(logging.ERROR)
    logging.getLogger('aioredis').setLevel(logging.DEBUG)
    logging.getLogger('backoff').setLevel(logging.DEBUG)

    config = load_config()
    bot = SeraphSix(config)
    bot.run(config['discord_api_key'])
