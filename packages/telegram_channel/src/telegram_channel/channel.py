import contextlib
import logging
from typing import AsyncIterator, Awaitable, Callable

import telethon
from tele_acp_core import (
    Channel,
    ChatMessage,
    ChatMessageFilePart,
    ChatMessagePart,
    ChatMessageTextPart,
    unreachable,
)
from telethon.tl.custom import Message as TeleMessage

from .client import TGClient
from .settings import TelegramUserChannel, TypeTelegramChannel


def peer_id_into_raw_int(peer_id: telethon.types.TypePeer) -> int:
    match peer_id:
        case telethon.types.PeerUser():
            return peer_id.user_id
        case telethon.types.PeerChat():
            return peer_id.chat_id
        case telethon.types.PeerChannel():
            return peer_id.channel_id
        case _:
            unreachable("peer_id_into_raw_int")


def peer_id_into_chat_id(peer_id: telethon.types.TypePeer) -> str:
    match peer_id:
        case telethon.types.PeerUser():
            return f"U{peer_id.user_id}"
        case telethon.types.PeerChat():
            return f"G{peer_id.chat_id}"
        case telethon.types.PeerChannel():
            return f"C{peer_id.channel_id}"
        case _:
            unreachable("peer_id_into_chat_id")


def chat_id_into_peer_id(chat_id: str) -> telethon.types.TypePeer | str:
    if chat_id == "":
        return chat_id

    type_str = chat_id[0].upper()
    id_str = chat_id.removeprefix(type_str)

    match type_str:
        case "U":
            return telethon.types.PeerUser(int(id_str))
        case "C":
            return telethon.types.PeerChat(int(id_str))
        case "G":
            return telethon.types.PeerChannel(int(id_str))
        case _:
            return chat_id


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

    def __init__(
        self, id: str, api_id: int | None, api_hash: str | None, settings: TypeTelegramChannel, message_handler: Callable[[ChatMessage], Awaitable[None]]
    ):
        tele_client = TGClient.create_as_login(api_id, api_hash, settings)
        tele_client.add_event_handler(self._on_receive_new_message_event, telethon.events.NewMessage())
        self.settings = settings
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
        files: list[telethon.hints.FileLike] = [part.path for part in message.parts if isinstance(part, ChatMessageFilePart)]
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

        if not await self.is_message_allowed(message):
            return

        peer_id = message.peer_id
        if not isinstance(peer_id, telethon.types.PeerUser):  # hard-coded peer filter used during development
            return

        chat_id: str = peer_id_into_chat_id(peer_id)
        chat_message = convert_telegram_message_to_chat_message(self.id, chat_id, message, lifespan=self.build_message_lifespan(peer_id, message.id))
        await self.receive_message(chat_message)

    @contextlib.asynccontextmanager
    async def build_message_lifespan(self, peer: telethon.types.TypePeer, message_id: int) -> AsyncIterator[None]:
        async with self._tele_client.with_action(peer, "typing"):
            # mark the massage `read`
            await self._tele_client.send_read_acknowledge(peer, max_id=message_id)

            yield

    async def is_message_allowed(self, message: TeleMessage) -> bool:
        """If Peer is allowed by the whitelist or contact list"""

        peer: telethon.types.TypePeer = message.peer_id
        sender: telethon.types.TypePeer | None = message.from_id  # None if it is an anonymous messages

        peer_raw_id = peer_id_into_raw_int(peer)
        chat_id = peer_id_into_chat_id(peer)

        sender_raw_id = peer_id_into_raw_int(sender) if sender else None
        sender_chat_id = peer_id_into_chat_id(sender) if sender else None

        def _is_allowed_by_white_list(settings: TypeTelegramChannel) -> bool:
            whitelist = settings.whitelist
            if whitelist is None:
                return False

            # check if chat_id in white list
            ret = any(item in {chat_id, str(peer_raw_id)} for item in whitelist)

            if isinstance(peer, telethon.types.PeerUser):
                return ret

            if sender_raw_id is None or sender_chat_id is None:
                return False  # Do Not Respond to anonymous messages

            ret &= any(item in {sender_raw_id, str(sender_chat_id)} for item in whitelist)
            return ret

        async def _is_allowed_by_contact(settings: TypeTelegramChannel) -> bool:
            if not isinstance(settings, TelegramUserChannel):
                return False

            if not settings.allow_contacts:
                return False

            if not isinstance(peer, telethon.types.PeerUser):
                return False

            contacts = await self._tele_client.get_contact_user_peer()
            match = any(contact.user_id == peer.user_id for contact in contacts)

            return match

        match_white_list: bool = _is_allowed_by_white_list(self.settings)
        match_contact_list = await _is_allowed_by_contact(self.settings)

        return match_white_list or match_contact_list
