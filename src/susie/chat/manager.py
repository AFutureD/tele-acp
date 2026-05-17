import logging

from susie_core import DEFAULT_ASSISTANT_ID, Chatable, ChatInfo, ChatMessage, Command

from susie.channel.hub import ChannelHub
from susie.command import CommandChain
from susie.replier import ChatReplierHub
from susie.settings import SUSIE_CHAT_ALL_INDICATOR, ChatSettings, Config

from .chat import Chat


class ChatManager(Chatable):
    def __init__(self, config: Config, channel_hub: ChannelHub, replier_hub: ChatReplierHub, command_chain: CommandChain):
        self._config = config
        self._channel_hub = channel_hub
        self._replier_hub = replier_hub
        self._command_chain = command_chain
        self.logger = logging.getLogger("ChatManager")

        self._chats: dict[tuple[str, str], Chat] = {}

    async def send_message(self, message: ChatMessage):
        chat = await self.require_chat(message.channel_id, message.chat_id)
        await chat.send_message(message)

    async def receive_message(self, message: ChatMessage):
        chat = await self.require_chat(message.channel_id, message.chat_id)
        await chat.receive_message(message)

    async def list_chat_infos(self, channel_id: str, with_archived: bool = False) -> list[ChatInfo]:
        channel = self._channel_hub.require_channel(channel_id)
        return await channel.list_chats(with_archived)

    def get_chat(self, channel_id: str, chat_id: str) -> Chat | None:
        key = (channel_id, chat_id)
        return self._chats.get(key)

    async def require_chat(self, channel_id: str, chat_id: str) -> Chat:
        cache_key = (channel_id, chat_id)

        if chat := self._chats.get(cache_key):
            return chat

        channel = self._channel_hub.require_channel(channel_id)

        # The Chat Settings
        binding = await self.get_binding(channel_id, chat_id)

        command_chain = CommandChain(self._command_chain)
        try:
            self.logger.info(f"Chat {channel_id} ({chat_id}) building replier")
            replier = await self._replier_hub.build_replier(binding.assistant_id, command_chain)
        except Exception as e:
            self.logger.error(f"build replier failed. error: {e}")
            raise

        chat = Chat(chat_id, channel, binding, replier, command_chain)

        self._chats[cache_key] = chat
        return chat

    async def get_binding(self, channel_id: str, chat_id: str) -> ChatSettings:
        for binding in self._config.bindings:
            if binding.channel != channel_id:
                continue

            if chat_id in binding.chat_ids:
                return binding

            if SUSIE_CHAT_ALL_INDICATOR in binding.chat_ids:
                return binding

        return ChatSettings(
            assistant_id=DEFAULT_ASSISTANT_ID,
            channel=channel_id,
        )

    def get_commands(self) -> list[Command]:
        return []
