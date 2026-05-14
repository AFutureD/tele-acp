from __future__ import annotations

import contextlib
import logging
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Self

from susie_core import ChatInfo, ChatMessage, ChatMessageFilePart, ChatMessagePart, ChatMessageTextPart
from telegram import Message, MessageEntity, Update
from telegram.constants import ChatAction
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, filters

from .settings import TELEGRAM_BOT_CHAT_ALL_INDICATOR, TelegramBotChannelGroupPolicy, TelegramBotChannelSettings

type MessageHandlerFn = Callable[[ChatMessage], Awaitable[None]]


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

    return ChatMessage(
        id=str(message.message_id),
        channel_id=channel_id,
        chat_id=str(message.chat_id),
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


class TelegramBotChannel:
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
        self._cached_me_username: str | None = None
        self._chat_infos: dict[str, ChatInfo] = {}
        self._messages: defaultdict[str, deque[ChatMessage]] = defaultdict(lambda: deque(maxlen=100))
        self.logger = logging.getLogger(f"{self.__class__.__name__}:{self.id}")

    @property
    def id(self) -> str:
        return self._id

    @property
    async def status(self) -> bool:
        try:
            me = await self._application.bot.get_me()
        except Exception:
            self.logger.exception("Failed to get Telegram bot status")
            return False

        self._cached_me_username = me.username
        return True

    @contextlib.asynccontextmanager
    async def run_until_finish(self) -> AsyncIterator[Self]:
        await self._application.initialize()
        try:
            me = await self._application.bot.get_me()
            self._cached_me_username = me.username

            if self._application.updater is None:
                raise RuntimeError("Telegram bot updater is not available")

            await self._application.updater.start_polling(drop_pending_updates=self.settings.drop_pending_updates)
            await self._application.start()

            yield self
        finally:
            if self._application.updater is not None and self._application.updater.running:
                await self._application.updater.stop()
            if self._application.running:
                await self._application.stop()
            await self._application.shutdown()

    async def send_message(self, message: ChatMessage) -> None:
        texts = [part.text for part in message.parts if isinstance(part, ChatMessageTextPart)]
        content = "\n".join(texts)
        files = [part.path for part in message.parts if isinstance(part, ChatMessageFilePart)]
        receiver = message.receiver or message.chat_id
        reply_to_message_id = int(message.reply_to) if message.reply_to and message.reply_to.isdecimal() else None

        if content:
            await self._application.bot.send_message(
                chat_id=receiver,
                text=content,
                disable_notification=message.mute,
                reply_to_message_id=reply_to_message_id,
            )

        for file_path in files:
            with open(file_path, "rb") as file:
                await self._application.bot.send_document(
                    chat_id=receiver,
                    document=file,
                    disable_notification=message.mute,
                    reply_to_message_id=reply_to_message_id,
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

        chat_id = str(message.chat_id)
        self._chat_infos[chat_id] = ChatInfo(channel_id=self.id, chat_id=chat_id, name=_chat_title(message))

        chat_message = convert_telegram_bot_message_to_chat_message(
            self.id,
            message,
            lifespan=self.build_message_lifespan(chat_id=message.chat_id),
        )
        self._messages[chat_id].append(chat_message)
        await self.receive_message(chat_message)

    @contextlib.asynccontextmanager
    async def build_message_lifespan(self, chat_id: int) -> AsyncIterator[None]:
        await self._application.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        yield

    async def is_message_allowed(self, message: Message) -> bool:
        if message.from_user is None:
            return False

        if message.from_user.is_bot:
            return False

        user_id = str(message.from_user.id)
        chat_id = str(message.chat_id)

        if message.chat.type == "private":
            return self._matches_whitelist(self.settings.whitelist, user_id)

        policy = self._get_group_policy(chat_id)
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
