from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from pathlib import Path

import anyio
import telethon
from acp.schema import HttpMcpServer
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from telethon.custom import Message

from tele_acp.acp import ACPAgentConfig
from tele_acp.shared import get_app_user_defualt_dir
from tele_acp.types import AcpMessageChunk, OutBoundMessage, peer_hash_into_str
from tele_acp.types.acp import AcpMessage
from tele_acp.types.agent import AgentConfig

from .agent import ACPAgentRuntime


def _get_agent_work_folder():
    ret = get_app_user_defualt_dir() / "workspace"
    ret.mkdir(parents=True, exist_ok=True)
    return ret


def get_agent_work_dir(id: str) -> Path:
    agent_dir = _get_agent_work_folder() / id
    agent_dir.mkdir(parents=True, exist_ok=True)
    return agent_dir


class AgentThread:
    def __init__(
        self,
        dialog_id: str,
        peer: telethon.types.TypePeer,
        agent_config: AgentConfig,
        acp_config: ACPAgentConfig,
        inbound_recv: MemoryObjectReceiveStream[Message],
        outbound_send: MemoryObjectSendStream[OutBoundMessage],
    ) -> None:
        self.agent_config = agent_config
        self.peer = peer
        self.dialog_id = dialog_id
        self.inbound_recv = inbound_recv
        self.outbound_send = outbound_send

        self.logger = logging.getLogger(f"{__name__}:{dialog_id}")

        inner_outbound_writer, inner_outbound = anyio.create_memory_object_stream[AcpMessageChunk](0)
        self._inner_outbound = inner_outbound

        self._message_lock = asyncio.Lock()
        self.message: AcpMessage | None = None

        mcp_server = HttpMcpServer(name="telegram_mcp_server", url="http://127.0.0.1:9998/mcp", headers=[], type="http")
        self._runtime = ACPAgentRuntime(
            agent_config=acp_config,
            outbound_send=inner_outbound_writer,
            logger=self.logger,
            cwd=self.work_dir(),
            mcp_servers=[mcp_server],
        )

    def work_dir(self) -> Path:
        acp_cwd = self.agent_config.work_dir
        if acp_cwd:
            path = Path(acp_cwd)
            if path.exists():
                return path

        return get_agent_work_dir(self.agent_config.id)

    async def run_until_finish(self) -> None:
        async with AsyncExitStack() as ts:
            await ts.enter_async_context(self.outbound_send)
            await ts.enter_async_context(self.inbound_recv)
            await ts.enter_async_context(self._runtime)
            await ts.enter_async_context(self.handler_acp_message())

            async for message in self.inbound_recv:
                content = message.message
                if not content or not isinstance(content, str):
                    continue

                self.logger.info("Dialog %s received: %s", self.dialog_id, content)

                async with self.in_turn():
                    async with self._message_lock:
                        if self.message is None:
                            self.logger.warning("Message state is not initialized for dialog %s", self.dialog_id)
                            continue
                        self.message.prompt = content
                    prompt = f"""
                    This is a message from Telegram.
                    Dialog ID: {self.dialog_id}
                    Peer ID: {self.peer.to_json()}

                    User Content:
                    {content}
                    """
                    await self._forward_to_acp(prompt)

    async def _run_acp_message_handler(self) -> None:
        async with self._inner_outbound:
            async for chunk in self._inner_outbound:
                async with self._message_lock:
                    if self.message is None:
                        continue
                    self.message.chunks.append(chunk)
                    message = self.message.model_copy(deep=True)

                await self.outbound_send.send(message)

    @asynccontextmanager
    async def handler_acp_message(self):
        task = asyncio.create_task(self._run_acp_message_handler())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def command_help(self) -> None:
        await self._send_system_message(
            "\n".join(
                [
                    "Commands:",
                    "/help",
                    "/agent list",
                    "/agent current",
                    "/agent use <id>",
                    "/session list",
                    "/session current",
                    "/session new [name]",
                    "/session use <name>",
                    "/session reset",
                    "/reset",
                ]
            )
        )

    async def command_error(self, message: str) -> None:
        pass

    async def command_unknown(self, name: str) -> None:
        pass

    async def command_agent_list(self) -> None:
        pass

    async def command_agent_current(self) -> None:
        pass

    async def command_agent_use(self, agent_id: str) -> None:
        pass

    async def command_session_list(self) -> None:
        pass

    async def command_session_current(self) -> None:
        pass

    async def command_session_new(self, session_id: str | None) -> None:
        pass

    async def command_session_use(self, session_id: str) -> None:
        pass

    async def command_session_reset(self) -> None:
        pass

    async def _forward_to_acp(self, content: str) -> None:
        try:
            await self._runtime.prompt(content=content)
            return
        except Exception:
            self.logger.exception("Prompt failed for dialog %s, retrying once", self.dialog_id)

        await self._runtime.restart(self._runtime.agent_config)
        await self._runtime.prompt(content=content)

    async def _send_system_message(self, message: str) -> None:
        await self.outbound_send.send(message)

    @asynccontextmanager
    async def in_turn(self):
        try:
            await self._start_turn()
            yield
        finally:
            await self._finish_turn()

    async def _start_turn(self) -> None:
        async with self._message_lock:
            self.message = AcpMessage(
                prompt=None,
                model=None,
                chunks=[],
                usage=None,
            )

    async def _finish_turn(self) -> None:
        async with self._message_lock:
            if self.message is None:
                return

            final = self.message.model_copy(deep=True)
            final.in_turn = False

            self.message = None

        await self.outbound_send.send(final)
