from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator

import anyio
import telethon
from acp.schema import HttpMcpServer, McpServerStdio, SseMcpServer
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from telethon.custom import Message

from tele_acp.acp import ACPAgentConfig
from tele_acp.shared import get_app_user_defualt_dir
from tele_acp.telegram import TGActionProvider
from tele_acp.types import AcpMessageChunk, OutBoundMessage
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


class AgentBaseThread:
    def __init__(
        self,
        agent_config: AgentConfig,
        acp_config: ACPAgentConfig,
        inbound_recv: MemoryObjectReceiveStream[Message],
        outbound_send: MemoryObjectSendStream[OutBoundMessage],
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger(f"{__name__}")

        self.id = agent_config.id
        self.agent_config = agent_config
        self.inbound_recv = inbound_recv
        self.outbound_send = outbound_send

        inner_outbound_writer, inner_outbound = anyio.create_memory_object_stream[AcpMessageChunk](0)
        self._inner_outbound = inner_outbound

        self._runtime = ACPAgentRuntime(
            agent_config=acp_config,
            outbound_send=inner_outbound_writer,
            logger=self.logger,
            cwd=self.work_dir(agent_config.id, agent_config.work_dir),
            mcp_servers=mcp_servers,
        )

        self.queue_message_when_idle = False
        self._turn_task: asyncio.Task | None = None

        self._message_lock = asyncio.Lock()
        self.message: AcpMessage | None = None

    @staticmethod
    def work_dir(acp_id: str, work_dir: str | None) -> Path:
        if work_dir:
            path = Path(work_dir)
            if path.exists():
                return path

        return get_agent_work_dir(acp_id)

    async def run_until_finish(self) -> None:
        async with AsyncExitStack() as ts:
            await ts.enter_async_context(self.outbound_send)
            await ts.enter_async_context(self.inbound_recv)
            await ts.enter_async_context(self._runtime)
            await ts.enter_async_context(self._handler_acp_message())

            async for message in self.inbound_recv:
                content = message.message
                if not content or not isinstance(content, str):
                    continue

                if not self.queue_message_when_idle:
                    if self._turn_task is not None and not self._turn_task.done():
                        self.logger.info("Agent turn is still running, skip new input")
                        continue
                    self._turn_task = asyncio.create_task(self.run_turn(content))
                else:
                    pass

    def build_runtime_messages(self, content: str) -> list[str]:
        return [content]

    async def run_turn(self, content: str) -> None:
        await self._start_turn(content)
        try:
            async with self.turn_context():
                response = await self._runtime.send_immediately(messages=self.build_runtime_messages(content))

                async with self._message_lock:
                    if self.message is not None:
                        self.message.stopReason = response.stopReason
        finally:
            await self._finish_turn()

    @asynccontextmanager
    async def _handler_acp_message(self):
        task = asyncio.create_task(self._run_acp_message_handler())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _run_acp_message_handler(self) -> None:
        async with self._inner_outbound:
            async for chunk in self._inner_outbound:
                async with self._message_lock:
                    if self.message is None:
                        continue

                    # TODO: call method
                    self.message.chunks.append(chunk)

    @asynccontextmanager
    async def turn_context(self) -> AsyncIterator[None]:
        yield

    async def _start_turn(self, content: str) -> None:
        async with self._message_lock:
            message = self.message
            if not (message is not None and message.stopReason == "cancelled"):
                message = AcpMessage(
                    prompt=None,
                    model=None,
                    chunks=[],
                    usage=None,
                )
            else:
                message.chunks.clear()
                message.usage = None
                message.stopReason = None

            message.prompt = content
            self.message = message

    async def _finish_turn(self) -> None:
        """
        Clean up message.
        keep it if this turn is stop by `cancelled` and can be reuse in next turn.
        """

        async with self._message_lock:
            message = self.message

            if message is None:
                return

            self.logger.info(f"Agent turn has end {message.markdown()}")

            if not (message.stopReason and message.stopReason == "cancelled"):
                self.message = None

        await self.outbound_send.send(message)


class AgentThread(AgentBaseThread):
    def __init__(
        self,
        dialog_id: str,
        peer: telethon.types.TypePeer,
        agent_config: AgentConfig,
        acp_config: ACPAgentConfig,
        inbound_recv: MemoryObjectReceiveStream[Message],
        outbound_send: MemoryObjectSendStream[OutBoundMessage],
        tele_action: TGActionProvider,
    ) -> None:
        logger = logging.getLogger(f"{__name__}:{dialog_id}")

        mcp_server = HttpMcpServer(name="telegram_mcp_server", url="http://127.0.0.1:9998/mcp", headers=[], type="http")
        super().__init__(
            agent_config=agent_config, acp_config=acp_config, inbound_recv=inbound_recv, outbound_send=outbound_send, mcp_servers=[mcp_server], logger=logger
        )

        self.peer = peer
        self.dialog_id = dialog_id
        self._tele_action = tele_action

    @asynccontextmanager
    async def turn_context(self) -> AsyncIterator[None]:
        async with self._tele_action.with_action(self.peer, "typing"):
            yield

    def build_runtime_messages(self, content: str) -> list[str]:
        prompt = (
            # Context Info
            f"<CONTEXT>\n"
            f"This is a message from Telegram.\n"
            f"Dialog ID: {self.dialog_id}\n"
            f"Peer ID: {self.peer.to_json()}\n"
            f"</CONTEXT>\n"
            f"\n"
            # IMPORTANT
            f"<IMPORTANT>\n"
            f"always using `Telegram MCP` send_message method when you have some message needs replay to this message.\n"
            f"</IMPORTANT>\n"
            f"\n"
            # User Input
            f"User Content:\n"
            f"{content}"
        )

        return [prompt]
