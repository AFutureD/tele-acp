import contextlib
import uuid
from typing import AsyncIterator, Self

import acp
from susie_core import AssistantConfig

from susie.settings import Config

from .acp import ACPAgentConfig, ACPAgentRuntime, ACPRegisteryManage, ACPRegistryCache, get_agent_work_dir
from .codex import CodexSDKRuntime
from .runtime import AgentRuntime, McpServerHttpSetting


class AgentRuntimeHub:
    def __init__(
        self,
        config: Config,
        acp_registry: ACPRegistryCache,
        mcp_servers: list[McpServerHttpSetting] | None = None,
    ) -> None:
        self._config = config
        self._stack: contextlib.AsyncExitStack | None = None
        self._mcp_servers = mcp_servers
        self._runtimes: dict[str, AgentRuntime] = {}
        self._acp_manager = ACPRegisteryManage(acp_registry)

    async def spawn_acp_runtime(self, assistant: AssistantConfig) -> AgentRuntime:
        assert self._stack is not None

        id = str(uuid.uuid4())

        runtime: AgentRuntime
        if assistant.agent_id == "codex":
            runtime = CodexSDKRuntime(cwd=assistant.work_dir or get_agent_work_dir(assistant.assistant_id), mcp_servers=self._mcp_servers)
        else:
            acp_config = await self.get_acp_config(assistant.agent_id)
            assert acp_config is not None, f"acp agent {assistant.agent_id} not found"
            
            runtime = ACPAgentRuntime(
                id, acp_config, cwd=assistant.work_dir or get_agent_work_dir(assistant.assistant_id), mcp_servers=self.convert_to_acp_mcp_servers()
            )
        await self._stack.enter_async_context(runtime)
        self._runtimes[id] = runtime

        return runtime

    async def get_acp_config(self, agent_id: str) -> ACPAgentConfig | None:
        acp = await self._acp_manager.get_agent_config(agent_id)
        return acp

    def get_runtime(self, id: str) -> AgentRuntime | None:
        return self._runtimes.get(id)

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[Self]:
        async with contextlib.AsyncExitStack() as stack:
            self._stack = stack
            try:
                yield self
            finally:
                self._stack = None

    def convert_to_acp_mcp_servers(self) -> list[acp.schema.HttpMcpServer | acp.schema.SseMcpServer | acp.schema.McpServerStdio] | None:
        mcp_servers = self._mcp_servers
        if mcp_servers is None:
            return None

        ret = list[acp.schema.HttpMcpServer | acp.schema.SseMcpServer | acp.schema.McpServerStdio]()
        for mcp in mcp_servers:
            ret.append(acp.schema.HttpMcpServer(headers=[], name=mcp.name, url=mcp.name, type="http"))

        return ret
