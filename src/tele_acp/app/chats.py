import asyncio
import contextlib
import signal
from abc import abstractmethod
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

import telethon
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass
from telethon.custom import Message

from tele_acp import types
from tele_acp.acp import ACPAgentConfig
from tele_acp.telegram import TGClient
from tele_acp.types import AcpMessage, AgentConfig, Config, TelegramUserChannel, peer_hash_into_str
from tele_acp.types.config import DEFAULT_AGENT_ID, DEFAULT_CHANNEL_ID, DialogBind


def convert_acp_message_to_chat_message(message: AcpMessage) -> ChatMessage:
    return ChatMessage.Empty()


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

    def swarn_replier(self, agent_id: str) -> ChatMessageReplyable | None:
        agent_settings = self.settings.get(agent_id)
        if agent_settings is None:
            return None

        replier = ChatReplier(agent_settings, self._acp_hub.build_acp_runtime(agent_settings.acp_id))
        return replier


class ChatMessageReplyable(Protocol):
    async def receive_message(self, chat: Chat, message: ChatMessage) -> None: ...


class AgentThread(ChatMessageReplyable):
    def __init__(self, settings: AgentConfig, acp_runtime: ACPAgentRuntime):
        self.settings = settings
        self._acp_runtime = acp_runtime

    async def stop_and_send_message(self, message: str) -> AsyncIterator[AcpMessage]:
        yield AcpMessage(
            prompt=None,
            model=None,
            chunks=[],
            usage=None,
            stopReason=None,
        )


class ChatReplier(AgentThread, ChatMessageReplyable):
    async def receive_message(self, chat: Chat, message: ChatMessage) -> None:
        prompt = message.parts[0]
        print(prompt)

        iter = self.stop_and_send_message(prompt)
        async for delta in iter:
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

    @contextlib.asynccontextmanager
    async def run_until_finish(self):
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._tele_client)
            yield

    async def send_message(self, message: ChatMessage):
        await self._tele_client.send_message("me")
        pass

    async def receive_message(self, message: ChatMessage):
        await self._message_handler(message)

    async def _on_reveive_new_message_event(self, event: telethon.events.NewMessage.Event):
        """Handle message from telethon client"""

        message = event.message

        chat_message = convert_telegram_message_to_chat_message(self.channel_id, message, lifespan=self.build_message_lifespan(message.peer_id))
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

        replier = self._replier_hub.swarn_replier(binding.agent)
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


class ACPAgentRuntime:
    def __init__(self) -> None:
        pass


class ACPRuntimeHub:
    def __init__(self, config: Config) -> None:
        self._config = config

    def build_acp_runtime(self, agent_id: str) -> ACPAgentRuntime:
        return ACPAgentRuntime()

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

        self._shutdown = asyncio.Event()

    async def startup(self) -> None:
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._channel_hub.run())

            await self._shutdown.wait()

            self._router.stop_accepting()

    def shutdown(self) -> None:
        self._shutdown.set()


config = Config(channels=[TelegramUserChannel(id="default", session_name="a7321e7c-e74e-49f9-9e74-38967d1fb0f0")])
app = APP(config)


async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, app.shutdown)

    await app.startup()


if __name__ == "__main__":
    asyncio.run(main())
