from tele_acp_core import Chatable, ChatMessage, ChatReplyable


class ComposedReplier(ChatReplyable):
    def __init__(self, *ordered_repliers: ChatReplyable) -> None:
        self._repliers = ordered_repliers

    async def receive_message(self, chat: Chatable, message: ChatMessage):
        for replier in self._repliers:
            await replier.receive_message(chat, message)
