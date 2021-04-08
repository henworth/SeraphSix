import logging
import logging.config
import warnings

from seraphsix.bot import SeraphSix
from seraphsix.tasks.config import Config, log_config

warnings.filterwarnings('ignore', category=UserWarning, module='psycopg2')


def main():
    logging.config.dictConfig(log_config())
    log = logging.getLogger(__name__)

    try:
        config = Config()
        bot = SeraphSix(config)
        bot.run(config.discord_api_key)
    except Exception:
        log.exception("Caught exception")


if __name__ == '__main__':
    main()
