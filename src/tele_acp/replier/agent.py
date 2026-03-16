import logging
from typing import AsyncIterator

from tele_acp.acp import ACPAgentRuntime, AcpMessage
from tele_acp.types import AgentConfig, Chatable, ChatMessage, ChatMessagePart, ChatMessageReplyable, ChatMessageTextPart


def convert_acp_message_to_chat_message(channel_id: str, chat_id: str, message: AcpMessage) -> ChatMessage:
    text = message.markdown()
    parts: list[ChatMessagePart] = [ChatMessageTextPart(text)] if text else []

    return ChatMessage(id=None, channel_id=channel_id, chat_id=chat_id, out=False, mute=False, parts=parts)


class AgentThread:
    def __init__(self, settings: AgentConfig, acp_runtime: ACPAgentRuntime):
        self.settings = settings
        self._acp_runtime = acp_runtime
        self.logger = logging.getLogger(__name__)

    async def stop_and_send_message(self, message: str) -> AsyncIterator[AcpMessage]:
        async for item in self._acp_runtime.prompt([message]):
            yield item


class ChatReplier(AgentThread, ChatMessageReplyable):
    async def receive_message(self, chat: Chatable, message: ChatMessage) -> None:
        prompt = next((x for x in message.parts if isinstance(x, ChatMessageTextPart)), None)
        if prompt is None:
            return

        self.logger.info(prompt)

        stream: AsyncIterator[AcpMessage] = self.stop_and_send_message(prompt.text)
        async for delta in stream:
            if (stop_reason := delta.stop_reason) and stop_reason != "cancelled":
                msg = convert_acp_message_to_chat_message(message.channel_id, message.chat_id, delta)
                await chat.send_message(msg)
        self.logger.info("Message sent for peer: %s", message.channel_id)
