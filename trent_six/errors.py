from discord.ext.commands.errors import CommandError


class InvalidGameModeError(CommandError):
    def __init__(self, game_mode, supported_game_modes, *args):
        self.message = (
            f"Invalid game mode `{game_mode}`, supported are "
            f"`{', '.join(supported_game_modes)}`"
        )
        super().__init__(self.message, *args)


class InvalidMemberError(CommandError):
    def __init__(self, *args):
        self.message = "You don't seem to be a clan member"
        super().__init__(self.message, *args)


class NotRegisteredError(CommandError):
    def __init__(self, prefix, *args):
        self.message = (
            f"You don't seem to be registered, "
            f"try running `{prefix}register`"
        )
        super().__init__(self.message, *args)


class ConfigurationError(CommandError):
    def __init__(self, message, *args):
        self.message = message
        super().__init__(message, *args)


class InvalidCommandError(CommandError):
    def __init__(self, message, *args):
        self.message = message
        super().__init__(message, *args)
