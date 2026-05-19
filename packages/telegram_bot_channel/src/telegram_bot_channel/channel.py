from __future__ import annotations

import contextlib
import html
import logging
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Self

import telegram.constants
from susie_core import Channel, ChatInfo, ChatMessage, ChatMessageBlockQuote, ChatMessageFilePart, ChatMessagePart, ChatMessageTextPart
from telegram import Message, MessageEntity, Update, User
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters

from .settings import TELEGRAM_BOT_CHAT_ALL_INDICATOR, TelegramBotChannelGroupPolicy, TelegramBotChannelSettings

type MessageHandlerFn = Callable[[ChatMessage], Awaitable[None]]


def _render_message_as_html(message: ChatMessage) -> str:
    msg = ""
    for part in message.parts:
        match part:
            case ChatMessageTextPart():
                msg += html.escape(part.text)

            case ChatMessageBlockQuote():
                # https://core.telegram.org/bots/api#html-style
                title = html.escape(part.title)
                body = html.escape(part.body)
                msg += f"<blockquote expandable>{title}\n{body}</blockquote>"
                msg += "\n"

            case ChatMessageFilePart():
                pass

    return msg


def _render_message_as_plain_text(message: ChatMessage) -> str:
    msg = ""
    for part in message.parts:
        match part:
            case ChatMessageTextPart():
                msg += part.text

            case ChatMessageBlockQuote():
                msg += f"{part.title}\n{part.body}"
                msg += "\n"

            case ChatMessageFilePart():
                pass

    return msg


def create_chat_id(type: str, chat_id: str | int, thread_id: int | None) -> str:
    if thread_id is None:
        match type:
            case telegram.Chat.PRIVATE:
                return f"P:{chat_id}"
            case telegram.Chat.GROUP:
                return f"G:{chat_id}"
            case telegram.Chat.CHANNEL:
                return f"C:{chat_id}"
            case telegram.Chat.SUPERGROUP:
                return f"S:{chat_id}"
            case telegram.Chat.SENDER:
                return f"X:{chat_id}"
            case _:
                return ""
    else:
        match type:
            case telegram.Chat.PRIVATE:
                return f"P:{chat_id}:{thread_id}"
            case telegram.Chat.GROUP:
                return f"G:{chat_id}:{thread_id}"
            case telegram.Chat.CHANNEL:
                return f"C:{chat_id}:{thread_id}"
            case telegram.Chat.SUPERGROUP:
                return f"S:{chat_id}:{thread_id}"
            case telegram.Chat.SENDER:
                return f"X:{chat_id}:{thread_id}"
            case _:
                return ""


def split_from_chat_id(chat_id: str) -> tuple[str, int, int | None] | None:
    parts = chat_id.split(sep=":")

    if len(parts) == 3:
        match parts[0].upper():
            case "P":
                return telegram.Chat.PRIVATE, int(parts[1]), int(parts[2])
            case "G":
                return telegram.Chat.GROUP, int(parts[1]), int(parts[2])
            case "C":
                return telegram.Chat.CHANNEL, int(parts[1]), int(parts[2])
            case "S":
                return telegram.Chat.SUPERGROUP, int(parts[1]), int(parts[2])
            case "X":
                return telegram.Chat.SENDER, int(parts[1]), int(parts[2])
            case _:
                return None

    if len(parts) == 2:
        match parts[0].upper():
            case "P":
                return telegram.Chat.PRIVATE, int(parts[1]), None
            case "G":
                return telegram.Chat.GROUP, int(parts[1]), None
            case "C":
                return telegram.Chat.CHANNEL, int(parts[1]), None
            case "S":
                return telegram.Chat.SUPERGROUP, int(parts[1]), None
            case "X":
                return telegram.Chat.SENDER, int(parts[1]), None
            case _:
                return None

    return None


def _message_text(message: Message) -> str | None:
    return message.text or message.caption


def _chat_title(message: Message) -> str | None:
    chat = message.chat
    return chat.title or chat.full_name or chat.username


def convert_telegram_bot_message_to_chat_message(
    channel_id: str, message: Message, lifespan: contextlib.AbstractAsyncContextManager | None = None
) -> ChatMessage:
    text = _message_text(message)
    parts: list[ChatMessagePart] = [ChatMessageTextPart(text)] if text else []

    chat_id = create_chat_id(message.chat.type, message.chat.id, message.message_thread_id)

    return ChatMessage(
        id=str(message.message_id),
        channel_id=channel_id,
        chat_id=chat_id,
        receiver=None,
        reply_to=str(message.reply_to_message.message_id) if message.reply_to_message else None,
        out=bool(message.from_user and message.from_user.is_bot),
        mute=False,
        parts=parts,
        lifespan=lifespan,
        meta={
            "telegram_bot_chat_type": message.chat.type,
            "telegram_bot_from_user_id": str(message.from_user.id) if message.from_user else None,
        },
    )


class TelegramBotChannel(Channel):
    def __init__(
        self,
        id: str,
        settings: TelegramBotChannelSettings,
        message_handler: MessageHandlerFn,
    ) -> None:
        self.settings = settings
        self._id = id
        self._message_handler = message_handler
        self._application: Application = ApplicationBuilder().token(settings.token).build()
        self._application.add_handler(MessageHandler(filters.ALL, self._on_receive_update))
        self._cached_me_id: int | None = None
        self._cached_me_username: str | None = None
        self._chat_infos: dict[str, ChatInfo] = {}
        self._messages: defaultdict[str, deque[ChatMessage]] = defaultdict(lambda: deque(maxlen=100))
        self.logger = logging.getLogger(f"{self.__class__.__name__}:{self.id}")

        self._cached_me: User | None = None

    async def __aenter__(self) -> "TelegramBotChannel":
        await self._application.initialize()

        me = await self._application.bot.get_me()
        self._cached_me_id = me.id
        self._cached_me_username = me.username

        if self._application.updater is None:
            raise RuntimeError("Telegram bot updater is not available")

        await self._application.updater.start_polling(drop_pending_updates=self.settings.drop_pending_updates)
        await self._application.start()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._application.updater is not None and self._application.updater.running:
            await self._application.updater.stop()
        if self._application.running:
            await self._application.stop()
        await self._application.shutdown()

    @contextlib.asynccontextmanager
    async def run_until_finish(self) -> AsyncIterator[Self]:
        await self.__aenter__()
        try:
            yield self
        finally:
            await self.__aexit__(None, None, None)

    @property
    def id(self) -> str:
        return self._id

    @property
    async def status(self) -> bool:
        try:
            _ = await self.get_me()
        except Exception:
            self.logger.exception("Failed to get Telegram bot status")
            return False

        return True

    async def get_me(self) -> User:
        try:
            # if self._application.running else self._application.bot.bot
            me = await self._application.bot.get_me()
            return me
        finally:
            if not self._application.running:
                await self._application.shutdown()

    async def send_message(self, message: ChatMessage) -> None:
        files = [part.path for part in message.parts if isinstance(part, ChatMessageFilePart)]
        parts = split_from_chat_id(chat_id=message.chat_id)
        if parts is None:
            return

        _, raw_chat_id, raw_thread_id = parts

        parts = split_from_chat_id(chat_id=message.receiver) if message.receiver else None
        if parts:
            _, raw_chat_id, raw_thread_id = parts

        del parts

        reply_to_message_id = int(message.reply_to) if message.reply_to and message.reply_to.isdecimal() else None

        raw_msg = _render_message_as_plain_text(message)
        self.logger.debug("send_message raw text: %s", raw_msg)

        msg = _render_message_as_html(message)

        if msg:
            await self._application.bot.send_message(
                chat_id=raw_chat_id,
                text=msg,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=reply_to_message_id,
                message_thread_id=raw_thread_id,
            )

        for file_path in files:
            with open(file_path, "rb") as file:
                await self._application.bot.send_document(
                    chat_id=raw_chat_id,
                    document=file,
                    reply_to_message_id=reply_to_message_id,
                    message_thread_id=raw_thread_id,
                )

        self.logger.info("send_message: %s", message)

    async def receive_message(self, message: ChatMessage) -> None:
        await self._message_handler(message)

    async def _on_receive_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context

        message = update.effective_message
        if message is None:
            return

        self.logger.info(message)

        if not await self.is_message_allowed(message):
            return

        chat_id = create_chat_id(message.chat.type, message.chat.id, message.message_thread_id)
        self._chat_infos[chat_id] = ChatInfo(channel_id=self.id, chat_id=chat_id, name=_chat_title(message))

        chat_message = convert_telegram_bot_message_to_chat_message(
            self.id,
            message,
            lifespan=self.build_message_lifespan(raw_chat_id=message.chat_id, raw_thread_id=message.message_thread_id),
        )
        self._messages[chat_id].append(chat_message)
        self._application.create_task(
            self.receive_message(chat_message),
            update=update,
            name=f"{self.__class__.__name__}:{self.id}:receive:{chat_id}:{chat_message.id}",
        )

    @contextlib.asynccontextmanager
    async def build_message_lifespan(self, raw_chat_id: int, raw_thread_id: int | None) -> AsyncIterator[None]:
        await self._application.bot.send_chat_action(chat_id=raw_chat_id, action=ChatAction.TYPING, message_thread_id=raw_thread_id)
        yield

    async def is_message_allowed(self, message: Message) -> bool:
        if message.from_user is None:
            return False

        if message.from_user.is_bot:
            return False

        user_id = str(message.from_user.id)
        raw_chat_id = str(message.chat.id)

        if message.chat.type == "private":
            return self._matches_whitelist(self.settings.whitelist, user_id)

        policy = self._get_group_policy(raw_chat_id)
        if policy is None:
            return False

        if policy.only_mention and not self._is_mentioned(message):
            return False

        return self._matches_whitelist(policy.whitelist, user_id)

    def _get_group_policy(self, chat_id: str) -> TelegramBotChannelGroupPolicy | None:
        return self.settings.groups.get(chat_id) or self.settings.groups.get(TELEGRAM_BOT_CHAT_ALL_INDICATOR)

    def _matches_whitelist(self, whitelist: list[str], user_id: str) -> bool:
        return TELEGRAM_BOT_CHAT_ALL_INDICATOR in whitelist or user_id in whitelist

    def _is_mentioned(self, message: Message) -> bool:
        if self._is_reply_to_me(message):
            return True

        username = self._cached_me_username
        if username is None:
            return False

        text = _message_text(message)
        if text is None:
            return False

        entities = list(message.entities or message.caption_entities or [])
        for entity in entities:
            if entity.type == MessageEntity.MENTION:
                mention = message.parse_entity(entity)
                if mention.removeprefix("@").casefold() == username.casefold():
                    return True

            if entity.type == MessageEntity.TEXT_MENTION and entity.user and entity.user.username:
                if entity.user.username.casefold() == username.casefold():
                    return True

        return False

    def _is_reply_to_me(self, message: Message) -> bool:
        bot_id = self._cached_me_id
        if bot_id is None or message.reply_to_message is None or message.reply_to_message.from_user is None:
            return False

        return message.reply_to_message.from_user.id == bot_id

    async def list_chats(self, with_archived: bool = False) -> list[ChatInfo]:
        del with_archived
        return list(self._chat_infos.values())

    async def list_messages(self, chat_id: str, num: int = 1, date_start: datetime | None = None, date_end: datetime | None = None) -> list[ChatMessage]:
        messages = list(self._messages.get(chat_id, []))

        if date_start is not None or date_end is not None:
            # The Bot API does not provide message history through polling. The in-memory cache does not preserve
            # Telegram message timestamps, so date filtering is intentionally a no-op for cached bot messages.
            pass

        return messages[-num:]
