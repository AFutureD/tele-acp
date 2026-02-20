import asyncio
import logging
from typing import Any

import acp
from acp import schema

from tele_acp.types import unreachable


class ACPClient(acp.Client):
    def __init__(self, outbound_queue: asyncio.Queue[str | None], logger: logging.Logger) -> None:
        self._outbound_queue = outbound_queue
        self._logger = logger

    def on_connect(self, conn: acp.Agent) -> None:
        self._logger.info("Connected to ACP agent: %s", conn)

    async def session_update(
        self,
        session_id: str,
        update: schema.UserMessageChunk
        | schema.AgentMessageChunk
        | schema.AgentThoughtChunk
        | schema.ToolCallStart
        | schema.ToolCallProgress
        | schema.AgentPlanUpdate
        | schema.AvailableCommandsUpdate
        | schema.CurrentModeUpdate
        | schema.ConfigOptionUpdate
        | schema.SessionInfoUpdate
        | schema.UsageUpdate,
        **kwargs: Any,
    ) -> None:
        self._logger.info("session_update")
        self._logger.info(update)

        _ = kwargs

        match update:
            case schema.UserMessageChunk():
                await self.handle_user_message_chunk(session_id, update)
            case schema.AgentMessageChunk():
                await self.handle_agent_message_chunk(session_id, update)
            case schema.AgentThoughtChunk():
                await self.handle_agent_message_chunk(session_id, update)
            case schema.ToolCallStart():
                await self.handle_tool_call_start(session_id, update)
            case schema.ToolCallProgress():
                await self.handle_tool_call_progress(session_id, update)
            case schema.AgentPlanUpdate():
                await self.handle_agent_plan_update(session_id, update)
            case schema.AvailableCommandsUpdate():
                await self.handle_available_commands_update(session_id, update)
            case schema.CurrentModeUpdate():
                await self.handle_current_mode_update(session_id, update)
            case schema.ConfigOptionUpdate():
                await self.handle_config_option_update(session_id, update)
            case schema.SessionInfoUpdate():
                await self.handle_session_info_update(session_id, update)
            case schema.UsageUpdate():
                await self.handle_usage_update(session_id, update)

    async def request_permission(
        self, options: list[schema.PermissionOption], session_id: str, tool_call: schema.ToolCallUpdate, **kwargs: Any
    ) -> schema.RequestPermissionResponse:
        raise NotImplementedError("Permission request not implemented")

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
        unreachable("External method not implemented")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        raise NotImplementedError("External notification not implemented")

    async def handle_user_message_chunk(self, session_id: str, update: schema.UserMessageChunk) -> None:
        _ = session_id, update

    async def handle_agent_message_chunk(self, session_id: str, update: schema.AgentMessageChunk | schema.AgentThoughtChunk) -> None:
        _ = session_id, update

        if isinstance(update, schema.AgentMessageChunk):
            content = update.content

            match content:
                case schema.TextContentBlock():
                    await self._outbound_queue.put(content.text)
                case schema.ImageContentBlock():
                    pass
                case schema.AudioContentBlock():
                    pass
                case schema.ResourceContentBlock():
                    pass
                case schema.EmbeddedResourceContentBlock():
                    pass

    async def handle_tool_call_start(self, session_id: str, update: schema.ToolCallStart) -> None:
        _ = session_id, update

    async def handle_tool_call_progress(self, session_id: str, update: schema.ToolCallProgress) -> None:
        _ = session_id, update

    async def handle_agent_plan_update(self, session_id: str, update: schema.AgentPlanUpdate) -> None:
        _ = session_id, update

    async def handle_available_commands_update(self, session_id: str, update: schema.AvailableCommandsUpdate) -> None:
        _ = session_id, update

    async def handle_current_mode_update(self, session_id: str, update: schema.CurrentModeUpdate) -> None:
        _ = session_id, update

    async def handle_config_option_update(self, session_id: str, update: schema.ConfigOptionUpdate) -> None:
        _ = session_id, update

    async def handle_session_info_update(self, session_id: str, update: schema.SessionInfoUpdate) -> None:
        _ = session_id, update

    async def handle_usage_update(self, session_id: str, update: schema.UsageUpdate) -> None:
        _ = session_id, update
