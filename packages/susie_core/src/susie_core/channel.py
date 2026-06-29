import contextlib
from abc import abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Protocol, Self, TypeAlias

from pydantic import BaseModel

from .chat import ChatInfo, ChatMessage

ChannelPeer: TypeAlias = Any

ChannelType: TypeAlias = str


class ChannelSettings(BaseModel):
    type: ChannelType


class Channel(Protocol):
    @property
    def id(self) -> str:
        """Channel ID"""
        ...

    @property
    def message_syntax(self) -> str | None: ...

    @contextlib.asynccontextmanager
    async def run_until_finish(self) -> AsyncIterator[Self]:
        yield self

    @abstractmethod
    async def send_message(self, message: ChatMessage):
        """Channel Outbound"""
        ...

    @abstractmethod
    async def receive_message(self, message: ChatMessage):
        """Channel Inbound"""
        ...

    @property
    async def status(self) -> bool:
        """Channel Status"""
        ...

    @abstractmethod
    async def list_chats(self, with_archived: bool = False) -> list[ChatInfo]: ...

    @abstractmethod
    async def list_messages(self, chat_id: str, num: int = 1, date_start: datetime | None = None, date_end: datetime | None = None) -> list[ChatMessage]: ...
