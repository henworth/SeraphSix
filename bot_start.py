from seraphsix.bot import SeraphSix
from seraphsix.constants import LOG_FORMAT_MSG, LOG_FORMAT_TIME
from seraphsix.tasks.config import Config

import logging
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='psycopg2')


def main():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(fmt=LOG_FORMAT_MSG, datefmt=LOG_FORMAT_TIME)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logging.getLogger('aiohttp.client').setLevel(logging.ERROR)
    logging.getLogger('aioredis').setLevel(logging.DEBUG)
    logging.getLogger('backoff').setLevel(logging.DEBUG)
    logging.getLogger('bot').setLevel(logging.DEBUG)
    logging.getLogger('seraphsix').setLevel(logging.DEBUG)

    config = Config()
    bot = SeraphSix(config)
    bot.run(config.discord_api_key)

if __name__ == '__main__':
    main()
