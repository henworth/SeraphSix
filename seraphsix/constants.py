import discord
import pytz

from datetime import datetime

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT_TZ = f"{DATE_FORMAT} %Z"
TIME_HOUR_SECONDS = 3600
TIME_MIN_SECONDS = 60
ROOT_LOG_LEVEL = "INFO"

LOG_FORMAT_MSG = "%(asctime)s %(name)s[%(process)d]: %(levelname)s %(message)s"
DB_MAX_CONNECTIONS = 20

ARQ_MAX_JOBS = 100
ARQ_JOB_TIMEOUT = TIME_HOUR_SECONDS

BLUE = discord.Color(3381759)
CLEANUP_DELAY = 4

EMOJI_PC = 586933311994200074
EMOJI_PSN = 590019204623761438
EMOJI_XBOX = 590004787370786817
EMOJI_STEAM = 644904784088006656
EMOJI_STADIA = 644904919111041035

EMOJI_LETTER_A = "\U0001F1E6"
EMOJI_LETTER_B = "\U0001F1E7"
EMOJI_LETTER_C = "\U0001F1E8"
EMOJI_LETTER_D = "\U0001F1E9"
EMOJI_LETTER_E = "\U0001F1EA"
EMOJI_LETTER_F = "\U0001F1EB"
EMOJI_LETTER_G = "\U0001F1EC"
EMOJI_LETTER_H = "\U0001F1ED"
EMOJI_LETTER_I = "\U0001F1EE"
EMOJI_LETTER_J = "\U0001F1EF"
EMOJI_LETTER_K = "\U0001F1F0"
EMOJI_LETTER_L = "\U0001F1F1"
EMOJI_LETTER_M = "\U0001F1F2"
EMOJI_LETTER_N = "\U0001F1F3"
EMOJI_LETTER_O = "\U0001F1F4"
EMOJI_LETTER_P = "\U0001F1F5"
EMOJI_LETTER_Q = "\U0001F1F6"
EMOJI_LETTER_R = "\U0001F1F7"
EMOJI_LETTER_S = "\U0001F1F8"
EMOJI_LETTER_T = "\U0001F1F9"
EMOJI_LETTER_U = "\U0001F1FA"
EMOJI_LETTER_V = "\U0001F1FB"
EMOJI_LETTER_W = "\U0001F1FC"
EMOJI_LETTER_X = "\U0001F1FD"
EMOJI_LETTER_Y = "\U0001F1FE"
EMOJI_LETTER_Z = "\U0001F1FF"

EMOJI_LETTERS = [
    EMOJI_LETTER_A,
    EMOJI_LETTER_B,
    EMOJI_LETTER_C,
    EMOJI_LETTER_D,
    EMOJI_LETTER_E,
    EMOJI_LETTER_F,
    EMOJI_LETTER_G,
    EMOJI_LETTER_H,
    EMOJI_LETTER_I,
    EMOJI_LETTER_J,
    EMOJI_LETTER_K,
    EMOJI_LETTER_L,
    EMOJI_LETTER_M,
    EMOJI_LETTER_N,
    EMOJI_LETTER_O,
    EMOJI_LETTER_P,
    EMOJI_LETTER_Q,
    EMOJI_LETTER_R,
    EMOJI_LETTER_S,
    EMOJI_LETTER_T,
    EMOJI_LETTER_U,
    EMOJI_LETTER_V,
    EMOJI_LETTER_W,
    EMOJI_LETTER_X,
    EMOJI_LETTER_Y,
    EMOJI_LETTER_Z,
]

EMOJI_STOP = "\N{BLACK SQUARE FOR STOP}"
EMOJI_CHECKMARK = "\u2705"
EMOJI_CROSSMARK = "\u274C"

PLATFORM_XBOX = 1
PLATFORM_PSN = 2
PLATFORM_STEAM = 3
PLATFORM_BLIZZARD = 4
PLATFORM_STADIA = 5
PLATFORM_BUNGIE = 254

PLATFORMS = [
    PLATFORM_XBOX,
    PLATFORM_PSN,
    PLATFORM_BLIZZARD,
    PLATFORM_STEAM,
    PLATFORM_STADIA,
]

PLATFORM_MAP = {
    "xbox": PLATFORM_XBOX,
    "psn": PLATFORM_PSN,
    "blizzard": PLATFORM_BLIZZARD,
    "steam": PLATFORM_STEAM,
    "stadia": PLATFORM_STADIA,
    "bungie": PLATFORM_BUNGIE,
}

PLATFORM_EMOJI_MAP = {
    "psn": EMOJI_PSN,
    "xbox": EMOJI_XBOX,
    "steam": EMOJI_STEAM,
    "stadia": EMOJI_STADIA,
}

PLATFORM_EMOJI_ID = {
    EMOJI_PSN: PLATFORM_PSN,
    EMOJI_XBOX: PLATFORM_XBOX,
    EMOJI_STEAM: PLATFORM_STEAM,
    EMOJI_STADIA: PLATFORM_STADIA,
}

CLAN_MEMBER_NONE = 0
CLAN_MEMBER_BEGINNER = 1
CLAN_MEMBER_MEMBER = 2
CLAN_MEMBER_ADMIN = 3
CLAN_MEMBER_ACTING_FOUNDER = 4
CLAN_MEMBER_FOUNDER = 5

CLAN_MEMBER_RANKS = [
    CLAN_MEMBER_NONE,
    CLAN_MEMBER_BEGINNER,
    CLAN_MEMBER_MEMBER,
    CLAN_MEMBER_ADMIN,
    CLAN_MEMBER_ACTING_FOUNDER,
    CLAN_MEMBER_FOUNDER,
]

# https://bungie-net.github.io/#/components/schemas/Destiny.DestinyComponentType
COMPONENT_PROFILES = 100
COMPONENT_CHARACTERS = 200

MODE_NONE = 0
MODE_STORY = 2
MODE_STRIKE = 3
MODE_RAID = 4
MODE_ALLPVP = 5
MODE_PATROL = 6
MODE_ALLPVE = 7
MODE_RESERVED9 = 9
MODE_CONTROL = 10
MODE_RESERVED11 = 11
MODE_CLASH = 12
MODE_RESERVED13 = 13
MODE_CRIMSONDOUBLES = 15
MODE_NIGHTFALL = 16
MODE_HEROICNIGHTFALL = 17
MODE_ALLSTRIKES = 18
MODE_IRONBANNER = 19
MODE_RESERVED20 = 20
MODE_RESERVED21 = 21
MODE_RESERVED22 = 22
MODE_RESERVED24 = 24
MODE_ALLMAYHEM = 25
MODE_RESERVED26 = 26
MODE_RESERVED27 = 27
MODE_RESERVED28 = 28
MODE_RESERVED29 = 29
MODE_RESERVED30 = 30
MODE_SUPREMACY = 31
MODE_PRIVATEMATCHESALL = 32
MODE_SURVIVAL = 37
MODE_COUNTDOWN = 38
MODE_TRIALSOFTHENINE = 39
MODE_SOCIAL = 40
MODE_TRIALSCOUNTDOWN = 41
MODE_TRIALSSURVIVAL = 42
MODE_IRONBANNERCONTROL = 43
MODE_IRONBANNERCLASH = 44
MODE_IRONBANNERSUPREMACY = 45
MODE_SCOREDNIGHTFALL = 46
MODE_SCOREDHEROICNIGHTFALL = 47
MODE_RUMBLE = 48
MODE_ALLDOUBLES = 49
MODE_DOUBLES = 50
MODE_PRIVATEMATCHESCLASH = 51
MODE_PRIVATEMATCHESCONTROL = 52
MODE_PRIVATEMATCHESSUPREMACY = 53
MODE_PRIVATEMATCHESCOUNTDOWN = 54
MODE_PRIVATEMATCHESSURVIVAL = 55
MODE_PRIVATEMATCHESMAYHEM = 56
MODE_PRIVATEMATCHESRUMBLE = 57
MODE_HEROICADVENTURE = 58
MODE_SHOWDOWN = 59
MODE_LOCKDOWN = 60
MODE_SCORCHED = 61
MODE_SCORCHEDTEAM = 62
MODE_GAMBIT = 63
MODE_ALLPVECOMPETITIVE = 64
MODE_BREAKTHROUGH = 65
MODE_BLACKARMORYRUN = 66
MODE_SALVAGE = 67
MODE_IRONBANNERSALVAGE = 68
MODE_PVPCOMPETITIVE = 69
MODE_PVPQUICKPLAY = 70
MODE_CLASHQUICKPLAY = 71
MODE_CLASHCOMPETITIVE = 72
MODE_CONTROLQUICKPLAY = 73
MODE_CONTROLCOMPETITIVE = 74
MODE_GAMBITPRIME = 75
MODE_RECKONING = 76
MODE_MENAGERIE = 77
MODE_VEXOFFENSIVE = 78
MODE_NIGHTMAREHUNT = 79
MODE_ELIMINATION = 80
MODE_MOMENTUM = 81
MODE_DUNGEON = 82
MODE_THESUNDIAL = 83
MODE_TRIALSOFOSIRIS = 84

MODES_PVP = [
    MODE_ALLMAYHEM,
    MODE_SUPREMACY,
    MODE_DOUBLES,
    MODE_LOCKDOWN,
    MODE_BREAKTHROUGH,
    MODE_SHOWDOWN,
    MODE_IRONBANNERCONTROL,
    MODE_IRONBANNERCLASH,
    MODE_CLASHQUICKPLAY,
    MODE_CONTROLQUICKPLAY,
    MODE_MOMENTUM,
    MODE_ELIMINATION,
    MODE_SURVIVAL,
    MODE_COUNTDOWN,
    MODE_CLASHCOMPETITIVE,
    MODE_CONTROLCOMPETITIVE,
    MODE_TRIALSOFOSIRIS,
    MODE_TRIALSCOUNTDOWN,
    MODE_TRIALSSURVIVAL,
    MODE_CRIMSONDOUBLES,
    MODE_SCORCHEDTEAM,
]

MODES_GAMBIT = [MODE_GAMBIT, MODE_GAMBITPRIME]

MODES_STRIKE = [MODE_STRIKE, MODE_SCOREDNIGHTFALL]

MODES_PVE = [
    MODE_STRIKE,
    MODE_NIGHTFALL,
    MODE_MENAGERIE,
    MODE_SCOREDNIGHTFALL,
    MODE_VEXOFFENSIVE,
    MODE_BLACKARMORYRUN,
    MODE_NIGHTMAREHUNT,
    MODE_RAID,
    MODE_HEROICADVENTURE,
    MODE_THESUNDIAL,
    MODE_PATROL,
    MODE_STORY,
    MODE_DUNGEON,
    MODE_RECKONING,
    MODE_SCOREDHEROICNIGHTFALL,
    MODE_HEROICNIGHTFALL,
]

MODE_MAP = {
    MODE_STORY: {"title": "story", "player_count": 3, "threshold": 2},
    MODE_STRIKE: {"title": "strike", "player_count": 3, "threshold": 2},
    MODE_RAID: {"title": "raid", "player_count": 6, "threshold": 3},
    MODE_PATROL: {"title": "patrol", "player_count": 3, "threshold": 2},
    MODE_NIGHTFALL: {"title": "nightfall", "player_count": 3, "threshold": 2},
    MODE_HEROICNIGHTFALL: {"title": "nightfall", "player_count": 3, "threshold": 2},
    MODE_SCOREDNIGHTFALL: {"title": "nightfall", "player_count": 3, "threshold": 2},
    MODE_SCOREDHEROICNIGHTFALL: {
        "title": "nightfall",
        "player_count": 3,
        "threshold": 2,
    },
    MODE_BLACKARMORYRUN: {"title": "forge", "player_count": 3, "threshold": 2},
    MODE_ALLMAYHEM: {"title": "mayhem", "player_count": 6, "threshold": 3},
    MODE_SUPREMACY: {"title": "supremacy", "player_count": 4, "threshold": 2},
    MODE_SURVIVAL: {"title": "survival", "player_count": 3, "threshold": 2},
    MODE_COUNTDOWN: {"title": "countdown", "player_count": 4, "threshold": 2},
    MODE_IRONBANNERCONTROL: {
        "title": "ironbanner (control)",
        "player_count": 6,
        "threshold": 3,
    },
    MODE_IRONBANNERCLASH: {
        "title": "ironbanner (clash)",
        "player_count": 6,
        "threshold": 3,
    },
    MODE_DOUBLES: {"title": "doubles", "player_count": 2, "threshold": 2},
    MODE_CRIMSONDOUBLES: {
        "title": "crimson doubles",
        "player_count": 2,
        "threshold": 2,
    },
    MODE_LOCKDOWN: {"title": "lockdown", "player_count": 4, "threshold": 2},
    MODE_SHOWDOWN: {"title": "showdown", "player_count": 4, "threshold": 2},
    MODE_BREAKTHROUGH: {"title": "breakthrough", "player_count": 4, "threshold": 2},
    MODE_CLASHQUICKPLAY: {
        "title": "clash (quickplay)",
        "player_count": 6,
        "threshold": 3,
    },
    MODE_CLASHCOMPETITIVE: {
        "title": "clash (competitive)",
        "player_count": 4,
        "threshold": 2,
    },
    MODE_CONTROLQUICKPLAY: {
        "title": "control (quickplay)",
        "player_count": 6,
        "threshold": 3,
    },
    MODE_CONTROLCOMPETITIVE: {
        "title": "control (competitive)",
        "player_count": 4,
        "threshold": 2,
    },
    MODE_GAMBIT: {"title": "gambit", "player_count": 4, "threshold": 2},
    MODE_GAMBITPRIME: {"title": "gambit prime", "player_count": 4, "threshold": 2},
    MODE_RECKONING: {"title": "reckoning", "player_count": 4, "threshold": 2},
    MODE_MENAGERIE: {"title": "menagerie", "player_count": 6, "threshold": 3},
    MODE_VEXOFFENSIVE: {"title": "menagerie", "player_count": 6, "threshold": 3},
    MODE_NIGHTMAREHUNT: {"title": "nightmare hunt", "player_count": 3, "threshold": 2},
    MODE_HEROICADVENTURE: {
        "title": "heroic adventure",
        "player_count": 3,
        "threshold": 2,
    },
    MODE_ELIMINATION: {"title": "elimination", "player_count": 3, "threshold": 2},
    MODE_MOMENTUM: {"title": "momentum control", "player_count": 6, "threshold": 3},
    MODE_THESUNDIAL: {"title": "the sundial", "player_count": 6, "threshold": 3},
    MODE_TRIALSOFOSIRIS: {
        "title": "trials of osiris",
        "player_count": 3,
        "threshold": 2,
    },
    MODE_TRIALSCOUNTDOWN: {
        "title": "trials of the nine",
        "player_count": 3,
        "threshold": 2,
    },
    MODE_TRIALSSURVIVAL: {
        "title": "trials of the nine",
        "player_count": 3,
        "threshold": 2,
    },
    MODE_SCORCHEDTEAM: {"title": "team scorched", "player_count": 6, "threshold": 3},
    MODE_DUNGEON: {"title": "dungeon", "player_count": 3, "threshold": 2},
}

SUPPORTED_GAME_MODES = {
    "gambit": MODES_GAMBIT,
    "pve": MODES_PVE,
    "pvp": MODES_PVP,
    "raid": [MODE_RAID],
    "all": MODES_PVP + MODES_GAMBIT + MODES_PVE,
}

DESTINY_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
DESTINY_DATE_FORMAT_MS = "%Y-%m-%dT%H:%M:%S.%f%z"
DESTINY_DATE_FORMAT_API = "%Y-%m-%dT%H:%M:%SZ"
FORSAKEN_RELEASE = datetime.strptime(
    "2018-09-04T18:00:00Z", DESTINY_DATE_FORMAT
).astimezone(tz=pytz.utc)
SHADOWKEEP_RELEASE = datetime.strptime(
    "2019-10-01T18:00:00Z", DESTINY_DATE_FORMAT
).astimezone(tz=pytz.utc)
BEYOND_LIGHT_RELEASE = datetime.strptime(
    "2020-11-10T18:00:00Z", DESTINY_DATE_FORMAT
).astimezone(tz=pytz.utc)

TWITTER_DESTINY_REDDIT = 2608131020
TWITTER_XBOX_SUPPORT = 59804598

TWITTER_FOLLOW_USERS = [TWITTER_DESTINY_REDDIT, TWITTER_XBOX_SUPPORT]

THE100_GAME_SORT_RULES = {
    "Destiny 2": {
        "fresh": [
            "Raid - Garden of Salvation" "Raid - Crown of Sorrow",
            "Raid - Leviathan - Prestige",
            "Raid - Scourge of the Past",
            "Raid - Leviathan - Normal",
            "Raid - Last Wish",
        ],
        "normal": [
            "Blind Well",
            "Escalation Protocol",
            "Quest - Outbreak Perfected",
            "Strike - Nightfall",
        ],
        "anything": ["Quest"],
    }
}

THE100_DATE_DISPLAY = "%m-%d %a %I:%M %p %Z"
THE100_DATE_CREATE = "%m/%d %I:%M%p"
THE100_LOGO_URL = (
    "https://www.the100.io/assets/the-100-logo-"
    "01d3884b844d4308fcf20f19281cc758f7b9803e2fba6baa6dc915ab8b385ba7.png"
)
