import asyncio
import contextlib
import logging
import signal
from abc import abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

import acp
import telethon
from acp.client.connection import ClientSideConnection
from acp.schema import HttpMcpServer, McpServerStdio, SseMcpServer
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass
from telethon.custom import Message

from tele_acp import types
from tele_acp.acp import ACPAgentConfig, ACPClient, ACPUpdateChunk
from tele_acp.constant import VERSION
from tele_acp.telegram import TGClient
from tele_acp.types import AcpContentBlock, AcpMessage, AgentConfig, Config, TelegramUserChannel, peer_hash_into_str
from tele_acp.types.config import DEFAULT_AGENT_ID, DEFAULT_CHANNEL_ID, DialogBind


def convert_acp_message_to_chat_message(message: AcpMessage) -> ChatMessage:
    text = message.markdown()
    parts = [text] if text else []

    return ChatMessage(id=None, channel_id="", chat_id="", parts=parts)


def convert_telegram_message_to_chat_message(channel_id: str, message: Message, lifespan: contextlib.AbstractAsyncContextManager | None = None) -> ChatMessage:
    message_id = str(message.id)
    chat_id: str = peer_hash_into_str(message.peer_id)

    text_part: str | None = message.message
    parts = [text_part] if text_part else []

    return ChatMessage(id=message_id, channel_id=channel_id, chat_id=chat_id, parts=parts, lifespan=lifespan)


class ChatReplierHub:
    def __init__(self, config: Config, acp_hub: ACPRuntimeHub) -> None:
        self._config = config
        self._acp_hub = acp_hub

        self.settings: dict[str, AgentConfig] = {agent.id: agent for agent in config.agents}

    async def spawn_replier(self, agent_id: str) -> ChatMessageReplyable | None:
        agent_settings = self.settings.get(agent_id)
        if agent_settings is None:
            return None

        runtime = await self._acp_hub.build_acp_runtime(agent_settings)
        replier = ChatReplier(agent_settings, runtime)
        return replier


class ChatMessageReplyable(Protocol):
    async def receive_message(self, chat: Chat, message: ChatMessage) -> None: ...


class AgentThread(ChatMessageReplyable):
    def __init__(self, settings: AgentConfig, acp_runtime: ACPAgentRuntime):
        self.settings = settings
        self._acp_runtime = acp_runtime
        self.logger = logging.getLogger(__name__)

    async def stop_and_send_message(self, message: str) -> AsyncIterator[AcpMessage]:
        async for item in self._acp_runtime.prompt([message]):
            yield item


class ChatReplier(AgentThread, ChatMessageReplyable):
    async def receive_message(self, chat: Chat, message: ChatMessage) -> None:
        if len(message.parts) == 0:
            return

        prompt = message.parts[0]
        self.logger.info(prompt)

        stream = self.stop_and_send_message(prompt)
        async for delta in stream:
            msg = convert_acp_message_to_chat_message(delta)
            await chat.send_message(msg)


class Channel(Protocol):
    @contextlib.asynccontextmanager
    async def run_until_finish(self):
        yield

    async def send_message(self, message: ChatMessage):
        """Channel Outbound"""
        ...

    @abstractmethod
    async def receive_message(self, message: ChatMessage):
        """Channel Inbound"""
        ...


class TelegramChannel(Channel):
    """
    屏蔽 telethon 对 APP 的细节
    """

    def __init__(self, settings: types.TypeTelegramChannel, message_handler: Callable[[ChatMessage], Awaitable[None]]):
        tele_client = TGClient.create_as_login(None, None, settings)
        tele_client.add_event_handler(self._on_reveive_new_message_event, telethon.events.NewMessage())
        self._tele_client = tele_client
        self._message_handler = message_handler
        self.channel_id = settings.id
        self.logger = logging.getLogger(f"{self.__class__.__name__}:{self.channel_id}")

    @contextlib.asynccontextmanager
    async def run_until_finish(self):
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._tele_client)
            yield

    async def send_message(self, message: ChatMessage):
        # await self._tele_client.send_message("me")
        self.logger.info(f"send_message: {message}")

    async def receive_message(self, message: ChatMessage):
        await self._message_handler(message)

    async def _on_reveive_new_message_event(self, event: telethon.events.NewMessage.Event):
        """Handle message from telethon client"""

        message = event.message

        peer_id = message.peer_id
        if not isinstance(peer_id, telethon.types.PeerUser):
            return

        chat_message = convert_telegram_message_to_chat_message(self.channel_id, message, lifespan=self.build_message_lifespan(peer_id))
        await self.receive_message(chat_message)

    @contextlib.asynccontextmanager
    async def build_message_lifespan(self, peer: telethon.types.TypePeer) -> AsyncIterator[None]:
        async with self._tele_client.with_action(peer, "typing"):
            yield


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class ChatMessage:
    """The Message in Chat"""

    id: str | None = Field(description="The identifier of the message in the chat")
    channel_id: str = Field(description="Which channel this message was sent from")
    chat_id: str = Field(description="Which chat this message wants to be sent to")
    parts: list[str] = Field(default_factory=list, description="The Message")
    lifespan: contextlib.AbstractAsyncContextManager | None = Field(default=None, exclude=True)
    meta: dict[str, Any] = Field(default_factory=dict, description="Metadata for the message")

    @staticmethod
    def Empty() -> ChatMessage:
        return ChatMessage(id=None, channel_id="", chat_id="", parts=[])


class Chat:
    def __init__(self, channel: Channel, replier: ChatMessageReplyable):
        self.replier = replier
        self.channel = channel
        pass

    async def receive_message(self, message: ChatMessage):
        lifespan = message.lifespan or contextlib.nullcontext()

        async with lifespan:
            await self.replier.receive_message(self, message)

    async def send_message(self, message: ChatMessage):
        await self.channel.send_message(message)


class ChatManager:
    def __init__(self, config: Config, channel_hub: ChannelHub, replier_hub: ChatReplierHub):
        self._config = config
        self._channel_hub = channel_hub
        self._replier_hub = replier_hub

        self._chats: dict[str, Chat] = {}

    async def send_message(self, message: ChatMessage):
        pass

    async def receive_message(self, message: ChatMessage):
        chat = await self.get_chat(message.channel_id, message.chat_id)
        await chat.receive_message(message)

    async def get_chat(self, channel_id: str, chat_id: str) -> Chat:
        if chat := self._chats.get(chat_id):
            return chat

        binding = await self.get_binding(channel_id, chat_id)

        channel = self._channel_hub.get_channel(channel_id)
        assert channel is not None, "channel not found"

        replier = await self._replier_hub.spawn_replier(binding.agent)
        assert replier is not None, "agent not found"

        chat = Chat(channel, replier)

        self._chats[chat_id] = chat
        return chat

    async def get_binding(self, channel_id: str, chat_id: str) -> DialogBind:
        _ = channel_id, chat_id
        return DialogBind(
            agent=DEFAULT_AGENT_ID,
            channel=DEFAULT_CHANNEL_ID,
            reporter=None,
        )


class Router:
    def __init__(self, chat_handler: ChatManager):
        self._chat_handler = chat_handler
        self._accepting = True

    async def route(self, message: ChatMessage) -> None:
        if not self._accepting:
            return

        # TODO: add middlewares in the future.
        await self._chat_handler.receive_message(message)

    def stop_accepting(self) -> None:
        self._accepting = False


class ChannelHub:
    def __init__(self, config: Config, router: Router | None = None) -> None:
        self._config = config
        self._router = router

        self._channels_lock = asyncio.Lock()
        self._channels: dict[str, Channel] = {}

        for channel_settings in self._config.channels:
            channel = TelegramChannel(channel_settings, self._on_receive_new_message)
            self._channels[channel.channel_id] = channel

    def set_router(self, router: Router) -> None:
        self._router = router

    def get_channel(self, channel_id: str) -> Channel | None:
        return self._channels.get(channel_id)

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[ChannelHub]:
        async with contextlib.AsyncExitStack() as stack:
            async with self._channels_lock:
                for channel in self._channels.values():
                    await stack.enter_async_context(channel.run_until_finish())
            yield self

    async def _on_receive_new_message(self, message: ChatMessage) -> None:
        """Called when a new message is received from a channel."""
        assert self._router is not None

        await self._router.route(message)


class ACPRuntimeHub:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._stack: contextlib.AsyncExitStack | None

    async def build_acp_runtime(self, agent: AgentConfig) -> ACPAgentRuntime:
        assert self._stack is not None

        acp_config = self.get_acp_config(agent.acp_id)
        assert acp_config is not None, "acp agent not found"

        runtime = ACPAgentRuntime(acp_config, cwd=agent.work_dir)
        await self._stack.enter_async_context(runtime.run())

        return runtime

    def get_acp_config(self, agent_id: str) -> ACPAgentConfig | None:
        # hard-coded agents used during development
        _acp_agents: dict[str, ACPAgentConfig] = {
            agent.id: agent
            for agent in [
                ACPAgentConfig("codex", "Codex", "codex-acp", []),
                ACPAgentConfig("kimi", "Kimi CLI", "kimi", ["acp"]),
            ]
        }

        return _acp_agents.get(agent_id)

    @contextlib.asynccontextmanager
    async def run(self):
        async with contextlib.AsyncExitStack() as stack:
            self._stack = stack
            yield self


class APP:
    def __init__(self, config: Config):
        acp_hub = ACPRuntimeHub(config)
        replier_hub = ChatReplierHub(config, acp_hub)
        channel_hub = ChannelHub(config)
        chat_manager = ChatManager(config, channel_hub, replier_hub)
        router = Router(chat_manager)

        channel_hub.set_router(router)

        self._config = config
        self._chat_manager = chat_manager
        self._router = router
        self._channel_hub = channel_hub
        self._replier_hub = replier_hub
        self._acp_hub = acp_hub

        self._shutdown = asyncio.Event()

    async def startup(self) -> None:
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._channel_hub.run())
            await stack.enter_async_context(self._acp_hub.run())

            await self._shutdown.wait()

            self._router.stop_accepting()

    def shutdown(self) -> None:
        self._shutdown.set()


class ACPAgentRuntime:
    """spawn acp client based on ACPAgentConfig and maintain sessions"""

    def __init__(
        self,
        agent_config: ACPAgentConfig,
        cwd: str | Path | None = None,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._agent_config = agent_config
        self._cwd = str(Path(cwd or Path.cwd()).resolve())
        self._logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}:{agent_config.id}")

        self._mcp_servers = mcp_servers

        self._session: acp.NewSessionResponse | None = None

        self._update_queue: asyncio.Queue[ACPUpdateChunk | None] | None = None

        self._lock = asyncio.Lock()
        self._stack: contextlib.AsyncExitStack | None = None
        self._conn: ClientSideConnection | None = None
        self._proc: object | None = None

    @property
    async def agent_config(self) -> ACPAgentConfig:
        return self._agent_config

    async def change(self, agent_config: ACPAgentConfig | None) -> None:
        if agent_config:
            self._agent_config = agent_config

        await self._stop()
        await self._start()

    async def _ensure_conn(self) -> ClientSideConnection:
        await self._start()
        if self._conn is None:
            raise RuntimeError("ACP connection is not available.")
        return self._conn

    async def _ensure_session(self) -> acp.NewSessionResponse:
        if self._session:
            return self._session

        session = await self._new_session()
        return session

    async def prompt(self, parts: list[str]) -> AsyncIterator[AcpMessage]:
        conn = await self._ensure_conn()
        session = await self._ensure_session()

        prompt: list[AcpContentBlock] = list(map(lambda m: acp.text_block(m), parts))

        message = AcpMessage(prompt=prompt, model=None, usage=None)

        update_queue = asyncio.Queue[ACPUpdateChunk | None]()
        self._update_queue = update_queue

        stop_token = asyncio.Event()

        async def turn_task() -> acp.PromptResponse:
            ret = await conn.prompt(prompt=prompt, session_id=session.session_id)
            stop_token.set()
            return ret

        task = asyncio.create_task(turn_task())

        try:
            while True:
                update = await update_queue.get()
                if update is None:
                    if stop_token.is_set():
                        break
                    continue

                match update:
                    case acp.schema.AgentMessageChunk():
                        message.chunks.append(update)
                    case acp.schema.AgentThoughtChunk():
                        message.chunks.append(update)
                    case acp.schema.ToolCallStart():
                        message.chunks.append(update)
                    case acp.schema.ToolCallProgress():
                        message.chunks.append(update)
                    case acp.schema.AgentPlanUpdate():
                        message.chunks.append(update)
                    case acp.schema.CurrentModeUpdate():
                        message.model = update
                    case acp.schema.UsageUpdate():
                        message.usage = update
                    case _:
                        pass

                yield message

            response = await task
            message.stopReason = response.stop_reason
        finally:
            self._update_queue = None

            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def stop(self) -> None:
        conn = await self._ensure_conn()
        session = await self._ensure_session()
        await conn.cancel(session_id=session.session_id)

    async def new_session(self) -> str:
        session = await self._new_session()
        return session.session_id

    async def _new_session(self) -> acp.NewSessionResponse:
        conn = await self._ensure_conn()

        session = await conn.new_session(cwd=self._cwd, mcp_servers=self._mcp_servers)
        self._session = session

        return session

    async def _start(self):
        if self._stack is not None:
            return

        agent_config = self._agent_config

        async with contextlib.AsyncExitStack() as stack:
            try:
                acp_client = ACPClient(self._handle_session_update, self._logger)

                conn, proc = await stack.enter_async_context(
                    acp.spawn_agent_process(
                        acp_client,
                        agent_config.acp_path,
                        *agent_config.acp_args,
                        cwd=self._cwd,
                        transport_kwargs={
                            "limit": 10 * (2**10) * (2**10),  # Buffer Limit 10MB,
                        },
                    )
                )

                await conn.initialize(
                    protocol_version=acp.PROTOCOL_VERSION,
                    client_info=acp.Implementation(name="tele-acp", title="tele-acp", version=VERSION),
                )
            except Exception as e:
                self._logger.error(f"Failed to start ACP agent process, Error: {e}", e)
                raise

            async with self._lock:
                self._stack = stack
                self._conn = conn
                self._proc = proc

    async def _stop(self) -> None:
        async with self._lock:
            stack = self._stack

            self._stack = None
            self._conn = None
            self._proc = None

        if stack:
            await stack.aclose()

    async def __aenter__(self):
        await self._start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._stop()

    @contextlib.asynccontextmanager
    async def run(self):
        await self._start()
        try:
            yield self
        finally:
            await self._stop()

    async def _handle_session_update(self, session_id: str, update: ACPUpdateChunk) -> None:
        queue = self._update_queue
        session = self._session
        if queue is None or session is None:
            return

        if session.session_id != session_id:
            return

        await queue.put(update)


config = Config(channels=[TelegramUserChannel(id="default", session_name="a7321e7c-e74e-49f9-9e74-38967d1fb0f0")])
app = APP(config)


async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, app.shutdown)

    await app.startup()


if __name__ == "__main__":
    asyncio.run(main())
