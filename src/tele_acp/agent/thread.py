from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator

import anyio
import telethon
from acp.schema import HttpMcpServer
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


class AgentThread:
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
        self.agent_config = agent_config
        self.peer = peer
        self.dialog_id = dialog_id
        self.inbound_recv = inbound_recv
        self.outbound_send = outbound_send
        self._tele_action = tele_action

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

        self.queue_message_when_idle = False
        self._turn_task: asyncio.Task | None = None

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

                if not self.queue_message_when_idle:
                    self._turn_task = asyncio.create_task(self.run_turn(content))
                else:
                    pass

    async def run_turn(self, content: str):
        async with self.in_turn(content) as message:
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
            response = await self._runtime.send_immediately(messages=[prompt])

            message.stopReason = response.stopReason
        pass

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

    async def _send_system_message(self, message: str) -> None:
        await self.outbound_send.send(message)

    @asynccontextmanager
    async def in_turn(self, content: str) -> AsyncIterator[AcpMessage]:
        try:
            message = await self._start_turn(content)
            async with self._tele_action.with_action(self.peer, "typing"):
                yield message
        finally:
            await self._finish_turn()

    async def _start_turn(self, content: str) -> AcpMessage:
        async with self._message_lock:
            message = self.message

        if not (message is not None and message.stopReason == "cancelled"):
            message = AcpMessage(
                prompt=None,
                model=None,
                chunks=[],
                usage=None,
            )
        message.prompt = content

        async with self._message_lock:
            self.message = message
        return message

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
