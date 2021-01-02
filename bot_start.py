import logging
import warnings

from seraphsix.bot import SeraphSix
from seraphsix.constants import LOG_FORMAT_MSG, BUNGIE_DATE_FORMAT
from seraphsix.tasks.config import Config
from seraphsix.utils import UTCFormatter

warnings.filterwarnings('ignore', category=UserWarning, module='psycopg2')


def main():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = UTCFormatter(fmt=LOG_FORMAT_MSG, datefmt=BUNGIE_DATE_FORMAT)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logging.getLogger('aiohttp.client').setLevel(logging.ERROR)
    logging.getLogger('aioredis').setLevel(logging.DEBUG)
    logging.getLogger('backoff').setLevel(logging.DEBUG)
    logging.getLogger('bot').setLevel(logging.DEBUG)
    logging.getLogger('seraphsix.tasks.discord').setLevel(logging.DEBUG)

    log = logging.getLogger(__name__)

    try:
        config = Config()
        bot = SeraphSix(config)
        bot.run(config.discord_api_key)
    except Exception:
        log.exception("Caught exception")


if __name__ == '__main__':
    main()
