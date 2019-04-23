from discord.ext.commands.errors import CommandError


class InvalidGameModeError(CommandError):
    def __init__(self, game_mode, supported_game_modes, *args):
        self.message = f"Invalid game mode `{game_mode}`, supported are `{', '.join(supported_game_modes)}`"
        super().__init__(self.message, *args)


class InvalidFileIO(Exception):
    pass
