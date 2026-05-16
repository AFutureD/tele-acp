import logging
from typing import Any, Awaitable, Callable, TypeAlias

import acp
from acp import schema
from pydantic.dataclasses import dataclass
from susie_core import unreachable

# curl https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json
# https://github.com/agentclientprotocol/registry/blob/main/agent.schema.json


@dataclass
class ACPAgentConfig:
    id: str
    name: str
    acp_path: str
    acp_args: list[str]


ACPUpdateChunk: TypeAlias = (
    schema.UserMessageChunk
    | schema.AgentMessageChunk
    | schema.AgentThoughtChunk
    | schema.ToolCallStart
    | schema.ToolCallProgress
    | schema.AgentPlanUpdate
    | schema.AvailableCommandsUpdate
    | schema.CurrentModeUpdate
    | schema.ConfigOptionUpdate
    | schema.SessionInfoUpdate
    | schema.UsageUpdate
)


class ACPClient(acp.Client):
    def __init__(
        self,
        on_session_update: Callable[[str, ACPUpdateChunk], Awaitable[None]] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._on_session_update = on_session_update
        self.logger = logger or logging.getLogger(__name__)

    def on_connect(self, conn: acp.Agent) -> None:
        self.logger.info("Connected to ACP agent: %s", conn)

    async def session_update(self, session_id: str, update: ACPUpdateChunk, **kwargs: Any) -> None:
        _ = kwargs

        handler = self._on_session_update
        if handler is None:
            return

        match update:
            case schema.UserMessageChunk():
                await handler(session_id, update)
            case schema.AgentMessageChunk():
                await handler(session_id, update)
            case schema.AgentThoughtChunk():
                await handler(session_id, update)
            case schema.ToolCallStart():
                await handler(session_id, update)
            case schema.ToolCallProgress():
                await handler(session_id, update)
            case schema.AgentPlanUpdate():
                await handler(session_id, update)
            case schema.AvailableCommandsUpdate():
                await handler(session_id, update)
            case schema.CurrentModeUpdate():
                await handler(session_id, update)
            case schema.ConfigOptionUpdate():
                await handler(session_id, update)
            case schema.SessionInfoUpdate():
                await handler(session_id, update)
            case schema.UsageUpdate():
                await handler(session_id, update)

    async def request_permission(
        self, options: list[schema.PermissionOption], session_id: str, tool_call: schema.ToolCallUpdate, **kwargs: Any
    ) -> schema.RequestPermissionResponse:
        from acp.schema import AllowedOutcome

        options = [o for o in options if o.kind == "allow_always" or o.kind == "allow_once"]

        if len(options) < 1:
            unreachable("At least one option is required")

        return schema.RequestPermissionResponse(outcome=AllowedOutcome(outcome="selected", option_id=options[0].option_id))

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> schema.WriteTextFileResponse | None:
        unreachable("Write text file not implemented")

    async def read_text_file(self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any) -> schema.ReadTextFileResponse:
        unreachable("Read text file not implemented")

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[schema.EnvVariable] | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> schema.CreateTerminalResponse:
        unreachable("Create terminal not implemented")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> schema.TerminalOutputResponse:
        unreachable("Terminal output not implemented")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> schema.ReleaseTerminalResponse | None:
        unreachable("Terminal release not implemented")

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> schema.WaitForTerminalExitResponse:
        unreachable("Terminal wait for exit not implemented")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> schema.KillTerminalCommandResponse | None:
        unreachable("Terminal kill not implemented")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("External method not implemented")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        raise NotImplementedError("External notification not implemented")
