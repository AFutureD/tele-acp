import asyncio
import contextlib
import logging
from datetime import datetime

from tele_acp_core import Channel, Chatable, ChatMessage, ChatMessageQueryable, ChatMessageReplyable

from tele_acp.config import ChatSettings

IGNORE_MESSAGE_DURATION_IN_SECONDS = 120.0


class Chat(Chatable, ChatMessageQueryable):
    def __init__(self, chat_id: str, channel: Channel, settings: ChatSettings, replier: ChatMessageReplyable):
        self.id = chat_id
        self.replier = replier
        self.channel = channel
        self.logger = logging.getLogger(__name__ + ":" + chat_id)
        self._ignore_until: float = asyncio.get_event_loop().time()
        self.settings = settings

    @property
    def ignore_message(self) -> bool:
        now = asyncio.get_running_loop().time()
        return now <= self._ignore_until

    async def receive_message(self, message: ChatMessage):
        if message.out:
            await self._handle_sent_message(message)
        else:
            await self._handle_new_message(message)

    async def send_message(self, message: ChatMessage):
        await self.channel.send_message(message)

    async def list_messages(self, num: int = 1, date_start: datetime | None = None, date_end: datetime | None = None) -> list[ChatMessage]:
        return await self.channel.list_messages(chat_id=self.id, num=num, date_start=date_start, date_end=date_end)

    async def _handle_sent_message(self, message: ChatMessage):
        _ = message
        now = asyncio.get_running_loop().time()
        self._ignore_until = now + IGNORE_MESSAGE_DURATION_IN_SECONDS

    async def _handle_new_message(self, message: ChatMessage):
        if self.ignore_message:
            return

        lifespan = message.lifespan or contextlib.nullcontext()

        async with lifespan:
            await self.replier.receive_message(self, message)
