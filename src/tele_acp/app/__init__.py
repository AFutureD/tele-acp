import asyncio
import logging
from contextlib import AsyncExitStack

import telethon
from telethon import events
from telethon.custom import Message

from tele_acp.mcp import MCP
from tele_acp.telegram import TGClient
from tele_acp.types.config import Config

from .dialog import DialogManager


class APP:
    def __init__(self, config: Config) -> None:
        from tele_acp.mcp import mcp_server

        # Telegram Client
        tele_client = TGClient.create(session_name=None, config=config)
        tele_client.add_event_handler(self.on_tele_client_receive_message, events.NewMessage())

        # MCP Server
        mcp_server.set_tg_client(tele_client)

        # Initial Variable
        self.logger = logging.getLogger(__name__)

        self._config = config
        self._tele_client = tele_client
        self._mcp_server: MCP = mcp_server

        self._dialog_manager = DialogManager(config, tele_client)

    async def run_until_finish(self):
        async with AsyncExitStack() as stack:
            stack.push_async_callback(self._shutdown)
            stack.callback(self.logger.info, "Finished")

            tele_client = await stack.enter_async_context(self._tele_client)
            await stack.enter_async_context(self._dialog_manager.run())

            async def _wait_for_disconnect() -> None:
                await tele_client.disconnected

            group = await stack.enter_async_context(asyncio.TaskGroup())
            group.create_task(self._mcp_server.run_streamable_http_async())
            group.create_task(_wait_for_disconnect())

    async def on_tele_client_receive_message(self, event: events.NewMessage.Event):
        message: Message = event.message
        self.logger.info(f"New message received {message}")

        if message.out:
            return

        peer = message.peer_id

        # User Only
        if not isinstance(peer, telethon.types.PeerUser):
            return

        contacts = await self._tele_client.get_contact_user_peer()
        if not any(contact.user_id == peer.user_id for contact in contacts):
            return

        await self.dispatch_tele_message(message)

    async def dispatch_tele_message(self, message: Message):
        await self._dialog_manager.handle_message(message)

    async def _shutdown(self) -> None:
        pass
