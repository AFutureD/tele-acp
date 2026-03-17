import contextlib
from typing import Any, Protocol, TypeAlias

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass


@dataclass
class ChatMessageFilePart:
    path: str = Field(description="The local path of the file")


@dataclass
class ChatMessageTextPart:
    text: str = Field(description="The text of the message")


ChatMessagePart: TypeAlias = ChatMessageFilePart | ChatMessageTextPart


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class ChatMessage:
    """The Message in Chat"""

    id: str | None = Field(description="The identifier of the message in the chat")

    channel_id: str = Field(description="Which channel this message was sent from")
    chat_id: str = Field(description="Which chat this message wants to be sent to")
    receiver: str | None = Field(description="Which user this message wants to be sent to")

    out: bool = Field(description="Is this an outgoing message")

    mute: bool = Field(description="Whether to mute notifications for this message")

    parts: list[ChatMessagePart] = Field(default_factory=list, description="The Message. Ordered.")

    lifespan: contextlib.AbstractAsyncContextManager | None = Field(default=None, exclude=True)

    meta: dict[str, Any] = Field(default_factory=dict, description="Metadata for the message")

    @staticmethod
    def Empty() -> ChatMessage:
        return ChatMessage(meta={}, id=None, channel_id="", chat_id="", receiver="", out=False, mute=False)


class Chatable(Protocol):
    async def receive_message(self, message: ChatMessage):
        """Handle messages sent either by a remote peer or by the same user from another session on this channel."""
        ...

    async def send_message(self, message: ChatMessage):
        """Send message to remote peer, or boardcast message to all sessions on this channel."""
        ...


class ChatMessageReplyable(Protocol):
    async def receive_message(self, chat: Chatable, message: ChatMessage) -> None: ...
