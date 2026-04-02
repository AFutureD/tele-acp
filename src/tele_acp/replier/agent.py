import logging
from typing import AsyncIterator

import jinja2
from tele_acp_core import AgentConfig, Chatable, ChatCommandResponder, ChatMessage, ChatMessagePart, ChatMessageTextPart, Command

from src.tele_acp.constant import SUSIE_MCP_NAME
from tele_acp.acp import ACPAgentRuntime, AcpMessage
from tele_acp.agents import get_agents_dir

PROMPT = (
    # Context Info
    "<CONTEXT>\n"
    "Channel ID: {{channel_id}}\n"
    "Chat ID: {{chat_id}}\n"
    "Message ID: {{message_id}}\n"
    "{% if reply_to %}"
    "Reply message ID: {{reply_to}}\n"
    "{% endif %}"
    "</CONTEXT>\n"
    "\n"
    # User Input
    "User Content:\n"
    "{{content}}"
)


def convert_acp_message_to_chat_message(channel_id: str, chat_id: str, message: AcpMessage) -> ChatMessage:
    text = message.markdown()
    parts: list[ChatMessagePart] = [ChatMessageTextPart(text)] if text else []

    return ChatMessage(id=None, channel_id=channel_id, chat_id=chat_id, receiver=None, reply_to=None, out=False, mute=False, parts=parts)


class AgentReplier(ChatCommandResponder):
    def __init__(self, settings: AgentConfig, acp_runtime: ACPAgentRuntime):
        self.settings = settings
        self._acp_runtime = acp_runtime
        self.logger = logging.getLogger(__name__)

    async def new_session(self) -> str:
        session_id = await self._acp_runtime.new_session()
        self.logger.info(f"new session: {session_id}")

        lib_agent_path = get_agents_dir()
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(lib_agent_path),
            keep_trailing_newline=True,
        )
        template = env.get_template("SYSTEM.md")

        prompt = template.render(SUSIE_MCP_NAME=SUSIE_MCP_NAME)
        await self._acp_runtime.load_system_instruction_if_needed(prompt)

        return "ok"

    async def list_model_opts(self, value: str | None = None) -> str:
        opts = await self._acp_runtime.list_model_opts()
        _ = opts

        if value is None:
            current = await self._acp_runtime.model()
            lines = [f"{x.value}: {x.name}" for x in opts]

            return f"current: {current}\n\n" + ("\n".join(lines))

        ret = await self._acp_runtime.set_model(value)
        return "ok" if ret else "failed"

    async def cancel(self):
        await self._acp_runtime.cancel()

    async def receive_message(self, chat: Chatable, message: ChatMessage):
        channel_id = message.channel_id
        chat_id = message.chat_id
        reply_to = message.reply_to

        text_part = next((x for x in message.parts if isinstance(x, ChatMessageTextPart)), None)
        if text_part is None:
            return

        template = jinja2.Template(PROMPT)
        content = template.render(
            channel_id=channel_id,
            chat_id=chat_id,
            reply_to=reply_to,
            content=text_part.text,
        )
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

    def list_commands(self) -> list[Command]:
        return [
            Command(fn=self.new_session, name="new", description="Create a new session"),
            Command(fn=self.list_model_opts, name="model", description="List available model options or switch to a specific model"),
        ]
