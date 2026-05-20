from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path

from openai_codex import ApprovalMode, AppServerConfig, AsyncCodex, AsyncThread, AsyncTurnHandle, TextInput
from openai_codex.generated.v2_all import (
    AgentMessageThreadItem,
    CollabAgentToolCallThreadItem,
    CommandExecutionThreadItem,
    DynamicToolCallThreadItem,
    FileChangeThreadItem,
    ItemCompletedNotification,
    McpToolCallThreadItem,
    PlanThreadItem,
    ReasoningThreadItem,
    ThreadItem,
    ThreadTokenUsage,
    ThreadTokenUsageUpdatedNotification,
    TurnCompletedNotification,
    TurnError,
    TurnStatus,
)
from openai_codex.models import NotificationPayload
from susie_core import AgentModelOption, ChatAwareError, ChatMessagePart, ChatMessageTextPart
from susie_core.chat import ChatMessageBlockQuote

from susie.agent.runtime import AgentRuntime, AgentTurnStatus, McpServerHttpSetting
from susie.constant import VERSION


def _convert_mcp_settings_codex_config(mcp_servers: list[McpServerHttpSetting] | None = None) -> tuple[str, ...]:
    if mcp_servers is None:
        return ()

    cfgs: list[str] = []
    for mcp in mcp_servers:
        cfgs.append(f"mcp_servers.{mcp.name}.enable=true")
        cfgs.append(f"mcp_servers.{mcp.name}.url={mcp.url}")
    return tuple(cfgs)


@dataclass(slots=True)
class CodexSDKMessage:
    prompt: list[str] = field(default_factory=list)
    delta: ThreadItem | None = None
    chunks: list[ThreadItem] = field(default_factory=list)
    usage: ThreadTokenUsage | None = None
    error: TurnError | None = None
    status: AgentTurnStatus = AgentTurnStatus.in_progress

    @property
    def text(self) -> str:
        return "".join(item.root.text for item in self.chunks if isinstance(item.root, AgentMessageThreadItem))

    def chat_message_parts(self) -> list[ChatMessagePart]:
        ret: list[ChatMessagePart] = []

        for item in self.chunks:
            chunk = item.root

            match chunk:
                case AgentMessageThreadItem():
                    ret.append(ChatMessageTextPart(chunk.text))

                case ReasoningThreadItem():
                    content = "\n".join((chunk.summary or []) + (chunk.content or []))
                    if content:
                        ret.append(ChatMessageTextPart(content))

                case PlanThreadItem():
                    ret.append(ChatMessageTextPart(chunk.text))

                case CommandExecutionThreadItem():
                    status = chunk.status.value
                    title = chunk.command
                    content = chunk.aggregated_output or ""
                    if chunk.exit_code is not None:
                        content = f"exit_code: {chunk.exit_code}\n{content}".strip()
                    ret.append(ChatMessageBlockQuote(f"[{status}] {title}", content))

                case McpToolCallThreadItem():
                    status = chunk.status.value
                    title = f"{chunk.server}.{chunk.tool}"
                    content = chunk.error.message if chunk.error is not None else str(chunk.result.content if chunk.result is not None else chunk.arguments)
                    ret.append(ChatMessageBlockQuote(f"[{status}] {title}", content))

                case DynamicToolCallThreadItem():
                    status = chunk.status.value
                    title = f"{chunk.namespace}.{chunk.tool}" if chunk.namespace else chunk.tool
                    content = str(chunk.content_items if chunk.content_items is not None else chunk.arguments)
                    ret.append(ChatMessageBlockQuote(f"[{status}] {title}", content))

                case FileChangeThreadItem():
                    status = chunk.status.value
                    content = "\n".join(f"{change.kind.root.type}: {change.path}" for change in chunk.changes)
                    ret.append(ChatMessageBlockQuote(f"[{status}] file changes", content))

                case CollabAgentToolCallThreadItem():
                    status = chunk.status.value
                    content = chunk.prompt or ""
                    ret.append(ChatMessageBlockQuote(f"[{status}] {chunk.tool.value}", content))

                case _:
                    pass

        return ret


class CodexSDKRuntime(AgentRuntime):
    def __init__(
        self,
        *,
        cwd: str | Path,
        mcp_servers: list[McpServerHttpSetting] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.cwd = str(Path(cwd).resolve())
        self.logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        config: tuple[str, ...] = ()
        mcp_servers_cfg = _convert_mcp_settings_codex_config(mcp_servers)
        config += mcp_servers_cfg

        self._codex = AsyncCodex(
            AppServerConfig(
                config_overrides=config,
                cwd=self.cwd,
                client_name="tele-acp",
                client_title="tele-acp",
                client_version=VERSION,
            )
        )
        self._thread: AsyncThread | None = None
        self._thread_id: str | None = None
        self._active_turn: AsyncTurnHandle | None = None
        self._should_load_system_instructions = True
        self._model: str | None = None

    async def __aenter__(self) -> CodexSDKRuntime:
        await self._codex.__aenter__()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        await self._codex.__aexit__(exc_type, exc_val, exc_tb)

    @property
    def session_id(self) -> str | None:
        return self._thread_id

    @property
    def is_active(self) -> bool:
        return self._active_turn is not None

    async def _new_session_if_needed(self, instruction: str | None) -> AsyncThread:
        if thread := self._thread:
            return thread

        thread = await self._new_session(instruction)
        return thread

    async def _new_session(self, instruction: str | None) -> AsyncThread:
        if self.is_active:
            await self.cancel()

        thread = await self._codex.thread_start(
            base_instructions=instruction,
            cwd=self.cwd,
            model=self._model,
            approval_mode=ApprovalMode.auto_review,
        )

        self._thread = thread
        self._thread_id = thread.id
        self._active_turn = None
        return thread

    async def new_session(self, instruction: str | None) -> str:
        thread = await self._new_session_if_needed(instruction)
        return thread.id

    async def model(self) -> str | None:
        if self._model is not None:
            return self._model

        models = await self._codex.models()
        default = next((model for model in models.data if model.is_default), None)
        if default is None:
            return None
        return default.model

    async def list_model_opts(self) -> list[AgentModelOption]:
        models = await self._codex.models()
        return [AgentModelOption(value=model.model, name=model.display_name) for model in models.data if not model.hidden]

    async def set_model(self, value: str) -> bool:
        models = await self._codex.models(include_hidden=True)
        selected = next((model for model in models.data if model.model == value or model.id == value), None)
        if selected is None:
            return False

        self._model = selected.model
        return True

    async def prompt(self, parts: list[str]) -> AsyncGenerator[CodexSDKMessage, None]:
        thread = self._thread
        if thread is None:
            raise ChatAwareError("Please create session first")

        input_text = "\n\n".join(parts)

        if active_turn := self._active_turn:
            await active_turn.steer(TextInput(input_text))
            return

        message = CodexSDKMessage(prompt=parts)

        turn = await thread.turn(
            TextInput(input_text),
            approval_mode=ApprovalMode.auto_review,
            cwd=self.cwd,
            model=self._model,
        )
        self._active_turn = turn
        self.logger.info(f"thread {thread.id} started")

        try:
            yield message
            async for event in turn.stream():
                payload: NotificationPayload = event.payload

                self.logger.info(f"payload: {payload}")

                match payload:
                    case ItemCompletedNotification():
                        message.delta = payload.item
                        message.chunks.append(payload.item)
                        yield message

                    case ThreadTokenUsageUpdatedNotification():
                        message.usage = payload.token_usage
                        # yield message

                    case TurnCompletedNotification():
                        match payload.turn.status:
                            case TurnStatus.completed:
                                message.status = AgentTurnStatus.completed
                            case TurnStatus.interrupted:
                                message.status = AgentTurnStatus.cancelled
                            case TurnStatus.failed:
                                message.status = AgentTurnStatus.failed
                            case TurnStatus.in_progress:
                                message.status = AgentTurnStatus.in_progress
                        message.error = payload.turn.error
                        # yield message
                    case _:
                        pass

            yield message
            self.logger.info(f"thread {thread.id} completed")
        finally:
            self._active_turn = None

    async def cancel(self) -> None:
        turn = self._active_turn
        if turn is None:
            return
        await turn.interrupt()
