import logging
import pytz

from datetime import datetime


class UTCFormatter(logging.Formatter):
    converter = datetime.fromtimestamp

    def formatTime(self, record, datefmt=None, timezone="UTC"):
        retval = self.converter(record.created, tz=pytz.timezone(timezone))
        if datefmt:
            return retval.strftime(datefmt)
        else:
            return retval.isoformat()
