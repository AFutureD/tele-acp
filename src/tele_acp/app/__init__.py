import asyncio
from contextlib import suppress
from dataclasses import dataclass
import logging

import anyio
from anyio import BrokenResourceError, ClosedResourceError
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from tele_acp.acp import ACPAgentConfig
from tele_acp.utils.throttle import Throttler
import telethon
from telethon import events
from telethon.custom import Message

from tele_acp.mcp import MCP
from tele_acp.telegram import TGClient
from tele_acp.types import peer_hash_into_str
from tele_acp.types.config import Config
from tele_acp.agent import Agent, AgentThread


@dataclass
class DialogContext:
    inbound_send: MemoryObjectSendStream[Message]
    outbound_recv: MemoryObjectReceiveStream[str | None]
    outbound_consumer_task: asyncio.Task[None] | None
    lifecycle_task: asyncio.Task[None] | None
    last_activity_ts: float


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

        self._dialog_dict_lock = asyncio.Lock()
        self._dialog_ctx: dict[str, DialogContext] = {}

    async def run_until_finish(self):
        # start tg client
        try:
            async with self._tele_client as tele_client:

                async def _wait_for_disconnect() -> None:
                    await tele_client.disconnected

                async with asyncio.TaskGroup() as group:
                    group.create_task(self._mcp_server.run_streamable_http_async())
                    group.create_task(_wait_for_disconnect())
                    group.create_task(self._schedule_cron_clean_idle_dialogs())
        finally:
            await self._shutdown()
            self.logger.info("Finished")

    async def on_tele_client_receive_message(self, event: events.NewMessage.Event):
        message: Message = event.message
        self.logger.info(f"New message received {message}")

        if message.out:
            return

        # User Only
        if not isinstance(message.peer_id, telethon.types.PeerUser):
            return

        await self.dispatch_tele_message(message)

    async def dispatch_tele_message(self, message: Message):
        dialog_id = peer_hash_into_str(message.peer_id)
        ctx = await self._get_or_create_dialog(dialog_id)
        ctx.last_activity_ts = asyncio.get_running_loop().time()
        await ctx.inbound_send.send(message)

    async def _get_or_create_dialog(self, dialog_id: str) -> DialogContext:
        async with self._dialog_dict_lock:
            existing = self._dialog_ctx.get(dialog_id)
            if existing:
                return existing

            loop = asyncio.get_running_loop()

            inbound_send, inbound_recv = anyio.create_memory_object_stream[Message](0)
            outbound_send, outbound_recv = anyio.create_memory_object_stream[str | None](0)

            outbound_consumer_task = loop.create_task(self._consume_outbound(dialog_id, outbound_recv))
            lifecycle_task = loop.create_task(self._run_dialog_lifecycle(dialog_id, inbound_recv, outbound_send))

            ctx = DialogContext(
                inbound_send=inbound_send,
                outbound_recv=outbound_recv,
                outbound_consumer_task=outbound_consumer_task,
                lifecycle_task=lifecycle_task,
                last_activity_ts=loop.time(),
            )
            self._dialog_ctx[dialog_id] = ctx
            return ctx

    async def get_agent_for_dialog(self, dialog_id: str) -> ACPAgentConfig:
        _ = dialog_id
        return ACPAgentConfig(id="kimi", name="Kimi CLI", acp_path="kimi", acp_args=["acp"])

    async def _consume_outbound(self, dialog_id: str, outbound_recv: MemoryObjectReceiveStream[str]) -> None:
        _ = dialog_id

        async with outbound_recv:
            async for message in outbound_recv:
                print()
                print(f"========= {dialog_id}")
                print(message)
                print()

    async def _run_dialog_lifecycle(
        self, dialog_id: str, inbound_recv: MemoryObjectReceiveStream[Message], outbound_send: MemoryObjectSendStream[str | None]
    ) -> None:
        try:
            agent_config = await self.get_agent_for_dialog(dialog_id)
            agent_thread = AgentThread(dialog_id, agent_config, inbound_recv, outbound_send)
            await agent_thread.run_until_finish()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger.exception("AgentThread failed for dialog %s", dialog_id)
        finally:
            await self._close_dialog(dialog_id=dialog_id)

    async def _close_dialog(self, dialog_id: str) -> None:
        async with self._dialog_dict_lock:
            ctx = self._dialog_ctx.get(dialog_id)

        if not ctx:
            return

        with suppress(Exception):
            await ctx.inbound_send.aclose()
        with suppress(Exception):
            await ctx.outbound_recv.aclose()

        if ctx.outbound_consumer_task and not ctx.outbound_consumer_task.done():
            ctx.outbound_consumer_task.cancel()
            with suppress(asyncio.CancelledError):
                await ctx.outbound_consumer_task

        if ctx.lifecycle_task and not ctx.lifecycle_task.done():
            ctx.lifecycle_task.cancel()
            with suppress(asyncio.CancelledError):
                await ctx.lifecycle_task

        async with self._dialog_dict_lock:
            if self._dialog_ctx.get(dialog_id) is ctx:
                self._dialog_ctx.pop(dialog_id, None)

    async def _schedule_cron_clean_idle_dialogs(self) -> None:
        timeout_seconds = max(self._config.dialog_idle_timeout_minutes * 60, 1)
        check_interval_seconds = min(60, timeout_seconds)
        while True:
            await asyncio.sleep(check_interval_seconds)

            loop = asyncio.get_running_loop()
            now = loop.time()

            async with self._dialog_dict_lock:
                stale_dialog_ids = [dialog_id for dialog_id, ctx in self._dialog_ctx.items() if now - ctx.last_activity_ts >= timeout_seconds]

            for dialog_id in stale_dialog_ids:
                self.logger.info("Closing idle dialog %s", dialog_id)
                await self._close_dialog(dialog_id)

    async def _shutdown(self) -> None:
        async with self._dialog_dict_lock:
            dialog_ids = list(self._dialog_ctx.keys())

        for dialog_id in dialog_ids:
            await self._close_dialog(dialog_id)
