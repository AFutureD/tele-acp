from tele_acp_core import Chatable, ChatMessage, ChatMessageTextPart, ChatReplyable, CommandExecutable

SUSIE_COMMAND_TRIGGER = "/"


class CommandReplier(ChatReplyable):
    def __init__(self, executor: CommandExecutable):
        self._executor = executor

    async def receive_message(self, chat: Chatable, message: ChatMessage) -> bool:
        text_part = next((x for x in message.parts if isinstance(x, ChatMessageTextPart)), None)
        if text_part is None:
            return False

        text = text_part.text
        if not text.startswith(SUSIE_COMMAND_TRIGGER):
            return False

        command = text.removeprefix(SUSIE_COMMAND_TRIGGER)
        name, args = self.parse_command(command)
        if not await self._executor.can_execute(name):
            await chat.send_message(
                ChatMessage.create_simple_text_message(
                    channel_id=message.channel_id,
                    chat_id=message.chat_id,
                    text=f"Unknown command: {name}",
                )
            )
            return True

        try:
            response = await self._executor.execute_command(name, *args, message=message)
            if isinstance(response, str):
                await chat.send_message(
                    ChatMessage.create_simple_text_message(
                        channel_id=message.channel_id,
                        chat_id=message.chat_id,
                        text=response,
                    )
                )
            elif isinstance(response, ChatMessage):
                await chat.send_message(response)

        except Exception as e:
            await chat.send_message(
                ChatMessage.create_simple_text_message(
                    channel_id=message.channel_id,
                    chat_id=message.chat_id,
                    text=f"Error: {e}",
                )
            )

        return True

    def parse_command(self, command: str) -> tuple[str, list]:
        import shlex

        name, *args = shlex.split(command)
        return name, args
