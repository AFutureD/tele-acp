import contextlib
from datetime import datetime
from typing import Any, Protocol, Self

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass
from pydantic.json_schema import SkipJsonSchema


@dataclass
class ChatMessageFilePart:
    path: str = Field(description="The local path of the file")


@dataclass
class ChatMessageTextPart:
    text: str = Field(description="The text of the message")


type ChatMessagePart = ChatMessageFilePart | ChatMessageTextPart


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class ChatMessage:
    """The Message in Chat"""

    id: str | None = Field(description="The identifier of the message in the chat")

    channel_id: str = Field(description="Which channel this message was sent from")
    chat_id: str = Field(description="Which chat this message wants to be sent to")
    receiver: str | None = Field(description="Which user this message wants to be sent to")
    reply_to: str | None = Field(description="Which message this message is replying to. The value is the id of the message in the chat.")

    out: bool = Field(description="Is this an outgoing message")

    mute: bool = Field(description="Whether to mute notifications for this message")

    parts: list[ChatMessagePart] = Field(default_factory=list, description="The Message. Ordered.")

    lifespan: SkipJsonSchema[contextlib.AbstractAsyncContextManager | None] = Field(default=None, exclude=True)

    meta: dict[str, Any] = Field(default_factory=dict, description="Metadata for the message")

    @classmethod
    def Empty(cls) -> Self:
        return cls(meta={}, id=None, channel_id="", chat_id="", receiver=None, reply_to=None, out=False, mute=False)

    @classmethod
    def create_simple_text_message(
        cls, channel_id: str, chat_id: str, text: str, receiver: str | None = None, reply_to: str | None = None, out: bool = False, mute: bool = False
    ) -> Self:
        return cls(parts=[ChatMessageTextPart(text)], id=None, channel_id=channel_id, chat_id=chat_id, receiver=receiver, reply_to=reply_to, out=out, mute=mute)


@dataclass
class ChatInfo:
    channel_id: str = Field(description="The channel ID")
    chat_id: str = Field(description="The chat ID")
    name: str | None = Field(default=None, description="The chat name")


class Chatable(Protocol):
    async def receive_message(self, message: ChatMessage):
        """Handle messages sent either by a remote peer or by the same user from another session on this channel."""
        ...

    async def send_message(self, message: ChatMessage):
        """Send message to remote peer, or boardcast message to all sessions on this channel."""
        ...


class ChatMessageQueryable(Protocol):
    async def list_messages(self, num: int = 1, date_start: datetime | None = None, date_end: datetime | None = None) -> list[ChatMessage]:
        """
        List recent messages in this chat.

        Args:
            num: The number of messages to list. default to 1, which means to list the latest message.
            date_start: The start datetime to list messages. default to None, which means no limit on the start datetime.
            date_end: The end datetime to list messages. default to None, which means no limit on the end datetime.

        Returns:
            A list of messages, ordered from old to new.
        """
        ...


class ChatReplyable(Protocol):
    async def cancel(self):
        """
        cancel current message turn if exists
        """
        ...

    async def receive_message(self, chat: Chatable, message: ChatMessage):
        """
        Handle messages sent by remote peer, and reply to the chat if needed.
        Args:
            chat: The chat where the message is sent to.
            message: The message sent by remote peer.
        Returns:
            Whether the message is handled.
        """
        ...
