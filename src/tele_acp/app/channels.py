from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import AsyncIterator

import telethon
from telethon import events
from telethon.custom import Message

from tele_acp.mcp import MCP
from tele_acp.telegram import TGClient
from tele_acp.types import Config


@dataclass(frozen=True, slots=True)
class InboundMessage:
    channel_id: str
    client: TGClient
    message: Message
    peer: telethon.types.TypePeer


@dataclass(frozen=True, slots=True)
class Channel:
    client: TGClient


class ChannelsGateway:
    def __init__(
        self,
        config: Config,
        *,
        mcp_server: MCP,
        on_message: Callable[[InboundMessage], Awaitable[None]],
    ) -> None:
        self._config = config
        self._mcp_server = mcp_server
        self._on_message = on_message

        self.logger = logging.getLogger("ChannelsGateway")

        self._run_lock = asyncio.Lock()
        self._has_started = False

        self._channels: dict[str, Channel] = {}
        for channel in config.channels:
            if channel.id in self._channels:
                raise ValueError(f"Duplicate Telegram channel id: {channel.id}")

            client = TGClient.create_as_login(api_id=config.api_id, api_hash=config.api_hash, config=channel)
            client.add_event_handler(self._build_message_handler(channel.id), events.NewMessage())

            self._mcp_server.set_tele_client(channel.id, client)
            self._channels[channel.id] = Channel(client=client)

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        async with self._run_lock:
            if self._has_started:
                raise RuntimeError("ChannelsGateway has already started.")
            self._has_started = True

        async with AsyncExitStack() as stack:
            for runtime in self._channels.values():
                await stack.enter_async_context(runtime.client)

            self.logger.info("Started %s Telegram clients", len(self._channels))
            try:
                yield
            finally:
                self.logger.info("Finished")

    async def wait_until_disconnect(self) -> None:
        disconnect_tasks = [asyncio.ensure_future(runtime.client.disconnected) for runtime in self._channels.values()]
        if not disconnect_tasks:
            raise RuntimeError("No Telegram clients are configured.")

        try:
            done, pending = await asyncio.wait(disconnect_tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                await task
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        finally:
            for task in disconnect_tasks:
                if not task.done():
                    task.cancel()

    def _build_message_handler(self, channel_id: str):
        async def handler(event: events.NewMessage.Event) -> None:
            await self._handle_message(channel_id, event)

        return handler

    async def _handle_message(self, channel_id: str, event: events.NewMessage.Event) -> None:
        channel = self._channels[channel_id]
        message: Message = event.message
        self.logger.info("New message received on channel `%s`: %s", channel_id, message)

        peer = message.peer_id
        if peer is None:
            return

        # Current dialog handling only supports direct user peers.
        if not isinstance(peer, telethon.types.PeerUser):
            return

        await self._on_message(
            InboundMessage(
                channel_id=channel_id,
                client=channel.client,
                message=message,
                peer=peer,
            )
        )
