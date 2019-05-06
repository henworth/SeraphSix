from datetime import datetime
from trent_six.destiny import constants


class User(object):

    class memberships(object):
        pass

    def __init__(self, details):
        if details.get('destinyUserInfo'):
            self._process_membership(details['destinyUserInfo'])
        elif details.get('destinyMemberships'):
            for entry in details['destinyMemberships']:
                self._process_membership(entry)
            self.memberships.bungie = UserMembership(details['bungieNetUser'])

        if details.get('bungieNetUserInfo'):
            self._process_membership(details['bungieNetUserInfo'])

    def _process_membership(self, entry):
        if entry['membershipType'] == constants.PLATFORM_BLIZ:
            self.memberships.blizzard = UserMembership(entry)
        elif entry['membershipType'] == constants.PLATFORM_XBOX:
            self.memberships.xbox = UserMembership(entry)
        elif entry['membershipType'] == constants.PLATFORM_PSN:
            self.memberships.psn = UserMembership(entry)
        elif entry['membershipType'] == constants.PLATFORM_BNG:
            self.memberships.bungie = UserMembership(entry)


class UserMembership(object):

    def __init__(self, details):
        self.id = int(details['membershipId'])
        self.username = details['displayName']


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
