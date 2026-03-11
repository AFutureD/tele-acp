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
from tele_acp.types import AcpMessage, AgentConfig, Config, OutBoundMessage, TelegramBotChannel, TelegramUserChannel, peer_hash_into_str

from .channels import InboundMessage

ChannelID: TypeAlias = str
DialogID: TypeAlias = str
DialogKey: TypeAlias = tuple[ChannelID, DialogID]
SUPPRESS_DIALOG_SECONDS = 120.0


class Dialog(AgentBaseThread):
    def __init__(
        self,
        dialog_key: DialogKey,
        peer: telethon.types.TypePeer,
        agent_config: AgentConfig,
        acp_config: ACPAgentConfig,
        tele_action: TGActionProvider,
        mcp_server_url: str,
    ):
        logger = logging.getLogger(__name__)

        self.dialog_key = dialog_key
        self.agent_config = agent_config
        self.acp_config = acp_config

        self.peer = peer
        self._tele_action = tele_action
        self._ignore_messages_until: float | None = None

        mcp_server = HttpMcpServer(
            name="telegram_mcp_server",
            url=mcp_server_url,
            headers=[],
            type="http",
        )

        super().__init__(
            agent_config=agent_config,
            acp_config=acp_config,
            mcp_servers=[mcp_server],
            logger=logger,
        )

    @property
    def channel_id(self) -> ChannelID:
        return self.dialog_key[0]

    @property
    def dialog_id(self) -> str:
        return self.dialog_key[1]

    @property
    def ignored_until(self) -> float | None:
        if self._ignore_messages_until is None:
            return None

        now = asyncio.get_running_loop().time()
        if self._ignore_messages_until <= now:
            self._ignore_messages_until = None
            return None

        return self._ignore_messages_until

    @property
    def is_ignoring_messages(self) -> bool:
        return self.ignored_until is not None

    @contextlib.asynccontextmanager
    async def turn_context(self) -> AsyncIterator[None]:
        async with self._tele_action.with_action(self.peer, "typing"):
            yield

    async def handle_message(self, message: Message):
        if message.out:
            self.ignore_responses_for(SUPPRESS_DIALOG_SECONDS)
            return

        if self.is_ignoring_messages:
            return

        await self.handle_inbound_message(message)

    def ignore_responses_for(self, seconds: float) -> None:
        now = asyncio.get_running_loop().time()
        self._ignore_messages_until = now + seconds

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
            f"Channel ID: {self.channel_id}\n"
            f"Dialog ID: {self.dialog_id}\n"
            f"Peer ID: {self.peer.to_json()}\n"
            f"</CONTEXT>\n"
            f"\n"
            # IMPORTANT
            f"<IMPORTANT>\n"
            f"always using `Telegram MCP` tools when you need to operate on Telegram.\n"
            f"always pass `channel={self.channel_id}` to every `Telegram MCP` tool call.\n"
            f"If you want to reply to the message, always call `send_message`, and you may call it multiple times.\n"
            f"</IMPORTANT>\n"
            f"\n"
            # User Input
            f"User Content:\n"
            f"{content}"
        )

        return [prompt]


class DialogManager:
    def __init__(self, config: Config, *, mcp_server_url: str):
        self.logger = logging.getLogger(__name__)

        self._dialogs_lock = asyncio.Lock()
        self.dialogs: dict[DialogKey, Dialog] = {}

        self._task_stack: contextlib.AsyncExitStack | None = None

        self._run_lock = asyncio.Lock()
        self._has_started = False

        self._config = config
        self._mcp_server_url = mcp_server_url
        self._channels_by_id: dict[str, TelegramUserChannel | TelegramBotChannel] = {channel.id: channel for channel in self._config.channels}

        # hard-coded agents used during development
        self._acp_agents: dict[str, ACPAgentConfig] = {
            agent.id: agent
            for agent in [
                ACPAgentConfig("codex", "Codex", "codex-acp", []),
                ACPAgentConfig("kimi", "Kimi CLI", "kimi", ["acp"]),
            ]
        }
        self._agents_by_id = {agent.id: agent for agent in self._config.agents}

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
                self._task_stack = None
                self.dialogs.clear()

    async def get_dialog(
        self,
        channel_id: str,
        peer: telethon.types.TypePeer,
        tele_action: TGActionProvider,
    ) -> Dialog | None:
        dialog_id = peer_hash_into_str(peer)
        dialog_key = (channel_id, dialog_id)

        if dialog_key in self.dialogs:
            return self.dialogs[dialog_key]

        async with self._dialogs_lock:
            if dialog_key in self.dialogs:
                return self.dialogs[dialog_key]

            acp_config = await self.get_acp_for_dialog(dialog_key)
            agent_config = await self.get_agent_config_for_dialog(dialog_key)

            dialog = Dialog(
                dialog_key=dialog_key,
                peer=peer,
                agent_config=agent_config,
                acp_config=acp_config,
                tele_action=tele_action,
                mcp_server_url=self._mcp_server_url,
            )
            self.dialogs[dialog_key] = dialog

            assert self._task_stack is not None
            await self._task_stack.enter_async_context(dialog.run_until_finish())
            return dialog

    async def handle_message(self, envelope: InboundMessage):
        if not isinstance(envelope.peer, telethon.types.PeerUser):
            return

        if not await self._is_allowed(envelope.channel_id, envelope.client, envelope.peer):
            return

        dialog = await self.get_dialog(envelope.channel_id, envelope.peer, envelope.client)
        if not dialog:
            return

        await dialog.handle_message(envelope.message)

    async def _is_allowed(self, channel_id: str, tele_client: TGClient, peer: telethon.types.PeerUser) -> bool:
        channel = self._channels_by_id.get(channel_id)
        if channel is None:
            raise ValueError(f"Unknown channel id: {channel_id}")

        whitelist = channel.whitelist or []
        if whitelist and self._peer_matches_whitelist(peer, whitelist):
            return True

        if isinstance(channel, TelegramUserChannel) and not channel.allow_contacts:
            return False

        contacts = await tele_client.get_contact_user_peer()
        return any(contact.user_id == peer.user_id for contact in contacts)

    def _peer_matches_whitelist(self, peer: telethon.types.TypePeer, whitelist: list[str]) -> bool:
        raw_id: str | None = None
        if isinstance(peer, telethon.types.PeerUser):
            raw_id = str(peer.user_id)
        elif isinstance(peer, telethon.types.PeerChat):
            raw_id = str(peer.chat_id)
        elif isinstance(peer, telethon.types.PeerChannel):
            raw_id = str(peer.channel_id)

        peer_hash = peer_hash_into_str(peer)
        return any(item in {peer_hash, raw_id} for item in whitelist if raw_id is not None)

    async def get_acp_for_dialog(self, dialog_key: DialogKey) -> ACPAgentConfig:
        agent = await self.get_agent_config_for_dialog(dialog_key)
        acp_config = self._acp_agents.get(agent.acp_id)
        if acp_config is None:
            raise ValueError(f"Unknown ACP agent id: {agent.acp_id}")
        return acp_config

    async def get_agent_config_for_dialog(self, dialog_key: DialogKey) -> AgentConfig:
        channel_id, dialog_id = dialog_key
        defualt_agent_id = self._config.agents[0].id
        _ = dialog_id

        agent_id = next((binding.agent for binding in self._config.bindings if binding.channel == channel_id), defualt_agent_id)
        agent = self._agents_by_id.get(agent_id)

        if agent is None:
            raise ValueError(f"Unknown agent id: {agent_id}")
        return agent
