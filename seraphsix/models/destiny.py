from datetime import datetime
from seraphsix import constants


class UserMembership(object):

    def __init__(self):
        self.id = None
        self.username = None

    def __call__(self, details):
        self.id = int(details['membershipId'])
        self.username = details['displayName']

    def __repr__(self):
        return f'<{type(self).__name__}: {self.username}-{self.id}>'


class User(object):

    class Memberships(object):
        def __init__(self):
            self.blizzard = UserMembership()
            self.bungie = UserMembership()
            self.psn = UserMembership()
            self.xbox = UserMembership()

    def __init__(self, details):
        self.memberships = self.Memberships()

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
            if entry['membershipType'] == constants.PLATFORM_BLIZ:
                self.memberships.blizzard(entry)
            elif entry['membershipType'] == constants.PLATFORM_XBOX:
                self.memberships.xbox(entry)
            elif entry['membershipType'] == constants.PLATFORM_PSN:
                self.memberships.psn(entry)
            elif entry['membershipType'] == constants.PLATFORM_BNG:
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
            blizzard_username=self.memberships.blizzard.username
        )


class Member(User):

    def __init__(self, details):
        super().__init__(details)
        self.join_date = datetime.strptime(
            details['joinDate'], '%Y-%m-%dT%H:%M:%S%z')
        self.is_online = details['isOnline']
        self.last_online_status_change = datetime.utcfromtimestamp(
            int(details['lastOnlineStatusChange']))
        self.group_id = int(details['groupId'])
        self.member_type = details['memberType']

        if self.memberships.blizzard.id:
            self.platform_id = constants.PLATFORM_BLIZ
            self.member_id = self.memberships.blizzard.id
        elif self.memberships.xbox.id:
            self.platform_id = constants.PLATFORM_XBOX
            self.member_id = self.memberships.xbox.id
        elif self.memberships.psn.id:
            self.platform_id = constants.PLATFORM_PSN
            self.member_id = self.memberships.psn.id

    def __repr__(self):
        return f'<{type(self).__name__}: {self.platform_id}-{self.member_id}>'

    def __str__(self):
        return f'{self.platform_id}-{self.member_id}'


class Player(object):
    def __init__(self, details):
        self.membership_id = details['player']['destinyUserInfo']['membershipId']
        self.membership_type = details['player']['destinyUserInfo']['membershipType']

        self.completed = False
        if details['values']['completed']['basic']['displayValue'] == 'Yes':
            self.completed = True

        try:
            self.name = details['player']['destinyUserInfo']['displayName']
        except KeyError:
            self.name = None

    def __repr__(self):
        return f'<{type(self).__name__}: {self.membership_type}-{self.membership_id}>'


class Game(object):
    def __init__(self, details):
        self.mode_id = details['activityDetails']['mode']
        self.instance_id = int(details['activityDetails']['instanceId'])
        self.reference_id = details['activityDetails']['referenceId']
        self.date = datetime.strptime(details['period'], '%Y-%m-%dT%H:%M:%S%z')

        self.players = []
        for entry in details['entries']:
            player = Player(entry)
            self.players.append(player)

    def __repr__(self):
        return f'<{type(self).__name__}: {self.instance_id}>'


class ClanGame(Game):
    def __init__(self, details, member_dbs):
        super().__init__(details)

        members = {}
        for member_db in member_dbs:
            if member_db.blizzard_id:
                members.update(
                    {f'{constants.PLATFORM_BLIZ}-{member_db.blizzard_id}': member_db})
            if member_db.psn_id:
                members.update(
                    {f'{constants.PLATFORM_PSN}-{member_db.psn_id}': member_db})
            if member_db.xbox_id:
                members.update(
                    {f'{constants.PLATFORM_XBOX}-{member_db.xbox_id}': member_db})

        # Loop through all players to find any members that completed
        # the game session. Also check if the member joined before
        # the game time.
        self.clan_players = []
        for player in self.players:
            player_hash = f'{player.membership_type}-{player.membership_id}'
            if player.completed and player_hash in members.keys():
                if self.date > members[player_hash].clanmember.join_date:
                    self.clan_players.append(members[player_hash])
