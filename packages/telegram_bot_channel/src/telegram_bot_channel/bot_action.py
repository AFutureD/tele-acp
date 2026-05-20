import asyncio
import contextlib
import logging
from typing import Self

from telegram.ext import Application

TELEGRAM_BOT_CHAT_ACTION_DELAY_IN_SECONDS = 4.0


class _TelegramBotChatAction:
    def __init__(
        self,
        application: Application,
        chat_id: int,
        action: str,
        *,
        message_thread_id: int | None = None,
        delay: float = TELEGRAM_BOT_CHAT_ACTION_DELAY_IN_SECONDS,
    ):
        self._application = application
        self._chat_id = chat_id
        self._action = action
        self._message_thread_id = message_thread_id
        self._delay = delay
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._logger = logging.getLogger(f"{__name__}:{self.__class__.__name__}")

    async def __aenter__(self) -> Self:
        self._running = True
        self._task = self._application.create_task(
            self._update(),
            name=f"{self.__class__.__name__}:{self._chat_id}:{self._message_thread_id}:{self._action}",
        )
        return self

    async def __aexit__(self, *args) -> None:
        self._running = False
        if self._task is None:
            return

        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

        self._task = None

    async def _update(self) -> None:
        while self._running:
            try:
                await self._application.bot.send_chat_action(
                    chat_id=self._chat_id,
                    action=self._action,
                    message_thread_id=self._message_thread_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._logger.debug("Failed to send Telegram bot chat action: %s", e)

            await asyncio.sleep(self._delay)
