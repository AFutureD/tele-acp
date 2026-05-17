import asyncio
import contextlib
import logging
import uuid
from pathlib import Path
from typing import AsyncIterator, Self

import acp
from acp.schema import SessionConfigOption, SessionConfigSelectOption
from susie_core import AgentModelOption, AssistantConfig, ChatAwareError

from susie.agent.runtime import AgentRuntime, AgentTurnStatus
from susie.settings import Config
from susie.shared import get_app_user_config_dir

from .client import ACPAgentConfig, ACPUpdateChunk
from .connection import ACPAgentConnection
from .message import AcpContentBlock, AcpMessage
from .registry import ACPRegisteryManage, ACPRegistryCache


def _get_agent_work_folder():
    ret = get_app_user_config_dir() / "workspace"
    ret.mkdir(parents=True, exist_ok=True)
    return ret


def get_agent_work_dir(id: str) -> Path:
    agent_dir = _get_agent_work_folder() / id
    agent_dir.mkdir(parents=True, exist_ok=True)
    return agent_dir


MODEL_CONFIG_ID = "model"


class ACPAgentRuntime(ACPAgentConnection, AgentRuntime):
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

        super().__init__(agent_config, cwd, self._handle_session_update)

        self._mcp_servers = mcp_servers

        self.id = id
        self._session_id: str | None = None
        self.session_options: dict[str, SessionConfigOption] = {}
        self._should_load_system_instructions = True

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
        if self.is_active:
            await self.cancel()

        try:
            new_session = await self.connection.new_session(cwd=self._cwd, mcp_servers=self._mcp_servers)
            session_id = new_session.session_id

            # TODO: [2026/03/24 <Huanan>] it will raise "Resource not found" from codex acp. do not know why.
            # issue: https://github.com/zed-industries/codex-acp/issues/203
            # _ = await self.connction.load_session(cwd=self._cwd, session_id=session_id)

            self._session_id = session_id
            self.set_session_options(new_session.config_options)
            self._should_load_system_instructions = True
            return session_id
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            raise

    # MARK: Prompt

    @property
    def is_active(self) -> bool:
        return self._update_queue is not None

    async def load_system_instruction_if_needed(self, instruction: str):
        if not self._should_load_system_instructions:
            return
        self._should_load_system_instructions = False

        session_id = await self.require_session_id()

        prompt: list[AcpContentBlock] = [acp.text_block(instruction)]

        try:
            await self.connection.prompt(prompt=prompt, session_id=session_id)
        except acp.RequestError as e:
            self.logger.error(f"Failed to prompt: {e.to_error_obj()}")
            raise ChatAwareError(f"Failed to prompt: {e.to_error_obj()}")

        await self.connection.cancel(session_id)

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
            except acp.RequestError as e:
                self.logger.error(f"Failed to prompt: {e.to_error_obj()}")
                raise
            finally:
                update_queue.shutdown()

        task = asyncio.create_task(turn_task())
        self.logger.info("Prompting ACP agent...")

        try:
            # INDICATE THE START OF THE PROMPT TURN
            yield message

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
            if response.stop_reason == "end_turn":
                message.status = AgentTurnStatus.completed
            elif response.stop_reason == "cancelled":
                message.status = AgentTurnStatus.cancelled
            else:
                message.status = AgentTurnStatus.failed
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

    async def list_model_opts(self) -> list[AgentModelOption]:
        session_options = self.session_options
        if session_options is None:
            return []

        option = session_options.get(MODEL_CONFIG_ID)
        if option is None:
            return []

        selects = option.root.options

        # TODO: support SessionConfigSelectGroup
        selects = [x for x in selects if isinstance(x, SessionConfigSelectOption)]

        return [AgentModelOption(value=select.value, name=select.name) for select in selects]

    async def set_model(self, value: str) -> bool:
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
        acp_registry: ACPRegistryCache,
        mcp_servers: list[acp.schema.HttpMcpServer | acp.schema.SseMcpServer | acp.schema.McpServerStdio] | None = None,
    ) -> None:
        self._config = config
        self._stack: contextlib.AsyncExitStack | None = None
        self._mcp_servers = mcp_servers
        self._runtimes: dict[str, ACPAgentRuntime] = {}
        self._acp_manager = ACPRegisteryManage(acp_registry)

    async def spawn_acp_runtime(self, assistant: AssistantConfig) -> ACPAgentRuntime:
        assert self._stack is not None

        acp_config = await self.get_acp_config(assistant.agent_id)
        assert acp_config is not None, "acp agent not found"

        id = str(uuid.uuid4())
        runtime = ACPAgentRuntime(id, acp_config, cwd=assistant.work_dir or get_agent_work_dir(assistant.assistant_id), mcp_servers=self._mcp_servers)
        await self._stack.enter_async_context(runtime)
        self._runtimes[id] = runtime

        return runtime

    async def get_acp_config(self, agent_id: str) -> ACPAgentConfig | None:
        acp = await self._acp_manager.get_agent_config(agent_id)
        return acp

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
