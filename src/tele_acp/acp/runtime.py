import asyncio
import contextlib
import logging
import uuid
from pathlib import Path
from typing import AsyncIterator, Self

import acp
from acp.schema import SessionConfigOption, SessionConfigSelectOption
from tele_acp_core import AgentConfig

from tele_acp.config import Config
from tele_acp.shared import get_app_user_default_dir

from .client import ACPAgentConfig, ACPUpdateChunk
from .connection import ACPAgentConnection
from .message import AcpContentBlock, AcpMessage


def _get_agent_work_folder():
    ret = get_app_user_default_dir() / "workspace"
    ret.mkdir(parents=True, exist_ok=True)
    return ret


def get_agent_work_dir(id: str) -> Path:
    agent_dir = _get_agent_work_folder() / id
    agent_dir.mkdir(parents=True, exist_ok=True)
    return agent_dir


MODEL_CONFIG_ID = "model"


class ACPAgentRuntime(ACPAgentConnection):
    """spawn acp client based on ACPAgentConfig and maintain sessions"""

    def __init__(
        self,
        id: str,
        agent_config: ACPAgentConfig,
        cwd: str | Path | None = None,
        mcp_servers: list[acp.schema.HttpMcpServer | acp.schema.SseMcpServer | acp.schema.McpServerStdio] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}:{agent_config.id}")
        self._update_queue: asyncio.Queue[ACPUpdateChunk] | None = None

        super().__init__(agent_config, cwd, mcp_servers, self._handle_session_update)

        self.id = id
        self._session_id: str | None = None
        self.session_options: dict[str, SessionConfigOption] = {}

    # MARK: Session

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def require_session_id(self) -> str:
        if session_id := self._session_id:
            return self._session_id

        session_id = await self._new_session()
        return session_id

    async def new_session(self) -> str:
        session_id = await self._new_session()
        return session_id

    async def _new_session(self) -> str:
        if not self.is_active:
            await self.cancel()

        try:
            new_session = await self.connection.new_session(cwd=self._cwd, mcp_servers=self._mcp_servers)
            session_id = new_session.session_id

            # TODO: [2026/03/24 <Huanan>] it will raise "Resource not found" from codex acp. do not know why.
            # issue: https://github.com/zed-industries/codex-acp/issues/203
            # _ = await self.connction.load_session(cwd=self._cwd, session_id=session_id)

            self._session_id = session_id
            self.set_session_options(new_session.config_options)
            return session_id
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            raise

    # MARK: Prompt

    @property
    def is_active(self) -> bool:
        return self._update_queue is not None

    async def prompt(self, parts: list[str]) -> AsyncIterator[AcpMessage]:
        session_id = await self.require_session_id()

        prompt: list[AcpContentBlock] = list(map(lambda m: acp.text_block(m), parts))

        message = AcpMessage(prompt=prompt, model=None, usage=None)

        update_queue = asyncio.Queue[ACPUpdateChunk]()
        self._update_queue = update_queue

        async def turn_task() -> acp.PromptResponse:
            try:
                ret = await self.connection.prompt(prompt=prompt, session_id=session_id)
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

    async def cancel(self):
        if not self.is_active:
            return

        if session_id := self._session_id:
            await self.connection.cancel(session_id)

    async def _handle_session_update(self, session_id: str, update: ACPUpdateChunk) -> None:
        queue = self._update_queue
        current_session_id = self._session_id
        if queue is None or current_session_id is None:
            return

        if current_session_id != session_id:
            return

        try:
            await queue.put(update)
        except asyncio.QueueShutDown:
            return

    def set_session_options(self, new_value: list[SessionConfigOption] | None = None) -> None:
        if new_value is None:
            self.session_options.clear()
            return

        for opt in new_value:
            self.session_options[opt.root.id] = opt

    async def model(self) -> str | None:
        session_options = self.session_options
        if session_options is None:
            return None

        option = session_options.get(MODEL_CONFIG_ID)
        if option is None:
            return None

        return option.root.current_value

    async def list_model_opts(self) -> list[SessionConfigSelectOption]:
        session_options = self.session_options
        if session_options is None:
            return []

        option = session_options.get(MODEL_CONFIG_ID)
        if option is None:
            return []

        selects = option.root.options

        # TODO: support SessionConfigSelectGroup
        selects = [x for x in selects if isinstance(x, SessionConfigSelectOption)]

        return selects

    async def set_model(self, value) -> bool:
        session_id = self.session_id
        if session_id is None:
            return False

        session_options = self.session_options
        if session_options is None:
            return False

        option = session_options.get(MODEL_CONFIG_ID)
        if option is None:
            return False

        select = next((x for x in option.root.options if x.value == value), None)
        if select is None:
            return False

        ret = await self.connection.set_config_option(MODEL_CONFIG_ID, session_id, select.value)
        self.set_session_options(ret.config_options)
        return True


class ACPRuntimeHub:
    def __init__(
        self,
        config: Config,
        mcp_servers: list[acp.schema.HttpMcpServer | acp.schema.SseMcpServer | acp.schema.McpServerStdio] | None = None,
    ) -> None:
        self._config = config
        self._stack: contextlib.AsyncExitStack | None = None
        self._mcp_servers = mcp_servers
        self._runtimes: dict[str, ACPAgentRuntime] = {}

    async def spawn_acp_runtime(self, agent: AgentConfig) -> ACPAgentRuntime:
        assert self._stack is not None

        acp_config = self.get_acp_config(agent.acp_id)
        assert acp_config is not None, "acp agent not found"

        id = str(uuid.uuid4())
        runtime = ACPAgentRuntime(id, acp_config, cwd=agent.work_dir or get_agent_work_dir(agent.id), mcp_servers=self._mcp_servers)
        await self._stack.enter_async_context(runtime)
        self._runtimes[id] = runtime

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

    def get_runtime(self, id: str) -> ACPAgentRuntime | None:
        return self._runtimes.get(id)

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[Self]:
        async with contextlib.AsyncExitStack() as stack:
            self._stack = stack
            try:
                yield self
            finally:
                self._stack = None
