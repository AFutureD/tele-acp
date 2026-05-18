import asyncio
import contextlib
import logging
from pathlib import Path
from typing import AsyncIterator

import acp
from acp import NewSessionResponse
from acp.schema import SessionConfigOption, SessionConfigSelectOption
from susie_core import AgentModelOption, ChatAwareError

from susie.agent.runtime import AgentRuntime, AgentTurnStatus
from susie.shared import get_app_user_config_dir

from .client import ACPAgentConfig, ACPUpdateChunk
from .connection import ACPAgentConnection
from .message import AcpContentBlock, AcpMessage


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
        self._session: NewSessionResponse | None = None
        self.session_options: dict[str, SessionConfigOption] = {}
        self._should_load_system_instructions = True

    @property
    def is_active(self) -> bool:
        return self._update_queue is not None

    # MARK: Session

    @property
    def session_id(self) -> str | None:
        if session := self._session:
            return session.session_id
        return None

    async def _new_session_if_needed(self, instruction: str | None) -> NewSessionResponse:
        if session := self._session:
            return session

        session = await self._new_session(instruction)
        return session

    async def _new_session(self, instruction: str | None) -> NewSessionResponse:
        if self.is_active:
            await self.cancel()

        try:
            new_session = await self.connection.new_session(cwd=self._cwd, mcp_servers=self._mcp_servers)

            # TODO: [2026/03/24 <Huanan>] it will raise "Resource not found" from codex acp. do not know why.
            # issue: https://github.com/zed-industries/codex-acp/issues/203
            # _ = await self.connction.load_session(cwd=self._cwd, session_id=session_id)

            self._session_id = new_session.session_id
            self.set_session_options(new_session.config_options)

            if instruction:
                prompt: list[AcpContentBlock] = [acp.text_block(instruction)]
                await self.connection.prompt(prompt=prompt, session_id=new_session.session_id)

            return new_session
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            raise

    async def new_session(self, instruction: str | None) -> str:
        session = await self._new_session_if_needed(instruction)
        return session.session_id

    # MARK: Prompt

    async def load_system_instruction_if_needed(self, instruction: str):
        session = await self._new_session_if_needed(instruction)

        prompt: list[AcpContentBlock] = [acp.text_block(instruction)]

        try:
            await self.connection.prompt(prompt=prompt, session_id=session.session_id)
        except acp.RequestError as e:
            self.logger.error(f"Failed to prompt: {e.to_error_obj()}")
            raise ChatAwareError(f"Failed to prompt: {e.to_error_obj()}")

        await self.connection.cancel(session.session_id)

    async def prompt(self, parts: list[str]) -> AsyncIterator[AcpMessage]:
        session = self._session
        if session is None:
            raise ChatAwareError("Please create session first")

        prompt: list[AcpContentBlock] = list(map(lambda m: acp.text_block(m), parts))

        message = AcpMessage(prompt=prompt, model=None, usage=None)

        update_queue = asyncio.Queue[ACPUpdateChunk]()
        self._update_queue = update_queue

        async def turn_task() -> acp.PromptResponse:
            try:
                ret = await self.connection.prompt(prompt=prompt, session_id=session.session_id)
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
