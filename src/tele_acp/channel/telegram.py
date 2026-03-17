import contextlib
import logging
from typing import AsyncIterator, Awaitable, Callable

import telethon
from telethon import hints as TeleHints
from telethon.tl.custom import Message as TeleMessage

from tele_acp.types import (
    Channel,
    ChatMessage,
    ChatMessageFilePart,
    ChatMessagePart,
    ChatMessageTextPart,
    TypeTelegramChannel,
    chat_id_into_peer_id,
    peer_id_into_chat_id,
)

from .client import TGClient


def convert_telegram_message_to_chat_message(
    channel_id: str,
    chat_id: str,
    message: TeleMessage,
    lifespan: contextlib.AbstractAsyncContextManager | None = None,
) -> ChatMessage:
    message_id = str(message.id)

    text_part: str | None = message.message
    parts: list[ChatMessagePart] = [ChatMessageTextPart(text_part)] if text_part else []

    return ChatMessage(
        id=message_id, channel_id=channel_id, chat_id=chat_id, receiver=None, out=message.out, mute=message.silent or False, parts=parts, lifespan=lifespan
    )


class TelegramChannel(Channel):
    """
    屏蔽 telethon 对 APP 的细节
    """

    def __init__(self, id: str, settings: TypeTelegramChannel, message_handler: Callable[[ChatMessage], Awaitable[None]]):
        tele_client = TGClient.create_as_login(None, None, settings)
        tele_client.add_event_handler(self._on_receive_new_message_event, telethon.events.NewMessage())
        self._tele_client = tele_client
        self._message_handler = message_handler
        self._id = id
        self.logger = logging.getLogger(f"{self.__class__.__name__}:{self.id}")

    @property
    def id(self) -> str:
        return self._id

    @property
    async def status(self) -> bool:
        return await self._tele_client.is_user_authorized()

    @contextlib.asynccontextmanager
    async def run_until_finish(self) -> AsyncIterator[Channel]:
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._tele_client)
            yield self

    async def send_message(self, message: ChatMessage):
        files: list[TeleHints.FileLike] = [part.path for part in message.parts if isinstance(part, ChatMessageFilePart)]
        texts = [part.text for part in message.parts if isinstance(part, ChatMessageTextPart)]
        content = "\n".join(texts)

        receiver = message.receiver or message.chat_id
        peer_id = chat_id_into_peer_id(receiver)

        await self._tele_client.send_message(peer_id, message=content, file=files if len(files) > 0 else None)
        self.logger.info(f"send_message: {message}")

    async def receive_message(self, message: ChatMessage):
        await self._message_handler(message)

    async def _on_receive_new_message_event(self, event: telethon.events.NewMessage.Event):
        """Handle message from telethon client"""

        message: TeleMessage = event.message

        peer_id = message.peer_id
        chat_id: str = peer_id_into_chat_id(peer_id)
        if not isinstance(peer_id, telethon.types.PeerUser):
            return

        chat_message = convert_telegram_message_to_chat_message(self.id, chat_id, message, lifespan=self.build_message_lifespan(peer_id, message.id))
        await self.receive_message(chat_message)

    @contextlib.asynccontextmanager
    async def build_message_lifespan(self, peer: telethon.types.TypePeer, message_id: int) -> AsyncIterator[None]:
        async with self._tele_client.with_action(peer, "typing"):
            # Read the message
            await self._tele_client.send_read_acknowledge(peer, max_id=message_id)

            yield
