import contextlib

from susie_core import AssistantConfig, ChatReplyable

from susie.agent import ACPRuntimeHub, AgentRuntime, CodexSDKRuntime, get_agent_work_dir
from susie.command import CommandChain
from susie.settings import Config

from .assistant import AssistantReplier
from .command import CommandReplier


class ChatReplierHub:
    def __init__(self, config: Config, acp_hub: ACPRuntimeHub) -> None:
        self._config = config
        self._acp_hub = acp_hub
        self._stack: contextlib.AsyncExitStack | None = None

        self.settings: dict[str, AssistantConfig] = {assistant.assistant_id: assistant for assistant in config.assistants}

    async def __aenter__(self) -> "ChatReplierHub":
        self._stack = contextlib.AsyncExitStack()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        stack = self._stack
        self._stack = None
        if stack is not None:
            await stack.aclose()

    async def build_replier(self, replier_id: str, command_chain: CommandChain | None = None) -> ChatReplyable:
        assert self._stack is not None, "Chat replier hub is not running"

        assistant_id = replier_id

        assistant_settings = self.settings.get(assistant_id)
        if assistant_settings is None:
            raise RuntimeError(f"assistant not found for id: {assistant_id}")

        runtime: AgentRuntime
        if assistant_settings.agent_id == "codex":
            codex_runtime = CodexSDKRuntime(
                cwd=assistant_settings.work_dir or get_agent_work_dir(assistant_settings.assistant_id),
            )
            await self._stack.enter_async_context(codex_runtime)
            runtime = codex_runtime
        else:
            runtime = await self._acp_hub.spawn_acp_runtime(assistant_settings)

        assistant_replier = AssistantReplier(assistant_settings, runtime)
        await assistant_replier.new_session()

        replier = CommandReplier(assistant_replier, command_chain)
        return replier
