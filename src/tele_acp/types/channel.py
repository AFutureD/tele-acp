import contextlib
from abc import abstractmethod
from typing import Any, AsyncIterator, Protocol, TypeAlias

from .chat import ChatMessage

ChannelPeer: TypeAlias = Any


class Channel(Protocol):
    @property
    def id(self) -> str:
        """Channel ID"""
        ...

    @contextlib.asynccontextmanager
    async def run_until_finish(self) -> AsyncIterator[Channel]:
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
