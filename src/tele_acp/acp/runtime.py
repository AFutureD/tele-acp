import asyncio
import contextlib
import logging
from pathlib import Path
from typing import AsyncIterator

import acp

from tele_acp.types import AgentConfig, Config

from ..shared import get_app_user_defualt_dir
from .client import ACPAgentConfig, ACPUpdateChunk
from .connection import ACPAgentConnection
from .message import AcpContentBlock, AcpMessage


def _get_agent_work_folder():
    ret = get_app_user_defualt_dir() / "workspace"
    ret.mkdir(parents=True, exist_ok=True)
    return ret


def get_agent_work_dir(id: str) -> Path:
    agent_dir = _get_agent_work_folder() / id
    agent_dir.mkdir(parents=True, exist_ok=True)
    return agent_dir


class ACPAgentRuntime(ACPAgentConnection):
    """spawn acp client based on ACPAgentConfig and maintain sessions"""

    def __init__(
        self,
        agent_config: ACPAgentConfig,
        cwd: str | Path | None = None,
        mcp_servers: list[acp.schema.HttpMcpServer | acp.schema.SseMcpServer | acp.schema.McpServerStdio] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}:{agent_config.id}")
        self._update_queue: asyncio.Queue[ACPUpdateChunk] | None = None

        super().__init__(agent_config, cwd, mcp_servers, self._handle_session_update)

        self._session: acp.NewSessionResponse | None = None

    # MARK: Session

    @property
    async def session(self) -> acp.NewSessionResponse:
        if self._session:
            return self._session

        session = await self._new_session()
        return session

    async def new_session(self) -> str:
        session = await self._new_session()
        return session.session_id

    async def _new_session(self) -> acp.NewSessionResponse:
        try:
            session = await self.connction.new_session(cwd=self._cwd, mcp_servers=self._mcp_servers)
            self._session = session
            return session
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            raise

    # MARK: Prompt

    async def prompt(self, parts: list[str]) -> AsyncIterator[AcpMessage]:
        session = await self.session

        prompt: list[AcpContentBlock] = list(map(lambda m: acp.text_block(m), parts))

        message = AcpMessage(prompt=prompt, model=None, usage=None)

        update_queue = asyncio.Queue[ACPUpdateChunk]()
        self._update_queue = update_queue

        async def turn_task() -> acp.PromptResponse:
            try:
                ret = await self.connction.prompt(prompt=prompt, session_id=session.session_id)
                return ret
            finally:
                update_queue.shutdown()

        task = asyncio.create_task(turn_task())
        self.logger.info("Prompting ACP agent...")

        try:
            while True:
                try:
                    update = await update_queue.get()
                except asyncio.QueueShutDown:
                    break

                self.logger.debug(f"Received update: {update}")

                match update:
                    case acp.schema.AgentMessageChunk() | acp.schema.AgentThoughtChunk() | acp.schema.ToolCallStart() | acp.schema.ToolCallProgress():
                        message.delta = update
                        message.chunks.append(update)
                    case acp.schema.CurrentModeUpdate():
                        message.model = update
                    case acp.schema.UsageUpdate():
                        message.usage = update
                    case _:
                        pass

                yield message

            response = await task  # unlikely raise error
            message.stop_reason = response.stop_reason
            yield message

            self.logger.info("End Prompt")

        finally:
            self._update_queue = None

            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _handle_session_update(self, session_id: str, update: ACPUpdateChunk) -> None:
        queue = self._update_queue
        session = self._session
        if queue is None or session is None:
            return

        if session.session_id != session_id:
            return

        try:
            await queue.put(update)
        except asyncio.QueueShutDown:
            return


class ACPRuntimeHub:
    def __init__(
        self,
        config: Config,
        mcp_servers: list[acp.schema.HttpMcpServer | acp.schema.SseMcpServer | acp.schema.McpServerStdio] | None = None,
    ) -> None:
        self._config = config
        self._stack: contextlib.AsyncExitStack | None = None
        self._mcp_servers = mcp_servers

    async def build_acp_runtime(self, agent: AgentConfig) -> ACPAgentRuntime:
        assert self._stack is not None

        acp_config = self.get_acp_config(agent.acp_id)
        assert acp_config is not None, "acp agent not found"

        runtime = ACPAgentRuntime(acp_config, cwd=agent.work_dir or get_agent_work_dir(agent.id), mcp_servers=self._mcp_servers)
        await self._stack.enter_async_context(runtime)

        return runtime

    def get_acp_config(self, agent_id: str) -> ACPAgentConfig | None:
        # hard-coded agents used during development
        _acp_agents: dict[str, ACPAgentConfig] = {
            agent.id: agent
            for agent in [
                ACPAgentConfig("codex", "Codex", "codex-acp", []),
                ACPAgentConfig("kimi", "Kimi CLI", "kimi", ["acp"]),
            ]
        }

        return _acp_agents.get(agent_id)

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[ACPRuntimeHub]:
        async with contextlib.AsyncExitStack() as stack:
            self._stack = stack
            try:
                yield self
            finally:
                self._stack = None
