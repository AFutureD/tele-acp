from tele_acp_core.command import Command, CommandExecutable


class CommandExecutor(CommandExecutable):
    def __init__(self, command: Command):
        self.command = command

    async def execute_command(self, command: Command, args: dict[str, any] | None):
        pass
