from datetime import datetime
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config
from typing import Optional
from seraphsix import constants
from seraphsix.cogs.utils.helpers import destiny_date_as_utc
from seraphsix.tasks.parsing import member_hash, member_hash_db


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
    membership_id: str
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
        self.id = int(details['membershipId'])
        self.username = details['displayName']

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
        self.primary_membership_id = details.get('primaryMembershipId')

        if details.get('destinyUserInfo'):
            self._process_membership(details['destinyUserInfo'])
        elif details.get('destinyMemberships'):
            for entry in details['destinyMemberships']:
                self._process_membership(entry)

        if details.get('bungieNetUserInfo'):
            self._process_membership(details['bungieNetUserInfo'])

        if details.get('bungieNetUser'):
            self._process_membership(details['bungieNetUser'])

    def _process_membership(self, entry):
        if 'membershipType' not in entry.keys():
            self.memberships.bungie(entry)
        else:
            if entry['membershipType'] == constants.PLATFORM_XBOX:
                self.memberships.xbox(entry)
            elif entry['membershipType'] == constants.PLATFORM_PSN:
                self.memberships.psn(entry)
            elif entry['membershipType'] == constants.PLATFORM_BLIZZARD:
                self.memberships.blizzard(entry)
            elif entry['membershipType'] == constants.PLATFORM_STEAM:
                self.memberships.steam(entry)
            elif entry['membershipType'] == constants.PLATFORM_STADIA:
                self.memberships.stadia(entry)
            elif entry['membershipType'] == constants.PLATFORM_BUNGIE:
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
            stadia_username=self.memberships.stadia.username
        )


class Member(User):

    def __init__(self, details, user_details):
        super().__init__(user_details)
        self.join_date = destiny_date_as_utc(details['joinDate'])
        self.is_online = details['isOnline']
        self.last_online_status_change = datetime.utcfromtimestamp(int(details['lastOnlineStatusChange']))
        self.group_id = int(details['groupId'])
        self.member_type = details['memberType']

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
    def __init__(self, details, api=True):
        if not api:
            self.membership_id = details['membership_id']
            self.membership_type = details['membership_type']
            self.completed = details['completed']
            self.name = details['name']
            self.time_played = details['time_played']
        else:
            self.membership_id = details['player']['destinyUserInfo']['membershipId']
            self.membership_type = details['player']['destinyUserInfo']['membershipType']

            self.completed = False
            if details['values']['completed']['basic']['displayValue'] == 'Yes':
                self.completed = True

            try:
                self.name = details['player']['destinyUserInfo']['displayName']
            except KeyError:
                self.name = None

            try:
                self.time_played = details['values']['timePlayedSeconds']['basic']['value']
            except KeyError:
                self.time_played = 0.0

    def __str__(self):
        return f"<{type(self).__name__}: {self.membership_type}-{self.membership_id}>"

    def __repr__(self):
        return str(self.__dict__)


class Game(object):
    def __init__(self, details, api=True):
        if not api:
            self.mode_id = details['mode_id']
            self.instance_id = details['instance_id']
            self.reference_id = details['reference_id']
            self.date = datetime.strptime(details['date'], constants.DESTINY_DATE_FORMAT)
            self.players = [Player(player, api=False) for player in details['players']]
        else:
            self.mode_id = details['activityDetails']['mode']
            if self.mode_id == 0:
                modes = details['activityDetails']['modes']
                modes.sort()
                try:
                    self.mode_id = modes[-1]
                except IndexError:
                    pass
            self.instance_id = int(details['activityDetails']['instanceId'])
            self.reference_id = details['activityDetails']['referenceId']
            self.date = destiny_date_as_utc(details['period'])
            self.players = []

    def set_players(self, details):
        for entry in details['entries']:
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
