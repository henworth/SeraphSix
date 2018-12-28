# {'bungieNetUserInfo': {'displayName': 'HonestNixon93',
#                        'iconPath': '/img/profile/avatars/bungieday_16.jpg',
#                        'membershipId': '5721956',
#                        'membershipType': 254,
#                        'supplementalDisplayName': '5721956'},
#  'destinyUserInfo': {'displayName': 'HonestNixon93',
#                      'iconPath': '/img/theme/destiny/icons/icon_xbl.png',
#                      'membershipId': '4611686018431778531',
#                      'membershipType': 1},
#  'groupId': '803613',
#  'isOnline': False,
#  'joinDate': '2018-03-02T02:07:22Z',
#  'memberType': 2}

from datetime import datetime

class Member(object):
    bungie_username = None

    def __init__(self, details):
        self.bungie_id = int(details['destinyUserInfo']['membershipId'])
        self.xbox_username = details['destinyUserInfo']['displayName']
        self.join_date = details['joinDate']
        if 'bungieNetUserInfo' in details:
            self.bungie_username = details['bungieNetUserInfo']['displayName']


class Game(object):

    def __init__(self, details):
        self.players = []
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
            self.mode_id = details['activityDetails']['mode']
            self.date = datetime.strptime(details['period'], '%Y-%m-%dT%H:%M:%S%z')

async def get_all(destiny, group_id):
    group = await destiny.api.get_group_members(group_id)
    group_members = group['Response']['results']
    for member in group_members:
        yield Member(member)
