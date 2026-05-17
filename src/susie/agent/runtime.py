from __future__ import annotations

from enum import Enum
from typing import AsyncIterator, Protocol

from susie_core import AgentModelOption, ChatMessagePart


class AgentTurnStatus(Enum):
    in_progress = "in_progress"
    cancelled = "cancelled"
    completed = "completed"
    failed = "failed"


class AgentMessage(Protocol):
    status: AgentTurnStatus

    def chat_message_parts(self) -> list[ChatMessagePart]: ...


class AgentRuntime(Protocol):
    async def new_session(self) -> str: ...
    async def load_system_instruction_if_needed(self, instruction: str) -> None: ...
    async def list_model_opts(self) -> list[AgentModelOption]: ...
    async def model(self) -> str | None: ...
    async def set_model(self, value: str) -> bool: ...
    async def cancel(self) -> None: ...
    def prompt(self, parts: list[str]) -> AsyncIterator[AgentMessage]: ...
