from datetime import datetime
from trent_six.destiny import constants


class User(object):

    class memberships(object):
        pass

    def __init__(self, details):
        for entry in details['destinyMemberships']:
            if entry['membershipType'] == constants.PLATFORM_BLIZ:
                self.memberships.blizzard = UserMembership(entry)
            elif entry['membershipType'] == constants.PLATFORM_XBOX:
                self.memberships.xbox = UserMembership(entry)
            elif entry['membershipType'] == constants.PLATFORM_PSN:
                self.memberships.psn = UserMembership(entry)
        self.memberships.bungie = UserMembership(details['bungieNetUser'])


class UserMembership(object):

    def __init__(self, details):
        self.id = details['membershipId']
        self.username = details['displayName']


class Member(object):
    bungie_username = None

    def __init__(self, details):
        self.bungie_id = int(details['destinyUserInfo']['membershipId'])
        self.xbox_id = int()
        self.xbox_username = details['destinyUserInfo']['displayName']
        self.join_date = details['joinDate']
        if 'bungieNetUserInfo' in details:
            self.bungie_username = details['bungieNetUserInfo']['displayName']


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
