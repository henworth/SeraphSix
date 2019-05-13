from datetime import datetime
from trent_six.destiny import constants


class UserMembership(object):

    def __init__(self):
        self.id = None
        self.username = None

    def __call__(self, details):
        self.id = int(details['membershipId'])
        self.username = details['displayName']


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
        if not 'membershipType' in entry.keys():
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


class Member(User):

    def __init__(self, details):
        super().__init__(details)
        self.join_date = datetime.strptime(
            details['joinDate'], '%Y-%m-%dT%H:%M:%S%z')
        self.member_type = int(details['memberType'])
        self.is_online = details['isOnline']
        self.last_online_status_change = datetime.utcfromtimestamp(
            int(details['lastOnlineStatusChange']))
        self.group_id = int(details['groupId'])


class Game(object):
    def __init__(self, details):
        self.players = []
        self.mode_id = details['activityDetails']['mode']
        self.instance_id = int(details['activityDetails']['instanceId'])
        self.reference_id = details['activityDetails']['referenceId']
        self.date = datetime.strptime(details['period'], '%Y-%m-%dT%H:%M:%S%z')

        for entry in details['entries']:
            completed = True
            if entry['values']['completed']['basic']['displayValue'] == 'No':
                completed = False

            try:
                name = entry['player']['destinyUserInfo']['displayName']
            except KeyError:
                name = None

            self.players.append({
                'name': name,
                'completed': completed
            })
