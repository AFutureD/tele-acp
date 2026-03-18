import asyncio
import contextlib
import logging
from typing import AsyncIterator

from tele_acp_core import Channel, ChatMessage
from telegram_channel import TelegramChannel

from tele_acp.config import Config
from tele_acp.router import Router


class ChannelHub:
    def __init__(self, config: Config, router: Router | None = None) -> None:
        self._config = config
        self._router = router
        self.logger = logging.getLogger(__name__)

        self._channels_lock = asyncio.Lock()
        self._channels: dict[str, Channel] = {}

        for channel_id, channel_settings in self._config.channels.items():
            channel = TelegramChannel(channel_id, self._config.api_id, self._config.api_hash, channel_settings, self._on_receive_new_message)
            self._channels[channel.id] = channel

    def set_router(self, router: Router) -> None:
        self._router = router

    def get_channel(self, channel_id: str) -> Channel | None:
        return self._channels.get(channel_id)

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[ChannelHub]:
        assert len(self._channels) != 0, "No channels configured"

        async with contextlib.AsyncExitStack() as stack:
            async with self._channels_lock:
                for channel in self._channels.values():
                    channel: Channel = await stack.enter_async_context(channel.run_until_finish())
                    if not await channel.status:
                        raise RuntimeError(f"Channel {channel.id} is not authenticated")

            yield self

    async def _on_receive_new_message(self, message: ChatMessage) -> None:
        """Called when a new message is received from a channel."""
        assert self._router is not None

        await self._router.route(message)
