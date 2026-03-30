import asyncio
import contextlib
import logging
from datetime import datetime

from tele_acp_core import Channel, Chatable, ChatAwareError, ChatMessage, ChatMessageQueryable, ChatMessageTextPart, ChatReplyable

from tele_acp.command import CommandChain
from tele_acp.config import ChatSettings

from .inspect import Inspector

IGNORE_MESSAGE_DURATION_IN_SECONDS = 120.0


class Chat(Chatable, ChatMessageQueryable):
    def __init__(self, chat_id: str, channel: Channel, settings: ChatSettings, replier: ChatReplyable, command_chain: CommandChain):
        self.id = chat_id
        self.replier = replier
        self.channel = channel
        self.logger = logging.getLogger(__name__ + ":" + chat_id)
        self._ignore_until: float = asyncio.get_event_loop().time()
        self.settings = settings
        self.command_chain = command_chain
        self.inspector = Inspector()


        for command in self.inspector.list_commands():
            self.command_chain.register(command)

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
        try:
            await self.channel.send_message(message)
        except Exception as e:
            self.logger.error(f"Error while sending message: {e}")

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
            try:
                _ = await self.replier.receive_message(self, message)
            except ChatAwareError as e:
                await self.send_message(
                    ChatMessage(
                        id=None,
                        channel_id=message.channel_id,
                        chat_id=message.chat_id,
                        receiver=None,
                        reply_to=None,
                        out=False,
                        mute=False,
                        parts=[ChatMessageTextPart(str(e))],
                    )
                )
                self.logger.error(f"Error while processing message: {e}")
