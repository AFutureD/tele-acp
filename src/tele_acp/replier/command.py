import shlex

from tele_acp_core import Chatable, ChatMessage, ChatMessageTextPart, ChatReplyable

from tele_acp.command import CommandCenter
from tele_acp.constant import SUSIE_COMMAND_TRIGGER


class CommandReplier(ChatReplyable):
    def __init__(self, replier: ChatReplyable | None = None, chain_to: CommandCenter | None = None):
        self._replier = replier
        self.command_center = CommandCenter(chain_to)

    async def receive_message(self, chat: Chatable, message: ChatMessage):
        if (
            (text_part := next((x for x in message.parts if isinstance(x, ChatMessageTextPart)), None))
            and (text := text_part.text)
            and text_part.text.startswith(SUSIE_COMMAND_TRIGGER)
        ):
            command = text.removeprefix(SUSIE_COMMAND_TRIGGER)
            name, *args = shlex.split(command)
            if self.can_execute(name):
                await self.execute_command(chat, message, name, *args)
        else:
            await self._replier.receive_message(chat, message)

    async def can_execute(self, name: str) -> bool:
        return self.command_center.can_execute(name)

    async def execute_command(self, chat: Chatable, message: ChatMessage, name: str, *args, **kwargs):
        try:
            result = await self.command_center.execute_command(name, *args, message=message)
            if isinstance(result, str):
                await chat.send_message(
                    ChatMessage.create_simple_text_message(
                        channel_id=message.channel_id,
                        chat_id=message.chat_id,
                        text=result,
                    )
                )
            elif isinstance(result, ChatMessage):
                await chat.send_message(result)
        except Exception as e:
            await chat.send_message(
                ChatMessage.create_simple_text_message(
                    channel_id=message.channel_id,
                    chat_id=message.chat_id,
                    text=f"Error: {e}",
                )
            )
