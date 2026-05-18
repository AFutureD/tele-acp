from __future__ import annotations

from enum import Enum
from typing import AsyncIterator, Protocol

from pydantic import BaseModel, Field
from susie_core import AgentModelOption, ChatMessagePart


class McpServerHttpSetting(BaseModel):
    # HTTP headers to set when making requests to the MCP server.
    headers: dict[str, str] = {}
    # Human-readable name identifying this MCP server.
    name: str = Field(description="Human-readable name identifying this MCP server.")
    # URL to the MCP server.
    url: str = Field(description="URL to the MCP server.")


class AgentTurnStatus(Enum):
    in_progress = "in_progress"
    cancelled = "cancelled"
    completed = "completed"
    failed = "failed"


class AgentMessage(Protocol):
    status: AgentTurnStatus

    def chat_message_parts(self) -> list[ChatMessagePart]: ...


class AgentRuntime(Protocol):
    async def new_session(self, instruction: str | None) -> str: ...
    async def list_model_opts(self) -> list[AgentModelOption]: ...
    async def model(self) -> str | None: ...
    async def set_model(self, value: str) -> bool: ...
    async def cancel(self) -> None: ...
    def prompt(self, parts: list[str]) -> AsyncIterator[AgentMessage]: ...
