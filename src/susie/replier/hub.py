from susie_core import AssistantConfig, ChatReplyable

from susie.agent import AgentRuntimeHub
from susie.command import CommandChain
from susie.settings import Config

from .assistant import AssistantReplier
from .command import CommandReplier


class ChatReplierHub:
    def __init__(self, config: Config, acp_hub: AgentRuntimeHub) -> None:
        self._config = config
        self._acp_hub = acp_hub

        self.settings: dict[str, AssistantConfig] = {assistant.assistant_id: assistant for assistant in config.assistants}

    async def build_replier(self, replier_id: str, command_chain: CommandChain | None = None) -> ChatReplyable:
        assistant_id = replier_id

        assistant_settings = self.settings.get(assistant_id)
        if assistant_settings is None:
            raise RuntimeError(f"assistant not found for id: {assistant_id}")

        runtime = await self._acp_hub.spawn_acp_runtime(assistant_settings)

        assistant_replier = AssistantReplier(assistant_settings, runtime)
        await assistant_replier.new_session()

        replier = CommandReplier(assistant_replier, command_chain)
        return replier
