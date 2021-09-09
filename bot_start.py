import logging
import logging.config

from seraphsix.bot import SeraphSix
from seraphsix.tasks.config import Config, log_config


def main():
    try:
        config = Config()
        logging.config.dictConfig(log_config(config.root_log_level))
        log = logging.getLogger(__name__)
        bot = SeraphSix(config)
        bot.run(config.discord_api_key)
    except Exception:
        logging.config.dictConfig(log_config("DEBUG"))
        log = logging.getLogger(__name__)
        log.exception("Caught exception")


if __name__ == "__main__":
    main()
