import asyncio
import contextlib
import logging
from typing import AsyncIterator, TypeAlias

import telethon
from acp.schema import HttpMcpServer
from telethon.custom import Message

from tele_acp.acp import ACPAgentConfig
from tele_acp.agent.thread import AgentBaseThread
from tele_acp.telegram import TGActionProvider, TGClient
from tele_acp.types import AcpMessage, AgentConfig, Config, OutBoundMessage, peer_hash_into_str

DialogID: TypeAlias = str


class Dialog(AgentBaseThread):
    def __init__(
        self,
        dialog_id: str,
        peer: telethon.types.TypePeer,
        agent_config: AgentConfig,
        acp_config: ACPAgentConfig,
        tele_action: TGActionProvider,
    ):
        logger = logging.getLogger(__name__)

        self.agent_config = agent_config
        self.acp_config = acp_config

        self.peer = peer
        self.dialog_id = dialog_id
        self._tele_action = tele_action

        mcp_server = HttpMcpServer(name="telegram_mcp_server", url="http://127.0.0.1:9998/mcp", headers=[], type="http")
        super().__init__(
            agent_config=agent_config,
            acp_config=acp_config,
            mcp_servers=[mcp_server],
            logger=logger,
        )

    @contextlib.asynccontextmanager
    async def turn_context(self) -> AsyncIterator[None]:
        async with self._tele_action.with_action(self.peer, "typing"):
            yield

    async def handle_message(self, message: Message):
        await self.handle_inbound_message(message)

    async def handle_outbound_message(self, message: OutBoundMessage):
        peer = self.peer
        dialog_id = self.dialog_id

        match message:
            case str():
                await self._tele_action.send_message(peer, message)
            case AcpMessage() if message.stopReason is not None and message.stopReason != "cancelled":
                text = message.markdown()
                await self._tele_action.send_message(peer, text)
                self.logger.info(f"Dialog {dialog_id} stopped: {message.stopReason}")

    def build_runtime_messages(self, content: str) -> list[str]:
        prompt = (
            # Context Info
            f"<CONTEXT>\n"
            f"This is a message from Telegram.\n"
            f"Dialog ID: {self.dialog_id}\n"
            f"Peer ID: {self.peer.to_json()}\n"
            f"</CONTEXT>\n"
            f"\n"
            # IMPORTANT
            f"<IMPORTANT>\n"
            f"always using `Telegram MCP` send_message method when you have some message needs replay to this message.\n"
            f"</IMPORTANT>\n"
            f"\n"
            # User Input
            f"User Content:\n"
            f"{content}"
        )

        return [prompt]


class DialogManager:
    def __init__(self, config: Config, tele_client: TGClient):
        self.logger = logging.getLogger(__name__)

        self._dialogs_lock = asyncio.Lock()
        self.dialogs: dict[DialogID, Dialog] = {}

        self._task_stack: contextlib.AsyncExitStack | None = None

        self._run_lock = asyncio.Lock()
        self._has_started = False

        self._tele_client = tele_client
        self._config = config

        self._agents: list[ACPAgentConfig] = [
            ACPAgentConfig(id="codex", name="Codex", acp_path="codex-acp", acp_args=[]),
            ACPAgentConfig(id="kimi", name="Kimi CLI", acp_path="kimi", acp_args=["acp"]),
        ]

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        async with self._run_lock:
            if self._has_started:
                raise RuntimeError()
            self._has_started = True

        async with contextlib.AsyncExitStack() as stack:
            self._task_stack = stack
            self.logger.info("Started")

            try:
                yield  # Let the application run
            finally:
                self.logger.info("Finished")
                self._task_group = None
                self.dialogs.clear()

    async def get_dialog(self, peer: telethon.types.TypePeer) -> Dialog | None:
        dialog_id = peer_hash_into_str(peer)
        if dialog_id in self.dialogs:
            return self.dialogs[dialog_id]

        async with self._run_lock:
            acp_config = await self.get_acp_for_dialog(dialog_id)
            agent_config = await self.get_agent_config_for_dialog(dialog_id)

            dialog = Dialog(dialog_id=dialog_id, peer=peer, agent_config=agent_config, acp_config=acp_config, tele_action=self._tele_client)
            self.dialogs[dialog_id] = dialog

            assert self._task_stack is not None
            await self._task_stack.enter_async_context(dialog.run_until_finish())
            return dialog

    async def handle_message(self, message: Message):
        peer = message.peer_id

        dialog = await self.get_dialog(peer)
        if not dialog:
            return

        await dialog.handle_message(message)

    async def get_acp_for_dialog(self, dialog_id: str) -> ACPAgentConfig:
        _ = dialog_id
        return self._agents[0]

    async def get_agent_config_for_dialog(self, dialog_id: str) -> AgentConfig:
        _ = dialog_id
        return self._config.agents[0]
