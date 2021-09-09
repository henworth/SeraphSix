from discord.ext.commands.errors import CommandError


class InvalidGameModeError(CommandError):
    def __init__(self, game_mode, supported_game_modes, *args):
        message = f"Invalid game mode `{game_mode}`, supported are `{', '.join(supported_game_modes)}`."
        super().__init__(message, *args)


class InvalidMemberError(CommandError):
    def __init__(self, *args):
        message = "You don't seem to be a clan member."
        super().__init__(message, *args)


class InvalidAdminError(CommandError):
    def __init__(self, *args):
        message = "You don't seem to be an admin of any clan connected to this server, or you have not registered."
        super().__init__(message, *args)


class NotRegisteredError(CommandError):
    def __init__(self, prefix, *args):
        message = f"You don't seem to be registered, try running `{prefix}register`."
        super().__init__(message, *args)


class MissingTimezoneError(CommandError):
    def __init__(self, *args):
        message = "You don't have a timezone set"
        super().__init__(message, *args)


class ConfigurationError(CommandError):
    def __init__(self, message, *args):
        super().__init__(message, *args)


class InvalidCommandError(CommandError):
    def __init__(self, message, *args):
        super().__init__(message, *args)


class MaintenanceError(CommandError):
    def __init__(self, *args):
        message = "Destiny systems are currently undergoing maintenance, please try again later"
        super().__init__(message, *args)


class PrivateHistoryError(Exception):
    pass
