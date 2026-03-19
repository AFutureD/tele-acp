from tele_acp_core import AgentConfig, ChatMessageReplyable

from tele_acp.acp.runtime import ACPRuntimeHub
from tele_acp.config import Config

from .agent import AgentReplier


class ChatReplierHub:
    def __init__(self, config: Config, acp_hub: ACPRuntimeHub) -> None:
        self._config = config
        self._acp_hub = acp_hub

        self.settings: dict[str, AgentConfig] = {agent.id: agent for agent in config.agents}

    async def spawn_replier(self, agent_id: str) -> ChatMessageReplyable:
        agent_settings = self.settings.get(agent_id)
        if agent_settings is None:
            raise RuntimeError(f"agent not found for id: {agent_id}")

        runtime = await self._acp_hub.build_acp_runtime(agent_settings)
        replier = AgentReplier(agent_settings, runtime)
        return replier
