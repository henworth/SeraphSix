import asyncio
import pytz

from collections import OrderedDict
from datetime import datetime
from peewee import DoesNotExist
from seraphsix.constants import DESTINY_DATE_FORMAT, DESTINY_DATE_FORMAT_MS, DATE_FORMAT, DATE_FORMAT_TZ
from seraphsix.database import Member, ClanMember, Clan, Guild


def merge_dicts(a, b, path=None):
    # Merge dict `b` into dict `a`
    if path is None:
        path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dicts(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass  # same leaf value
            else:
                raise Exception(f"Conflict at {'.'.join(path + [str(key)])}")
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


def date_as_string(date, with_tz=False):
    if with_tz:
        date_format = DATE_FORMAT_TZ
    else:
        date_format = DATE_FORMAT
    return date.strftime(date_format)


def string_to_date(date, date_format=DATE_FORMAT):
    return datetime.strptime(date, date_format).astimezone(tz=pytz.utc)


def destiny_date_as_utc(date):
    try:
        return string_to_date(date, DESTINY_DATE_FORMAT_MS)
    except ValueError:
        return string_to_date(date, DESTINY_DATE_FORMAT)


def get_timezone_name(timezone, country_code):
    set_zones = set()
    # See if it's already a valid 'long' time zone name
    if '/' in timezone and timezone in pytz.all_timezones:
        set_zones.add(timezone)
        return set_zones

    # If it's a number value then use the Etc/GMT code
    try:
        offset = int(timezone)
        if offset > 0:
            offset = f"+{offset}"
        else:
            offset = str(offset)
        set_zones.add(f"Etc/GMT{offset}")
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


async def get_requestor(ctx):
    requestor_query = ctx.bot.database.get(
        Member.select(Member, ClanMember, Clan).join(ClanMember).join(Clan).join(Guild).where(
            Guild.guild_id == ctx.guild.id,
            Member.discord_id == ctx.author.id
        )
    )

    try:
        requestor_db = await asyncio.create_task(requestor_query)
    except DoesNotExist:
        requestor_db = None

    return requestor_db
