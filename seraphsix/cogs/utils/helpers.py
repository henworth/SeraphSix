import pytz

from collections import OrderedDict
from datetime import datetime
from seraphsix.constants import BUNGIE_DATE_FORMAT


def merge_dicts(a, b, path=None):
    "merges b into a"
    if path is None:
        path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dicts(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass  # same leaf value
            else:
                raise Exception('Conflict at %s' % '.'.join(path + [str(key)]))
        else:
            a[key] = b[key]
    return a


def sort_dict(d):
    res = OrderedDict()
    for k, v in sorted(d.items()):
        if isinstance(v, dict):
            res[k] = sort_dict(v)
        else:
            res[k] = v
    return res


def bungie_date_as_utc(date):
    return datetime.strptime(date, BUNGIE_DATE_FORMAT).astimezone(tz=pytz.utc)


def get_timezone_name(timezone, country_code):
    set_zones = set()
    # See if it's already a valid "long" time zone name
    if '/' in timezone and timezone in pytz.all_timezones:
        set_zones.add(timezone)
        return set_zones

    # If it's a number value then use the Etc/GMT code
    try:
        offset = int(timezone)
        if offset > 0:
            offset = '+' + str(offset)
        else:
            offset = str(offset)
        set_zones.add('Etc/GMT' + offset)
        return set_zones
    except ValueError:
        pass

    timezones = []
    try:
        # Find all timezones in the supplied country code
        timezones = pytz.country_timezones[country_code]
    except KeyError:
        # Invalid country code, try to match the timezone abbreviation to any time zone
        timezones = pytz.all_timezones

    for name in timezones:
        tzone = pytz.timezone(name)
        transition_info = getattr(tzone, '_transition_info', [[None, None, datetime.now(tzone).tzname()]])
        for utcoffset, dstoffset, tzabbrev in transition_info:
            if tzabbrev.upper() == timezone.upper():
                set_zones.add(name)

    return set_zones
