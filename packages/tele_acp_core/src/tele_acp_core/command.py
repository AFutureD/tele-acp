from typing import Any, Callable, Protocol, TypeAlias

from pydantic import BaseModel, Field

from .chat import ChatMessage, ChatReplyable

AnyFunction: TypeAlias = Callable[..., Any]


class Command(BaseModel):
    """
    The Command sent by the user to trigger some action in the agent.

    Example :
      - /help: Show the help message
      - /new: Create a new chat
      - /model gpt-5.4: Switch the model to gpt-5.4
    """

    fn: AnyFunction
    name: str = Field(description="The command name")
    description: str = Field(description="The command description")


class Context(BaseModel):
    message: ChatMessage = Field(description="The message that triggered the command")


class CommandProvider(Protocol):
    def list_commands(self) -> list[Command]: ...


class ChatCommandResponder(CommandProvider, ChatReplyable):
    ...
