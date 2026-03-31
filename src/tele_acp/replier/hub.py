from tele_acp_core import AgentConfig, ChatReplyable

from tele_acp.acp.runtime import ACPRuntimeHub
from tele_acp.command import CommandChain
from tele_acp.config import Config

from .agent import AgentReplier
from .command import CommandReplier


class ChatReplierHub:
    def __init__(self, config: Config, acp_hub: ACPRuntimeHub) -> None:
        self._config = config
        self._acp_hub = acp_hub

        self.settings: dict[str, AgentConfig] = {agent.id: agent for agent in config.agents}

    async def build_replier(self, replier_id: str, command_chain: CommandChain | None = None) -> ChatReplyable:
        agent_id = replier_id

        agent_settings = self.settings.get(agent_id)
        if agent_settings is None:
            raise RuntimeError(f"agent not found for id: {agent_id}")

        runtime = await self._acp_hub.spawn_acp_runtime(agent_settings)
        await runtime.require_session_id()  # start a session

        agent_replier = AgentReplier(agent_settings, runtime)

        replier = CommandReplier(agent_replier, command_chain)
        return replier
