import asyncio
import logging

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from tele_acp.acp import ACPAgentConfig
from tele_acp.types.error import unreachable
import telethon
from telethon import events
from telethon.custom import Message

from tele_acp.mcp import MCP
from tele_acp.telegram import TGClient
from tele_acp.types import peer_hash_into_str
from tele_acp.types.config import Config
from tele_acp.agent import Agent, AgentThread


class APP:
    def __init__(self, config: Config) -> None:
        from tele_acp.mcp import mcp_server

        # Telegram Client
        tele_client = TGClient.create(session_name=cli_args.session, config=config)
        tele_client.add_event_handler(self.on_tele_client_receive_message, events.NewMessage())

        # MCP Server
        mcp_server.set_tg_client(tele_client)

        # Initial Variable
        self.logger = logging.getLogger(__name__)

        self._tele_client = tele_client
        self._mcp_server: MCP = mcp_server

        self._inbound_dialog_dict_lock = asyncio.Lock()
        self._inbound_dialog_dict: dict[str, MemoryObjectSendStream[Message]] = {}

    async def run_until_finish(self):
        # start tg client
        async with self._tele_client as tele_client:

            async def _wait_for_disconnect() -> None:
                await tele_client.disconnected

            async with asyncio.TaskGroup() as group:
                group.create_task(self._mcp_server.run_streamable_http_async())
                group.create_task(_wait_for_disconnect())

            self.logger.info("Finished")

    async def on_tele_client_receive_message(self, event: events.NewMessage.Event):
        message: Message = event.message
        self.logger.info(f"New message received {message}")

        if message.out:
            return

        # User Only
        if not isinstance(message.peer_id, telethon.types.PeerUser):
            return

        dialog_id = peer_hash_into_str(message.peer_id)
        await self.ensure_running_agent_for_dialog(dialog_id)

        outbound_writer = await self._get_dialog_message_inbound_writer(dialog_id)
        await outbound_writer.send(message)

    async def _get_dialog_message_inbound_writer(self, dialog_id: str) -> MemoryObjectSendStream[Message]:
        async with self._inbound_dialog_dict_lock:
            inbound = self._inbound_dialog_dict[dialog_id]
            if inbound is None:
                unreachable("MUST call ensure_running_agent_for_dialog before get inbound")
            return inbound

    async def get_agent_for_dialog(self, dialog_id: str) -> Agent:
        _ = dialog_id
        return Agent(ACPAgentConfig(id="kimi", name="Kimi CLI", acp_path="kimi", acp_args=["acp"]))

    async def ensure_running_agent_for_dialog(self, dialog_id):
        agent = self.get_agent_for_dialog(dialog_id)

        read_stream_writer, read_stream = anyio.create_memory_object_stream(0)

        inbound: MemoryObjectSendStream[Message]
        inbound_reader: MemoryObjectReceiveStream[Message]

        outbound_writer: MemoryObjectSendStream[str]
        outbound: MemoryObjectReceiveStream[str]

        inbound, inbound_reader = anyio.create_memory_object_stream(0)
        outbound_writer, outbound = anyio.create_memory_object_stream(0)

        # async def stdin_reader():
        #     try:
        #         async with read_stream_writer:
        #             async for line in stdin:
        #                 try:
        #                     message = types.JSONRPCMessage.model_validate_json(line)
        #                 except Exception as exc:  # pragma: no cover
        #                     await read_stream_writer.send(exc)
        #                     continue

        #                 session_message = SessionMessage(message)
        #                 await read_stream_writer.send(session_message)
        #     except anyio.ClosedResourceError:  # pragma: no cover
        #         await anyio.lowlevel.checkpoint()
