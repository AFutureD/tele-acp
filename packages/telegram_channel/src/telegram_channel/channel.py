import contextlib
import copy
import logging
from datetime import datetime
from typing import AsyncIterator, Awaitable, Callable, Self

import telethon
import telethon.hints
from susie_core import Channel, ChatInfo, ChatMessage, ChatMessageBlockQuote, ChatMessageFilePart, ChatMessagePart, ChatMessageTextPart, unreachable
from telethon.extensions import markdown as telegram_markdown
from telethon.tl.custom import Message as TeleMessage
from telethon.tl.custom.dialog import Dialog as TeleDialog
from telethon.types import MessageEntityBlockquote, TypeMessageEntity

from .client import TGClient
from .settings import TELEGRAM_PEER_ALL_INDICATOR, TelegramChannelGroupPolicy, TelegramChannelSettings


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
        case "G":
            return telethon.types.PeerChat(int(id_str))
        case "C":
            return telethon.types.PeerChannel(int(id_str))
        case _:
            return chat_id


def parse_entity_from_text(text: str | None, entity: telethon.types.TypeMessageEntity) -> str | None:
    if text is None or not hasattr(entity, "offset") or not hasattr(entity, "length"):
        return None

    entity_text = text.encode("utf-16-le")
    entity_text = entity_text[entity.offset * 2 : (entity.offset + entity.length) * 2]

    return entity_text.decode("utf-16-le")


def convert_telegram_message_to_chat_message(
    channel_id: str,
    message: TeleMessage,
    lifespan: contextlib.AbstractAsyncContextManager | None = None,
) -> ChatMessage:
    chat_id: str = peer_id_into_chat_id(message.peer_id)

    message_id = str(message.id)

    reply_to = message.reply_to
    text_part: str | None = message.message
    parts: list[ChatMessagePart] = [ChatMessageTextPart(text_part)] if text_part else []

    return ChatMessage(
        id=message_id,
        channel_id=channel_id,
        chat_id=chat_id,
        receiver=None,
        reply_to=str(reply_to),
        out=message.out,
        mute=message.silent or False,
        parts=parts,
        lifespan=lifespan,
    )


type MessageHandler = Callable[[ChatMessage], Awaitable[None]]


def render_telegram_rich_text_sections(sections: list[dict[str, str]]) -> tuple[str, list[TypeMessageEntity]]:
    text_parts: list[str] = []
    entities: list[TypeMessageEntity] = []
    offset = 0

    for section in sections:
        section_text = str(section.get("text", "")).strip()
        if section_text == "":
            continue

        if text_parts:
            text_parts.append("\n\n")
            offset += 2

        text_type = section.get("text_type", "plain")
        if text_type == "markdown":
            clean_text, section_entities = telegram_markdown.parse(section_text)
        else:
            clean_text, section_entities = section_text, []

        if clean_text == "":
            continue

        section_offset = offset
        text_parts.append(clean_text)

        for entity in section_entities:
            shifted = copy.copy(entity)
            shifted.offset += section_offset
            entities.append(shifted)

        if text_type == "expandable_blockquote":
            entities.append(MessageEntityBlockquote(offset=section_offset, length=len(clean_text), collapsed=True))

        offset += len(clean_text)

    entities.sort(key=lambda entity: (entity.offset, -entity.length))

    return "".join(text_parts), entities


class TelegramChannel(Channel):
    """
    屏蔽 telethon 对 APP 的细节
    """

    def __init__(
        self,
        id: str,
        api_id: int | None,
        api_hash: str | None,
        settings: TelegramChannelSettings,
        message_handler: MessageHandler,
    ):
        tele_client = TGClient.create_as_login(api_id, api_hash, settings)
        tele_client.add_event_handler(self._on_receive_new_message_event, telethon.events.NewMessage())
        self.settings = settings
        self._tele_client = tele_client
        self._message_handler = message_handler
        self._id = id
        self.logger = logging.getLogger(f"{self.__class__.__name__}:{self.id}")
        self._cached_me: telethon.types.User | None = None

    @property
    def id(self) -> str:
        return self._id

    @property
    async def status(self) -> bool:
        return await self._tele_client.is_user_authorized()

    def require_me(self) -> telethon.types.User:
        if me := self._cached_me:
            return me
        raise ValueError("Not Found")

    @contextlib.asynccontextmanager
    async def run_until_finish(self) -> AsyncIterator[Self]:
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._tele_client)
            self._cached_me = await self._tele_client.get_user()

            yield self

    async def send_message(self, message: ChatMessage):
        files: list[telethon.hints.FileLike] = [part.path for part in message.parts if isinstance(part, ChatMessageFilePart)]
        entities: list[TypeMessageEntity] = []

        msg = ""
        offset = 0
        for part in message.parts:
            match part:
                case ChatMessageTextPart():
                    mode = telethon.utils.sanitize_parse_mode("md")
                    text, parts = mode.parse(part.text)

                    msg += text
                    entities.extend(parts)
                    offset += len(text)

                case ChatMessageBlockQuote():
                    text = f"{part.title}\n{part.body}"

                    msg += text
                    entities.append(MessageEntityBlockquote(offset=offset, length=len(text), collapsed=True))
                    offset += len(text)

                case ChatMessageFilePart():
                    pass

            msg += "\n"
            offset += 2

        receiver = message.receiver or message.chat_id
        peer_id = chat_id_into_peer_id(receiver)

        await self._tele_client.send_message(
            peer_id,
            message=msg,
            formatting_entities=entities,
            file=files if len(files) > 0 else None,
        )
        self.logger.info(f"send_message: {message}")

    async def receive_message(self, message: ChatMessage):
        await self._message_handler(message)

    async def _on_receive_new_message_event(self, event: telethon.events.NewMessage.Event):
        """Handle message from telethon client"""

        message: TeleMessage = event.message
        self.logger.info(message)

        if not await self.is_message_allowed(message):
            return

        peer_id = message.peer_id

        chat_message = convert_telegram_message_to_chat_message(self.id, message, lifespan=self.build_message_lifespan(peer=peer_id, message_id=message.id))
        await self.receive_message(chat_message)

    @contextlib.asynccontextmanager
    async def build_message_lifespan(self, peer: telethon.types.TypePeer, message_id: int) -> AsyncIterator[None]:
        async with self._tele_client.with_action(peer, "typing"):
            # mark the massage `read`
            await self._tele_client.send_read_acknowledge(peer, max_id=message_id)

            yield

    async def is_message_allowed(self, message: TeleMessage) -> bool:
        """If Peer is allowed by the whitelist or contact list"""

        peer_id: telethon.types.TypePeer = message.peer_id
        chat_id = peer_id_into_chat_id(peer_id)
        raw_id = peer_id_into_raw_int(peer_id)

        match peer_id:
            case telethon.types.PeerUser():

                async def _is_admin(settings: TelegramChannelSettings, peer: telethon.types.PeerUser):
                    chat = message.chat
                    if not chat:
                        return False

                    admins = await self._tele_client.list_admin_user(chat)
                    return any(admin.id == peer.user_id for admin in admins)

                async def _is_allowed_by_contact(settings: TelegramChannelSettings, peer: telethon.types.PeerUser) -> bool:
                    if not isinstance(settings, TelegramChannelSettings):
                        return False

                    if not settings.allow_contacts:
                        return False

                    contacts = await self._tele_client.get_contact_user_peer()
                    match = any(contact.user_id == peer.user_id for contact in contacts)

                    return match

                def _is_allowed_by_white_list(settings: TelegramChannelSettings, peer: telethon.types.PeerUser) -> bool:
                    whitelist = settings.whitelist
                    if whitelist is None:
                        return False

                    ret = any(str(item) in {chat_id, str(peer.user_id)} for item in whitelist)
                    return ret

                match_contact_list = await _is_allowed_by_contact(self.settings, peer_id)
                match_whitelist = _is_allowed_by_white_list(self.settings, peer_id)
                match_admin = await _is_admin(self.settings, peer_id)

                return match_whitelist or match_contact_list or match_admin

            case telethon.types.PeerChannel() | telethon.types.PeerChat():
                """
                https://docs.telethon.dev/en/v2/concepts/peers.html

                Telegram uses Peers to categorize users, groups and channels, much like how Telethon does. It also has the concept of InputPeers, which are commonly used as input parameters when sending requests. These match the concept of Telethon’s peer references.

                The main confusion in Telegram’s API comes from the word “chat”.

                In the TL schema definitions, there are two boxed types, User and Chat. A boxed User can only be the bare user, but the boxed Chat can be either a bare chat or a bare channel.

                A bare chat always refers to small groups. A bare channel can have either the broadcast or the megagroup flag set to True.

                A bare channel with the broadcast flag set to True is known as a broadcast channel. A bare channel with the megagroup flag set to True is known as a supergroup.

                A bare chat has less features available than a bare channel megagroup. Official clients are very good at hiding this difference. They will implicitly convert bare chat to bare channel megagroup when doing certain operations. Doing things like setting a username is actually a two-step process (migration followed by updating the username). Official clients transparently merge the history of migrated channel with their old chat.

                In Telethon:
                - A User always corresponds to user.
                - A Group represents either a chat or a channel megagroup.
                - A Channel represents a channel broadcast.

                Telethon classes aim to map to similar concepts in official applications.
                """
                if isinstance(message.chat, telethon.types.Channel):
                    if message.chat.broadcast:
                        return False

                sender: telethon.types.TypePeer | None = message.from_id  # None if it is an anonymous messages
                if sender is None:
                    return False  # Do Not Respond to anonymous messages

                # We can not use message.mentioned
                me = self.require_me()

                def if_message_mentioned_me() -> bool:
                    if message.mentioned:
                        return True

                    def mentioned_by_username() -> bool:
                        username = me.username
                        if username is None:
                            return False

                        entities = message.entities or []
                        entities = [entity for entity in entities if isinstance(entity, telethon.types.MessageEntityMention)]

                        mentions = map(lambda x: parse_entity_from_text(message.message, x), entities)
                        return any(username in [mention, mention.removeprefix("@")] for mention in mentions if mention is not None)

                    def mentioned_by_userid() -> bool:
                        entities = [entity for entity in (message.entities or []) if isinstance(entity, telethon.types.MessageEntityMentionName)]
                        return any(me.id == entity.user_id for entity in entities)

                    return mentioned_by_username() or mentioned_by_userid()

                is_me = sender == telethon.types.PeerUser(user_id=me.id)
                if not (if_message_mentioned_me() or is_me):
                    return False  # In early stage, we are only support mentioned message.

                policy: TelegramChannelGroupPolicy | None = None
                policy = policy or self.settings.groups.get(str(raw_id))
                policy = policy or self.settings.groups.get(chat_id)
                policy = policy or self.settings.groups.get(TELEGRAM_PEER_ALL_INDICATOR)

                if policy is None:
                    return False

                sender_raw_id = peer_id_into_raw_int(sender)
                sender_chat_id = peer_id_into_chat_id(sender)

                ret = False
                ret = ret or any(str(item) in {sender_chat_id, str(sender_raw_id)} for item in policy.whitelist)
                ret = ret or (TELEGRAM_PEER_ALL_INDICATOR in policy.whitelist)
                return ret

        unreachable("")

    async def list_chats(self, with_archived: bool = False) -> list[ChatInfo]:
        archived = None if with_archived else False

        dialogs: list[TeleDialog] = await self._tele_client.get_cached_dialogs(archived=archived)

        ret: list[ChatInfo] = []

        for dialog in dialogs:
            peer = dialog.dialog.peer

            info = ChatInfo(channel_id=self.id, chat_id=peer_id_into_chat_id(peer), name=dialog.name)
            ret.append(info)

        return ret

    async def list_messages(self, chat_id: str, num: int = 1, date_start: datetime | None = None, date_end: datetime | None = None) -> list[ChatMessage]:
        peer_id = chat_id_into_peer_id(chat_id)
        messages = await self._tele_client.list_messages(peer_id, date_start=date_start, date_end=date_end, limit=num)

        return [convert_telegram_message_to_chat_message(channel_id=self.id, message=message) for message in messages]
