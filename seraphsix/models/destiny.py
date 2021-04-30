from datetime import datetime, timezone
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config, LetterCase
from marshmallow import fields
from typing import Optional, List, Dict, Any

from seraphsix import constants
from seraphsix.tasks.parsing import member_hash, member_hash_db


def encode_datetime(obj):
    return obj.strftime(constants.DESTINY_DATE_FORMAT_API)


def decode_datetime(obj):
    try:
        return datetime.strptime(obj, constants.DESTINY_DATE_FORMAT)
    except ValueError:
        return datetime.strptime(obj, constants.DESTINY_DATE_FORMAT_MS)


def encode_datetime_timestamp(obj):
    return str(int(datetime.timestamp(obj)))


def decode_datetime_timestamp(obj):
    return datetime.fromtimestamp(float(obj)).astimezone(tz=timezone.utc)


def encode_id_string(obj):
    return str(obj)


def decode_id_string(obj):
    if obj:
        return int(obj)
    else:
        return None


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyUserInfo:
    cross_save_override: int
    applicable_membership_types: List[int]
    is_public: bool
    membership_type: int
    membership_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    last_seen_display_name: Optional[str] = field(
        metadata=config(field_name='LastSeenDisplayName'),
        default=None
    )
    last_seen_display_name_type: Optional[int] = field(
        metadata=config(field_name='LastSeenDisplayNameType'),
        default=None
    )
    display_name: Optional[str] = None
    icon_path: Optional[str] = None


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyBungieNetUserInfo:
    supplemental_display_name: str
    icon_path: str
    cross_save_override: int
    is_public: bool
    membership_type: int
    membership_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    display_name: str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyProfileData:
    user_info: DestinyUserInfo
    date_last_played: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    versions_owned: int
    character_ids: List[int]
    season_hashes: List[int]
    current_season_hash: int
    current_season_reward_power_cap: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyProfile:
    data: DestinyProfileData
    privacy: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyProfileResponse:
    profile: DestinyProfile


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyCharacterData:
    membership_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    membership_type: int
    character_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    date_last_played: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    minutes_played_this_session: str
    minutes_played_total: str
    light: int
    stats: Dict[str, int]
    race_hash: int
    gender_hash: int
    class_hash: int
    race_type: int
    class_type: int
    gender_type: int
    emblem_path: str
    emblem_background_path: str
    emblem_hash: int
    emblem_color: Dict[str, int]
    level_progression: Dict[str, int]
    base_character_level: int
    percent_to_next_level: int
    title_record_hash: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyCharacter:
    data: Dict[int, DestinyCharacterData]
    privacy: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyCharacterResponse:
    characters: DestinyCharacter


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyActivityStatValue:
    value: float
    display_value:  str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyActivityStat:
    basic: DestinyActivityStatValue
    stat_id: Optional[str] = None


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyActivityDetails:
    reference_id: int
    director_activity_hash: int
    instance_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    mode: int
    modes: List[int]
    is_private: bool
    membership_type: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyActivity:
    period: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    activity_details: DestinyActivityDetails
    values: Dict[str, DestinyActivityStat]


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyActivityResponse:
    activities: List[DestinyActivity]


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyPlayer:
    destiny_user_info: DestinyUserInfo
    character_class: str
    class_hash: int
    race_hash: int
    gender_hash: int
    character_level: int
    light_level: int
    emblem_hash: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyPGCRWeapon:
    reference_id: int
    values: Dict[str, DestinyActivityStat]


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyPGCRExtended:
    values: Dict[str, DestinyActivityStat]
    weapons: Optional[List[DestinyPGCRWeapon]] = None


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyPGCREntry:
    standing: int
    player: DestinyPlayer
    score: DestinyActivityStat
    character_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    values: Dict[str, DestinyActivityStat]
    extended: DestinyPGCRExtended


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyPGCR:
    period: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    activity_details: DestinyActivityDetails
    starting_phase_index: int
    entries: List[DestinyPGCREntry]
    teams: List[Any]


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyMembership:
    # Basically the same as DestinyUserInfo with the addition of the "LastSeen" fields
    # TODO Consolidate these two?
    last_seen_display_name: str = field(metadata=config(field_name='LastSeenDisplayName'))
    last_seen_display_name_type: int = field(metadata=config(field_name='LastSeenDisplayNameType'))
    icon_path: str
    cross_save_override: int
    applicable_membership_types: List[int]
    is_public: bool
    membership_type: int
    membership_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    display_name: str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyBungieNetUser:
    membership_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    unique_name: str
    display_name: str
    profile_picture: int
    profile_theme: int
    user_title: int
    success_message_flags: str
    is_deleted: bool
    about: str
    first_access: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    last_update: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    show_activity: bool
    locale: str
    locale_inherit_default: bool
    show_group_messaging: bool
    profile_picture_path: str
    profile_theme_name: str
    user_title_display: str
    status_text: str
    status_date: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    psn_display_name: Optional[str] = None
    xbox_display_name: Optional[str] = None
    steam_display_name: Optional[str] = None
    stadia_display_name: Optional[str] = None
    twitch_display_name: Optional[str] = None
    blizzard_display_name: Optional[str] = None
    fb_display_name: Optional[str] = None


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyMembershipResponse:
    destiny_memberships: List[DestinyMembership]
    bungie_net_user: Optional[DestinyBungieNetUser] = None
    primary_membership_id: Optional[int] = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        ),
        default=None
    )


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupMember:
    member_type: int
    is_online: bool
    last_online_status_change: datetime = field(
        metadata=config(
            encoder=encode_datetime_timestamp,
            decoder=decode_datetime_timestamp,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    group_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    destiny_user_info: DestinyUserInfo
    join_date: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    bungie_net_user_info: Optional[DestinyBungieNetUserInfo] = None


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupMembersResponse:
    results: List[DestinyGroupMember]
    total_results: int
    has_more: bool
    query: Dict[str, int]
    use_total_results: bool


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupFeatures:
    maximum_members: int
    maximum_memberships_of_group_type: int
    capabilities: int
    membership_types: List[int]
    invite_permission_override: bool
    update_culture_permission_override: bool
    host_guidedGame_permission_override: int
    update_banner_permission_override: bool
    join_level: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupD2ClanProgression:
    progression_hash: int
    daily_progress: int
    daily_limit: int
    weekly_progress: int
    weekly_limit: int
    current_progress: int
    level: int
    level_cap: int
    step_index: int
    progress_to_next_level: int
    next_level_at: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupClanBannerData:
    decal_id: int
    decal_color_id: int
    decal_background_color_id: int
    gonfalon_id: int
    gonfalon_color_id: int
    gonfalon_detail_id: int
    gonfalon_detail_color_id: int


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupClanInfo:
    d2_clan_progressions: Dict[int, DestinyGroupD2ClanProgression]
    clan_callsign: str
    clan_banner_data: DestinyGroupClanBannerData


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupDetail:
    group_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    name: str
    group_type: int
    membership_id_created: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    creation_date: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    modification_date: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    about: str
    tags: List[Any]
    member_count: int
    is_public: bool
    is_public_topic_admin_only: bool
    motto: str
    allow_chat: bool
    is_default_post_public: bool
    chat_security: int
    locale: str
    avatar_image_index: int
    homepage: int
    membership_option: int
    default_publicity: int
    theme: str
    banner_path: str
    avatar_path: str
    conversation_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    enable_invitation_messaging_for_admins: bool
    ban_expire_date: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    features: DestinyGroupFeatures
    clan_info: DestinyGroupClanInfo


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupResponse:
    detail: DestinyGroupDetail
    founder: DestinyGroupMember
    allied_ids: List[int]
    alliance_status: int
    group_join_invite_count: int
    current_user_memberships_inactive_for_destiny: bool
    current_user_member_map: Dict[Any, Any]
    current_user_potential_member_map: Dict[Any, Any]


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyMemberGroup:
    member: DestinyGroupMember
    group: DestinyGroupDetail


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyMemberGroupResponse:
    results: List[DestinyMemberGroup]
    total_results: int
    has_more: bool
    query: Dict[str, int]
    use_total_results: bool
    are_all_memberships_inactive: Dict[str, bool]


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupPendingMember:
    group_id: int = field(
        metadata=config(
            encoder=encode_id_string,
            decoder=decode_id_string,
            mm_field=fields.Integer()
        )
    )
    creation_date: datetime = field(
        metadata=config(
            encoder=encode_datetime,
            decoder=decode_datetime,
            mm_field=fields.DateTime(format=constants.DESTINY_DATE_FORMAT)
        )
    )
    resolve_state: int
    destiny_user_info: DestinyUserInfo
    bungie_net_user_info: Optional[DestinyBungieNetUserInfo] = None


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class DestinyGroupPendingMembersResponse:
    results: List[DestinyGroupPendingMember]
    total_results: int
    has_more: bool
    query: Dict[str, int]
    use_total_results: bool


@dataclass_json
@dataclass
class DestinyResponse:
    error_code: int = field(metadata=config(field_name='ErrorCode'))
    error_status: str = field(metadata=config(field_name='ErrorStatus'))
    message: str = field(metadata=config(field_name='Message'))
    message_data: object = field(metadata=config(field_name='MessageData'))
    throttle_seconds: int = field(metadata=config(field_name='ThrottleSeconds'))
    response: Optional[object] = field(metadata=config(field_name='Response'), default=None)


@dataclass_json
@dataclass
class DestinyTokenResponse:
    access_token: str
    expires_in: int
    membership_id: int
    refresh_token: str
    refresh_expires_in: int
    token_type: str
    error: Optional[str] = None


@dataclass_json
@dataclass
class DestinyTokenErrorResponse:
    error: str
    error_description: str


class UserMembership(object):

    def __init__(self):
        self.id = None
        self.username = None

    def __call__(self, details):
        self.id = details.membership_id
        self.username = details.display_name

    def __repr__(self):
        return f"<{type(self).__name__}: {self.username}-{self.id}>"


class User(object):

    class Memberships(object):
        def __init__(self):
            self.bungie = UserMembership()
            self.psn = UserMembership()
            self.xbox = UserMembership()
            self.blizzard = UserMembership()
            self.steam = UserMembership()
            self.stadia = UserMembership()

    def __init__(self, details):
        self.memberships = self.Memberships()
        self.primary_membership_id = details.primary_membership_id
        self.is_cross_save = self.primary_membership_id is not None

        if hasattr(details, 'destiny_user_info'):
            self._process_membership(details.destiny_user_info)
        elif hasattr(details, 'destiny_memberships'):
            for entry in details.destiny_memberships:
                self._process_membership(entry)

        if hasattr(details, 'bungie_net_user_info'):
            self._process_membership(details.bungie_net_user_info)

        if hasattr(details, 'bungie_net_user'):
            self._process_membership(details.bungie_net_user)

    def _process_membership(self, entry):
        if not hasattr(entry, 'membership_id'):
            return
        if not hasattr(entry, 'membership_type'):
            self.memberships.bungie(entry)
        else:
            if entry.membership_type == constants.PLATFORM_XBOX:
                self.memberships.xbox(entry)
            elif entry.membership_type == constants.PLATFORM_PSN:
                self.memberships.psn(entry)
            elif entry.membership_type == constants.PLATFORM_BLIZZARD:
                self.memberships.blizzard(entry)
            elif entry.membership_type == constants.PLATFORM_STEAM:
                self.memberships.steam(entry)
            elif entry.membership_type == constants.PLATFORM_STADIA:
                self.memberships.stadia(entry)
            elif entry.membership_type == constants.PLATFORM_BUNGIE:
                self.memberships.bungie(entry)

    def to_dict(self):
        return dict(
            bungie_id=self.memberships.bungie.id,
            bungie_username=self.memberships.bungie.username,
            xbox_id=self.memberships.xbox.id,
            xbox_username=self.memberships.xbox.username,
            psn_id=self.memberships.psn.id,
            psn_username=self.memberships.psn.username,
            blizzard_id=self.memberships.blizzard.id,
            blizzard_username=self.memberships.blizzard.username,
            steam_id=self.memberships.steam.id,
            steam_username=self.memberships.steam.username,
            stadia_id=self.memberships.stadia.id,
            stadia_username=self.memberships.stadia.username,
            primary_membership_id=self.primary_membership_id,
            is_cross_save=self.is_cross_save
        )


class Member(User):

    def __init__(self, details, user_details):
        super().__init__(user_details)
        self.join_date = details.join_date
        self.is_online = details.is_online
        self.last_online_status_change = details.last_online_status_change
        self.group_id = details.group_id
        self.member_type = details.member_type

        if self.memberships.xbox.id:
            self.platform_id = constants.PLATFORM_XBOX
            self.member_id = self.memberships.xbox.id
        elif self.memberships.psn.id:
            self.platform_id = constants.PLATFORM_PSN
            self.member_id = self.memberships.psn.id
        elif self.memberships.blizzard.id:
            self.platform_id = constants.PLATFORM_BLIZZARD
            self.member_id = self.memberships.blizzard.id
        elif self.memberships.steam.id:
            self.platform_id = constants.PLATFORM_STEAM
            self.member_id = self.memberships.steam.id
        elif self.memberships.stadia.id:
            self.platform_id = constants.PLATFORM_STADIA
            self.member_id = self.memberships.stadia.id

    def __repr__(self):
        return f"<{type(self).__name__}: {self.platform_id}-{self.member_id}>"

    def __str__(self):
        return f"{self.platform_id}-{self.member_id}"


class Player(object):
    def __init__(self, details):
        self.membership_id = details.player.destiny_user_info.membership_id
        self.membership_type = details.player.destiny_user_info.membership_type
        self.name = details.player.destiny_user_info.display_name

        self.completed = False
        if details.values['completed'].basic.display_value == 'Yes':
            self.completed = True

        try:
            self.time_played = details.values['timePlayedSeconds'].basic.value
        except KeyError:
            self.time_played = 0.0

    def __str__(self):
        return f"<{type(self).__name__}: {self.membership_type}-{self.membership_id}>"

    def __repr__(self):
        return str(self.__dict__)


class Game(object):
    def __init__(self, details):
        self.mode_id = details.activity_details.mode
        if self.mode_id == 0:
            modes = details.activity_details.modes
            modes.sort()
            try:
                self.mode_id = modes[-1]
            except IndexError:
                pass
        self.instance_id = int(details.activity_details.instance_id)
        self.reference_id = details.activity_details.reference_id
        self.date = details.period
        self.players = []

    def set_players(self, details):
        for entry in details.entries:
            player = Player(entry)
            self.players.append(player)

    def __str__(self):
        return f"<{type(self).__name__}: {self.instance_id}>"

    def __repr__(self):
        retval = self.__dict__
        retval['date'] = self.date.strftime(constants.DESTINY_DATE_FORMAT)
        return str(retval)


class ClanGame(Game):
    def __init__(self, details, member_dbs):
        self.clan_id = member_dbs[0].clan_id
        super().__init__(details)
        self.set_players(details)

        members = {}
        for member_db in member_dbs:
            member = member_db.member
            if member.psn_id:
                members.update(
                    {member_hash_db(member, constants.PLATFORM_PSN): member_db}
                )
            if member.xbox_id:
                members.update(
                    {member_hash_db(member, constants.PLATFORM_XBOX): member_db}
                )
            if member.blizzard_id:
                members.update(
                    {member_hash_db(member, constants.PLATFORM_BLIZZARD): member_db}
                )
            if member.steam_id:
                members.update(
                    {member_hash_db(member, constants.PLATFORM_STEAM): member_db}
                )
            if member.stadia_id:
                members.update(
                    {member_hash_db(member, constants.PLATFORM_STADIA): member_db}
                )

        # Loop through all players to find clan members in the game session.
        # Also check if the member joined before the game time.
        self.clan_players = []
        for player in self.players:
            player_hash = member_hash(player)
            if player_hash in members.keys() and self.date > members[player_hash].join_date:
                self.clan_players.append(player)
