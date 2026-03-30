from tele_acp_core import ChatMessage, Command, CommandProvider


class Inspector(CommandProvider):
    def list_commands(self) -> list[Command]:
        return [
            Command(fn=self.get_chat_id, name="chat_id", description="Get current chat id"),
        ]

    async def get_chat_id(self, message: ChatMessage) -> str:
        return message.chat_id
