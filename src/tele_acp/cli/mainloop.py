import asyncio
import logging
import os
from typing import Any
from tele_acp.telegram import TGClient

from tele_acp.types import peer_hash_into_str
from telethon import events
import telethon
from telethon.custom import Message

from .types import SharedArgs
from tele_acp.config import load_config
import acp
from acp import schema


class ACPClient(acp.Client):
    def __init__(self, response_queue: asyncio.Queue[str | None], logger: logging.Logger) -> None:
        self._response_queue = response_queue
        self._logger = logger

    async def request_permission(
        self, options: list[schema.PermissionOption], session_id: str, tool_call: schema.ToolCallUpdate, **kwargs: Any
    ) -> schema.RequestPermissionResponse:
        raise NotImplementedError("Permission request not implemented")

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

        _ = session_id, kwargs
        if not isinstance(update, schema.AgentMessageChunk):
            return
        if not isinstance(update.content, schema.TextContentBlock):
            return

        text = update.content.text
        await self._response_queue.put(text)

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> schema.WriteTextFileResponse | None:
        raise NotImplementedError("Write text file not implemented")

    async def read_text_file(self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any) -> schema.ReadTextFileResponse:
        raise NotImplementedError("Read text file not implemented")

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
        raise NotImplementedError("Create terminal not implemented")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> schema.TerminalOutputResponse:
        raise NotImplementedError("Terminal output not implemented")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> schema.ReleaseTerminalResponse | None:
        raise NotImplementedError("Terminal release not implemented")

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> schema.WaitForTerminalExitResponse:
        raise NotImplementedError("Terminal wait for exit not implemented")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> schema.KillTerminalCommandResponse | None:
        raise NotImplementedError("Terminal kill not implemented")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("External method not implemented")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        raise NotImplementedError("External notification not implemented")

    def on_connect(self, conn: acp.Agent) -> None:
        self._logger.info("Connected to ACP agent: %s", conn)


class AgentConnection:
    def __init__(self, peer: telethon.types.TypePeer, tg: TGClient) -> None:
        self.peer = peer
        self._tg = tg
        self._inbound_queue = asyncio.Queue[str]()
        self.logger = logging.getLogger(__name__ + str(self.peer))
        self.response_queue = asyncio.Queue[str | None]()

        loop = asyncio.get_running_loop()
        self._inbound_task = loop.create_task(self._handle_inbound())
        self._outbound_task = loop.create_task(self._handle_outbound())

    async def _handle_inbound(self) -> None:
        try:
            async with acp.spawn_agent_process(ACPClient(self.response_queue, self.logger), "/opt/homebrew/bin/codex-acp") as (conn, proc):
                # DEBUG
                conn._conn.add_observer(lambda x: self.logger.debug(f"RAW JSONC: {x}"))

                _ = proc
                await conn.initialize(
                    protocol_version=acp.PROTOCOL_VERSION,
                    client_capabilities=schema.ClientCapabilities(
                        fs=schema.FileSystemCapability(read_text_file=False, write_text_file=False),
                        terminal=False,
                    ),
                    client_info=schema.Implementation(name="tele-acp", title="tele-acp", version="2026.1.0"),
                )
                session = await conn.new_session(cwd=os.getcwd())
                session_id = session.session_id

                # IMPORTANT: inbound loop
                while True:
                    prompt_text = await self._inbound_queue.get()
                    try:
                        await conn.prompt(prompt=[acp.text_block(prompt_text)], session_id=session_id)
                    except Exception:
                        self.logger.exception("Failed to prompt ACP agent")
                    finally:
                        # Indicate a prompt turn has end.
                        await self.response_queue.put(None)

        except Exception as e:
            self.logger.exception(f"Failed to handle inbound message: {e}")

    async def _handle_outbound(self) -> None:

        sending_message: telethon.types.TypeMessage | None = None
        sending_content: str = ""  # we can't reuse sending_message as it will strip empty charactors.

        # IMPORTANT: outbound loop
        while True:
            msg = await self.response_queue.get()

            if not msg:
                # IMPORTANT: when received a none from queue it meams a prompt turn has end.
                sending_message = None
                sending_content = ""
                continue

            sending_content += msg

            try:
                if sending_message:
                    if sending_content.strip() == sending_message.message:
                        # telegram requirement. when edit message, content should not be the same.
                        continue

                    sending_message = await self._tg.edit_message(self.peer, sending_message.id, sending_content)
                else:
                    sending_message = await self._tg.send_message(self.peer, sending_content)

            except Exception:
                self.logger.exception("Failed to forward ACP response to telegram")

    async def handle(self, message: Message) -> None:
        text = (message.raw_text or "").strip()
        if not text:
            return
        await self._inbound_queue.put(text)


async def mainloop(cli_args: SharedArgs) -> bool:
    logger = logging.getLogger(__name__)

    lock = asyncio.Lock()
    conn_dict: dict[str, AgentConnection] = {}

    async def on_message(event: events.NewMessage.Event):
        _ = event
        message: Message = event.message
        logger.info(f"New message received {message}")

        if not isinstance(message.peer_id, telethon.types.PeerUser):
            return
        if message.out:
            return

        async with lock:
            conn = conn_dict.get(peer_hash_into_str(message.peer_id))
            if not conn:
                conn = AgentConnection(message.peer_id, tg)
                conn_dict[peer_hash_into_str(message.peer_id)] = conn

        await conn.handle(message)

    tg = await TGClient.create(session_name=cli_args.session, config=load_config(config_file=cli_args.config_file))
    tg.add_event_handler(on_message, events.NewMessage())

    async with tg as tg:
        await tg.disconnected

    return True
