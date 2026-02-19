import asyncio
import os
from typing import Any
from tele_acp.telegram import TGClient
import asyncio.subprocess as aio_subprocess

from .types import SharedArgs
from tele_acp.config import load_config
import acp


class ACPClient(acp.Client):
    async def request_permission(
        self, options: list[acp.PermissionOption], session_id: str, tool_call: acp.ToolCallUpdate, **kwargs: Any
    ) -> acp.RequestPermissionResponse:
        raise NotImplementedError("Permission request not implemented")

    async def session_update(
        self,
        session_id: str,
        update: acp.UserMessageChunk
        | acp.AgentMessageChunk
        | acp.AgentThoughtChunk
        | acp.ToolCallStart
        | acp.ToolCallProgress
        | acp.AgentPlanUpdate
        | acp.AvailableCommandsUpdate
        | acp.CurrentModeUpdate
        | acp.ConfigOptionUpdate
        | acp.SessionInfoUpdate
        | acp.UsageUpdate,
        **kwargs: Any,
    ) -> None:
        raise NotImplementedError("Session update not implemented")

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> acp.WriteTextFileResponse | None:
        raise NotImplementedError("Write text file not implemented")

    async def read_text_file(self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any) -> acp.ReadTextFileResponse:
        raise NotImplementedError("Read text file not implemented")

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[acp.EnvVariable] | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> acp.CreateTerminalResponse:
        raise

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> acp.TerminalOutputResponse:
        raise

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> acp.ReleaseTerminalResponse | None:
        raise

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> acp.WaitForTerminalExitResponse:
        raise NotImplementedError("Terminal wait for exit not implemented")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> acp.KillTerminalCommandResponse | None:
        raise NotImplementedError("Terminal kill not implemented")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("External method not implemented")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        raise NotImplementedError("External notification not implemented")

    def on_connect(self, conn: acp.Agent) -> None:
        raise NotImplementedError("External notification not implemented")


async def mainloop(cli_args: SharedArgs) -> bool:
    tg = await TGClient.create(session_name=cli_args.session, config=load_config(config_file=cli_args.config_file))
    async with tg as tg:
        await tg.disconnected

    proc = await asyncio.create_subprocess_exec(
        "kimi acp",
        stdin=aio_subprocess.PIPE,
        stdout=aio_subprocess.PIPE,
    )
    conn = acp.connect_to_agent(ACPClient(), proc.stdin, proc.stdout)
    await conn.initialize(
        protocol_version=acp.PROTOCOL_VERSION,
        client_capabilities=acp.ClientCapabilities(),
        client_info=acp.Implementation(name="example-client", title="Example Client", version="0.1.0"),
    )

    return True
