import logging
from typing import AsyncIterator

import jinja2
from tele_acp_core import AgentConfig, Chatable, ChatMessage, ChatMessagePart, ChatMessageTextPart, ChatReplyable

from tele_acp.acp import ACPAgentRuntime, AcpMessage
from tele_acp.command import CommandCenter
from tele_acp.constant import SUSIE_MCP_NAME

from .command import CommandReplier

PROMPT = (
    # IMPORTANT. We may move to system instructions but the acp do not support this.
    "<IMPORTANT>\n"
    f"always using `{SUSIE_MCP_NAME}` tools when you need to operate on Telegram.\n"
    "always pass `channel_id={{channel_id}}` to every tool call.\n"
    "If you want to reply to the message, always call `send_message`, and you may call it multiple times.\n"
    "</IMPORTANT>\n"
    "\n"
    # Context Info
    "<CONTEXT>\n"
    "Channel ID: {{channel_id}}\n"
    "Chat ID: {{chat_id}}\n"
    "</CONTEXT>\n"
    "\n"
    # User Input
    "User Content:\n"
    "{{content}}"
)


def convert_acp_message_to_chat_message(channel_id: str, chat_id: str, message: AcpMessage) -> ChatMessage:
    text = message.markdown()
    parts: list[ChatMessagePart] = [ChatMessageTextPart(text)] if text else []

    return ChatMessage(id=None, channel_id=channel_id, chat_id=chat_id, receiver=None, out=False, mute=False, parts=parts)


class AgentThread(ChatReplyable):
    def __init__(self, settings: AgentConfig, acp_runtime: ACPAgentRuntime):
        self.settings = settings
        self._acp_runtime = acp_runtime
        self.logger = logging.getLogger(__name__)

    async def receive_message(self, chat: Chatable, message: ChatMessage):
        channel_id = message.channel_id
        chat_id = message.chat_id

        text_part = next((x for x in message.parts if isinstance(x, ChatMessageTextPart)), None)
        if text_part is None:
            return

        template = jinja2.Template(PROMPT)
        content = template.render(channel_id=channel_id, chat_id=chat_id, content=text_part.text)
        prompt = [content]

        self.logger.info(prompt)

        # force cancel previous prompt turn
        await self._acp_runtime.cancel()  # TODO: check time delta

        # start prompt request
        stream: AsyncIterator[AcpMessage] = self._acp_runtime.prompt(prompt)
        async for delta in stream:
            if (stop_reason := delta.stop_reason) and stop_reason != "cancelled":
                msg = convert_acp_message_to_chat_message(message.channel_id, message.chat_id, delta)
                if (forward_to := self.settings.forward_to) and forward_to != "":
                    msg.receiver = forward_to
                await chat.send_message(msg)

        self.logger.info("Message sent for peer: %s", message.channel_id)


class AgentReplier(CommandReplier):
    def __init__(self, settings: AgentConfig, acp_runtime: ACPAgentRuntime, chain_to: CommandCenter | None = None):
        thread = AgentThread(settings=settings, acp_runtime=acp_runtime)
        super().__init__(thread, chain_to)

        self.thread = thread

        self.command_center.register_command(fn=self.echo, name="echo", description="Echo Messages")

    def echo(self, message: str) -> str:
        return message
