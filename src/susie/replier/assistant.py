import logging

import jinja2
from susie_core import AssistantConfig, Chatable, ChatCommandResponder, ChatMessage, ChatMessageTextPart, Command

from susie.agent import AgentRuntime, AgentTurnStatus
from susie.assistants import get_agents_dir
from susie.constant import SUSIE_MCP_NAME

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


class AssistantReplier(ChatCommandResponder):
    def __init__(self, settings: AssistantConfig, acp_runtime: AgentRuntime):
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
            if not opts:
                return f"current: {current}\n\nNo model options available for this runtime."
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
            message_id=message.id,
            reply_to=reply_to,
            content=text_part.text,
        )
        prompt = [content]

        self.logger.info(prompt)

        # force cancel previous prompt turn
        await self._acp_runtime.cancel()  # TODO: check time delta

        # start prompt request
        stream = self._acp_runtime.prompt(prompt)
        async for agent_message in stream:
            if agent_message.status in {AgentTurnStatus.completed, AgentTurnStatus.failed}:
                msg = ChatMessage(
                    id=None,
                    channel_id=channel_id,
                    chat_id=chat_id,
                    receiver=None,
                    reply_to=None,
                    out=False,
                    mute=False,
                    parts=agent_message.chat_message_parts(),
                )
                if (forward_to := self.settings.forward_to) and forward_to != "":
                    msg.receiver = forward_to
                await chat.send_message(msg)

        self.logger.info("Message sent for peer: %s", channel_id)

    def list_commands(self) -> list[Command]:
        return [
            Command(fn=self.new_session, name="new", description="Create a new session"),
            Command(fn=self.list_model_opts, name="model", description="List available model options or switch to a specific model"),
        ]
