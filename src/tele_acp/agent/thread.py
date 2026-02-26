from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from acp.schema import HttpMcpServer
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from telethon.custom import Message

from tele_acp.acp import ACPAgentConfig

from .agent import ACPAgentRuntime


class AgentThread:
    def __init__(
        self,
        dialog_id: str,
        agent_config: ACPAgentConfig,
        inbound_recv: MemoryObjectReceiveStream[Message],
        outbound_send: MemoryObjectSendStream[str | None],
    ) -> None:
        self.dialog_id = dialog_id
        self.inbound_recv = inbound_recv
        self.outbound_send = outbound_send
        self.logger = logging.getLogger(f"{__name__}:{dialog_id}")

        mcp_server = HttpMcpServer(name="Telegram ACP Interface", url="http://127.0.0.1:9998/mcp", headers=[], type="http")
        self._runtime = ACPAgentRuntime(
            agent_config=agent_config,
            outbound_send=outbound_send,
            logger=self.logger,
            cwd=Path.cwd(),
            mcp_servers=[mcp_server],
        )

    async def run_until_finish(self) -> None:
        async with AsyncExitStack() as ts:
            await ts.enter_async_context(self.outbound_send)
            await ts.enter_async_context(self.inbound_recv)
            await ts.enter_async_context(self._runtime)

            async for message in self.inbound_recv:
                content = message.message
                if not content:
                    continue

                self.logger.info("Dialog %s received: %s", self.dialog_id, content)

                async with self.in_turn():
                    await self._forward_to_acp(content)

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
        await self._start_turn()
        try:
            yield
        finally:
            await self._finish_turn()

    async def _start_turn(self) -> None:
        pass

    async def _finish_turn(self) -> None:
        await self.outbound_send.send(None)
