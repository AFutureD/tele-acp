import shlex

from tele_acp_core import Chatable, ChatCommandResponder, ChatMessage, ChatMessageTextPart, ChatReplyable

from tele_acp.command import CommandChain
from tele_acp.constant import SUSIE_COMMAND_TRIGGER


class CommandReplier(ChatReplyable):
    def __init__(self, replier: ChatReplyable | None = None, chain_to: CommandChain | None = None):
        self._replier = replier
        self.command_center = CommandChain(chain_to)

        if isinstance(replier, ChatCommandResponder):
            commands = replier.list_commands()
            for command in commands:
                self.command_center.register(command)


    async def receive_message(self, chat: Chatable, message: ChatMessage):
        if (
            (text_part := next((x for x in message.parts if isinstance(x, ChatMessageTextPart)), None))
            and (text := text_part.text)
            and text_part.text.startswith(SUSIE_COMMAND_TRIGGER)
        ):
            command = text.removeprefix(SUSIE_COMMAND_TRIGGER)
            name, *args = shlex.split(command)
            if await self.can_execute(name):
                await self.execute_command(chat, message, name, *args)
        else:
            if replier := self._replier:
                await replier.receive_message(chat, message)

    async def can_execute(self, name: str) -> bool:
        return await self.command_center.can_execute(name)

    async def execute_command(self, chat: Chatable, message: ChatMessage, name: str, *args):
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
