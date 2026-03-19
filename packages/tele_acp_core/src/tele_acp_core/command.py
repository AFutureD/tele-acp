from typing import Protocol

from pydantic import BaseModel, Field


class Command(BaseModel):
    """
    The Command sent by the user to trigger some action in the agent.

    Example :
      - /help: Show the help message
      - /new: Create a new chat
      - /model gpt-5.4: Switch the model to gpt-5.4
    """

    command: str = Field(description="The command name")
    description: str = Field(description="The command description")

    # TODO: generate function's signature and args schema
    structured_args_schema: dict[str, any] | None = None


class CommandExecutable(Protocol):
    async def execute_command(self, command: Command, args: dict[str, any] | None):
        """Perform the command with the given arguments."""
        ...
