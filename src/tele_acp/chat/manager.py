from tele_acp_core import DEFAULT_AGENT_ID, Chatable, ChatInfo, ChatMessage

from tele_acp.channel.hub import ChannelHub
from tele_acp.config import ChatSettings, Config
from tele_acp.replier.hub import ChatReplierHub

from .chat import Chat


class ChatManager(Chatable):
    def __init__(self, config: Config, channel_hub: ChannelHub, replier_hub: ChatReplierHub):
        self._config = config
        self._channel_hub = channel_hub
        self._replier_hub = replier_hub

        self._chats: dict[str, Chat] = {}

    async def send_message(self, message: ChatMessage):
        chat = await self.get_chat(message.channel_id, message.chat_id)
        await chat.send_message(message)

    async def receive_message(self, message: ChatMessage):
        chat = await self.get_chat(message.channel_id, message.chat_id)
        await chat.receive_message(message)

    async def list_chat_infos(self, channel_id: str, with_archived: bool = False) -> list[ChatInfo]:
        channel = self._channel_hub.require_channel(channel_id)
        return await channel.list_chats(with_archived)

    async def get_chat(self, channel_id: str, chat_id: str) -> Chat:
        if chat := self._chats.get(chat_id):
            return chat

        binding = await self.get_binding(channel_id, chat_id)
        channel = self._channel_hub.require_channel(channel_id)
        replier = await self._replier_hub.spawn_replier(binding.agent)

        chat = Chat(chat_id, channel, binding, replier)

        self._chats[chat_id] = chat
        return chat

    async def get_binding(self, channel_id: str, chat_id: str) -> ChatSettings:
        _ = chat_id

        for binding in self._config.bindings:
            if binding.channel != channel_id:
                continue
            return binding

        return ChatSettings(
            agent=DEFAULT_AGENT_ID,
            channel=channel_id,
        )
