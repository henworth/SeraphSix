import discord
from datetime import datetime

BLUE = discord.Colour(3381759)
CLEANUP_DELAY = 4

PLATFORM_XBOX = 1
PLATFORM_PSN = 2
PLATFORM_BLIZ = 4
PLATFORM_BNG = 254

PLATFORM_MAP = {
    'xbox': PLATFORM_XBOX,
    'psn': PLATFORM_PSN,
    'blizzard': PLATFORM_BLIZ,
    'bungie': PLATFORM_BNG
}

CLAN_MEMBER_NONE = 0
CLAN_MEMBER_BEGINNER = 1
CLAN_MEMBER_MEMBER = 2
CLAN_MEMBER_ADMIN = 3
CLAN_MEMBER_ACTING_FOUNDER = 4
CLAN_MEMBER_FOUNDER = 5

COMPONENT_CHARACTERS = 200

MODE_STRIKE = 3
MODE_RAID = 4
MODE_NIGHTFALL = 46

MODE_PVP_MAYHEM = 25
MODE_PVP_SUPREMACY = 31
MODE_PVP_SURVIVAL = 37
MODE_PVP_COUNTDOWN = 38
MODE_PVP_IRONBANNER_CONTROL = 43
MODE_PVP_IRONBANNER_CLASH = 44
MODE_PVP_DOUBLES = 50
MODE_PVP_LOCKDOWN = 60
MODE_PVP_BREAKTHROUGH = 65
MODE_PVP_CLASH_QUICK = 71
MODE_PVP_CLASH_COMP = 72
MODE_PVP_CONTROL_QUICK = 73
MODE_PVP_CONTROL_COMP = 74

MODE_GAMBIT = 63
MODE_GAMBIT_PRIME = 75
MODE_GAMBIT_RECKONING = 76

MODE_FORGE = 66

MODES_PVP_QUICK = [
    MODE_PVP_MAYHEM, MODE_PVP_SUPREMACY, MODE_PVP_DOUBLES,
    MODE_PVP_LOCKDOWN, MODE_PVP_BREAKTHROUGH,
    MODE_PVP_IRONBANNER_CONTROL, MODE_PVP_IRONBANNER_CLASH,
    MODE_PVP_CLASH_QUICK, MODE_PVP_CONTROL_QUICK
]

MODES_PVP_COMP = [
    MODE_PVP_SURVIVAL, MODE_PVP_COUNTDOWN,
    MODE_PVP_CLASH_COMP, MODE_PVP_CONTROL_COMP
]

MODES_GAMBIT = [
    MODE_GAMBIT, MODE_GAMBIT_PRIME, MODE_GAMBIT_RECKONING
]

MODES_STRIKE = [
    MODE_STRIKE, MODE_NIGHTFALL
]

MODE_MAP = {
    MODE_STRIKE: {'title': 'strike', 'player_count': 3, 'threshold': 2},
    MODE_RAID: {'title': 'raid', 'player_count': 6, 'threshold': 3},
    MODE_NIGHTFALL: {'title': 'nightfall', 'player_count': 3, 'threshold': 2},
    MODE_FORGE: {'title': 'forge', 'player_count': 3, 'threshold': 2},
    MODE_PVP_MAYHEM: {'title': 'mayhem', 'player_count': 6, 'threshold': 3},
    MODE_PVP_SUPREMACY: {'title': 'supremacy', 'player_count': 4, 'threshold': 2},
    MODE_PVP_SURVIVAL: {'title': 'survival', 'player_count': 4, 'threshold': 2},
    MODE_PVP_COUNTDOWN: {'title': 'countdown', 'player_count': 4, 'threshold': 2},
    MODE_PVP_IRONBANNER_CONTROL: {'title': 'ironbanner control', 'player_count': 6, 'threshold': 3},
    MODE_PVP_IRONBANNER_CLASH: {'title': 'ironbanner clash', 'player_count': 6, 'threshold': 3},
    MODE_PVP_DOUBLES: {'title': 'doubles', 'player_count': 2, 'threshold': 2},
    MODE_PVP_LOCKDOWN: {'title': 'lockdown', 'player_count': 4, 'threshold': 2},
    MODE_PVP_BREAKTHROUGH: {'title': 'breakthrough', 'player_count': 4, 'threshold': 2},
    MODE_PVP_CLASH_QUICK: {'title': 'clash (quickplay)', 'player_count': 6, 'threshold': 3},
    MODE_PVP_CLASH_COMP: {'title': 'clash (competitive)', 'player_count': 4, 'threshold': 2},
    MODE_PVP_CONTROL_QUICK: {'title': 'control (quickplay)', 'player_count': 6, 'threshold': 3},
    MODE_PVP_CONTROL_COMP: {'title': 'control (competitive)', 'player_count': 4, 'threshold': 2},
    MODE_GAMBIT: {'title': 'gambit', 'player_count': 4, 'threshold': 2},
    MODE_GAMBIT_PRIME: {'title': 'gambit prime', 'player_count': 4, 'threshold': 2},
    MODE_GAMBIT_RECKONING: {'title': 'reckoning',
                            'player_count': 4, 'threshold': 2}
}

SUPPORTED_GAME_MODES = {
    'gambit': MODES_GAMBIT,
    'strike': MODES_STRIKE,
    'raid': [MODE_RAID],
    'forge': [MODE_FORGE],
    'pvp': MODES_PVP_COMP + MODES_PVP_QUICK,
    'pvp-quick': MODES_PVP_QUICK,
    'pvp-comp': MODES_PVP_COMP
}

FORSAKEN_RELEASE = datetime.strptime(
    '2018-09-04T18:00:00Z', '%Y-%m-%dT%H:%M:%S%z')
