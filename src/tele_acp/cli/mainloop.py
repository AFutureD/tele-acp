import asyncio
import logging
import os
from typing import Any
from tele_acp.telegram import TGClient

from telethon import events
import telethon
from telethon.custom import Message

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
        raise NotImplementedError("Terminal output not implemented")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> acp.ReleaseTerminalResponse | None:
        raise NotImplementedError("Terminal release not implemented")

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


class AgentConnection:
    def __init__(self, peer: telethon.types.TypePeer) -> None:
        self.peer = peer
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run())
        self._buffer_lock = asyncio.Lock()
        self._buffer: list[Message] = []
        self.logger = logging.getLogger(__name__ + str(self.peer))
        self.response_queue = asyncio.Queue[str]()

    async def _run(self) -> None:
        async with acp.spawn_agent_process(ACPClient(), "kimi", "acp") as (conn, proc):
            _ = proc
            await conn.initialize(
                protocol_version=acp.PROTOCOL_VERSION,
                client_capabilities=acp.ClientCapabilities(),
                client_info=acp.Implementation(name="example-client", title="Example Client", version="0.1.0"),
            )
            session = await conn.new_session(cwd=os.getcwd())
            session_id = session.session_id

            while True:
                async with self._buffer_lock:
                    buffer = self._buffer
                    self._buffer = []
                self.logger.info(buffer)

                # await conn.prompt(prompt=[acp.text_block("")], session_id=session_id)

    async def _forward(self) -> None:
        while True:
            msg = await self.response_queue.get()
            print("!!!!!!" + msg)

    async def handle(self, message: Message):
        async with self._buffer_lock:
            self._buffer.append(message)


async def mainloop(cli_args: SharedArgs) -> bool:
    logger = logging.getLogger(__name__)

    lock = asyncio.Lock()
    conn_dict: dict[telethon.types.TypePeer, AgentConnection] = {}

    async def on_message(event: events.NewMessage.Event):
        _ = event
        message: Message = event.message
        logger.info(f"New message received {message}")

        if not isinstance(message.peer_id, telethon.types.PeerUser):
            return

        async with lock:
            conn = conn_dict.get(message.peer_id)
            if not conn:
                conn = AgentConnection(message.peer_id)
                conn_dict[message.peer_id] = conn

        await conn.handle(message)

    tg = await TGClient.create(session_name=cli_args.session, config=load_config(config_file=cli_args.config_file))
    tg.add_event_handler(on_message, events.NewMessage())

    async with tg as tg:
        await tg.disconnected

    return True
