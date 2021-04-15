import datetime

from seraphsix import constants


def member_hash(member):
    return f'{member.membership_type}-{member.membership_id}'


def member_hash_db(member_db, platform_id):
    membership_id, _ = parse_platform(member_db, platform_id)
    return f'{platform_id}-{membership_id}'


def parse_platform(member_db, platform_id):
    if platform_id == constants.PLATFORM_BUNGIE:
        member_id = member_db.bungie_id
        member_username = member_db.bungie_username
    elif platform_id == constants.PLATFORM_PSN:
        member_id = member_db.psn_id
        member_username = member_db.psn_username
    elif platform_id == constants.PLATFORM_XBOX:
        member_id = member_db.xbox_id
        member_username = member_db.xbox_username
    elif platform_id == constants.PLATFORM_BLIZZARD:
        member_id = member_db.blizzard_id
        member_username = member_db.blizzard_username
    elif platform_id == constants.PLATFORM_STEAM:
        member_id = member_db.steam_id
        member_username = member_db.steam_username
    elif platform_id == constants.PLATFORM_STADIA:
        member_id = member_db.stadia_id
        member_username = member_db.stadia_username
    return member_id, member_username


def encode_datetime(obj):
    if isinstance(obj, datetime.datetime):
        return {'__datetime__': True, 'as_str': obj.strftime(constants.DESTINY_DATE_FORMAT)}
    return obj


def decode_datetime(obj):
    if '__datetime__' in obj:
        obj = datetime.datetime.strptime(obj['as_str'], constants.DESTINY_DATE_FORMAT)
    return obj
