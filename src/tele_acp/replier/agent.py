import logging
from typing import AsyncIterator

from tele_acp.acp import ACPAgentRuntime, AcpMessage
from tele_acp.types import AgentConfig, Chatable, ChatMessage, ChatMessagePart, ChatMessageReplyable, ChatMessageTextPart


def convert_acp_message_to_chat_message(channel_id: str, chat_id: str, message: AcpMessage) -> ChatMessage:
    text = message.markdown()
    parts: list[ChatMessagePart] = [ChatMessageTextPart(text)] if text else []

    return ChatMessage(id=None, channel_id=channel_id, chat_id=chat_id, receiver=None, out=False, mute=False, parts=parts)


class AgentThread:
    def __init__(self, settings: AgentConfig, acp_runtime: ACPAgentRuntime):
        self.settings = settings
        self._acp_runtime = acp_runtime
        self.logger = logging.getLogger(__name__)

    async def stop_and_send_message(self, channel_id, chat_id, content: str) -> AsyncIterator[AcpMessage]:

        prompt = (
            # Context Info
            f"<CONTEXT>\n"
            f"This is a message from Telegram.\n"
            f"Channel ID: {channel_id}\n"
            f"Chat ID: {chat_id}\n"
            f"</CONTEXT>\n"
            f"\n"
            # IMPORTANT
            f"<IMPORTANT>\n"
            f"always using `telegram_mcp_server` tools when you need to operate on Telegram.\n"
            f"always pass `channel_id={channel_id}` to every `Telegram MCP` tool call.\n"
            f"If you want to reply to the message, always call `send_message`, and you may call it multiple times.\n"
            f"</IMPORTANT>\n"
            f"\n"
            # User Input
            f"User Content:\n"
            f"{content}"
        )

        async for item in self._acp_runtime.prompt([prompt]):
            yield item


class ChatReplier(AgentThread, ChatMessageReplyable):
    async def receive_message(self, chat: Chatable, message: ChatMessage) -> None:
        channel_id = message.channel_id
        chat_id = message.chat_id

        content = next((x for x in message.parts if isinstance(x, ChatMessageTextPart)), None)
        if content is None:
            return

        self.logger.info(content)
        stream: AsyncIterator[AcpMessage] = self.stop_and_send_message(channel_id, chat_id, content.text)
        async for delta in stream:
            if (stop_reason := delta.stop_reason) and stop_reason != "cancelled":
                msg = convert_acp_message_to_chat_message(message.channel_id, message.chat_id, delta)
                await chat.send_message(msg)
        self.logger.info("Message sent for peer: %s", message.channel_id)
