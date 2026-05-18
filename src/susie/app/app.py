import asyncio
import contextlib
import logging

from susie.agent import ACPRegistryCache, AgentRuntimeHub, McpServerHttpSetting
from susie.channel import ChannelHub
from susie.chat import ChatManager
from susie.command import command_chain
from susie.constant import NAME, SUSIE_MCP_NAME
from susie.replier import ChatReplierHub
from susie.router import Router
from susie.settings import Config


class MCPServerStartupError(RuntimeError):
    """Raised when the built-in MCP HTTP server cannot start."""


class APP:
    def __init__(self, config: Config):
        from susie.mcp import MCP, mcp_server

        # https://github.com/zed-industries/codex-acp/issues/55
        builtin_mcp = McpServerHttpSetting(headers={}, name=SUSIE_MCP_NAME, url=mcp_server.mcp_url)

        # Layer One: IO
        _ = mcp_server
        _ = command_chain
        acp_registry = ACPRegistryCache()
        acp_hub = AgentRuntimeHub(config, acp_registry, mcp_servers=[builtin_mcp])

        # Layer Two: The Data Process
        replier_hub = ChatReplierHub(config, acp_hub)
        channel_hub = ChannelHub(config)

        # Layer Three: The Domain Logic
        chat_manager = ChatManager(config, channel_hub, replier_hub, command_chain)

        # Layer Four:
        router = Router(chat_manager)

        # DI
        channel_hub.set_router(router)
        mcp_server.set_chat_manager(chat_manager)

        for command in chat_manager.get_commands():
            command_chain.register(command, scope=NAME)

        self._config = config
        self._chat_manager = chat_manager
        self._router = router
        self._channel_hub = channel_hub
        self._replier_hub = replier_hub
        self._acp_hub = acp_hub
        self._mcp_server: MCP = mcp_server
        self._acp_registery = acp_registry

        self._shutdown = asyncio.Event()
        self.logger = logging.getLogger(__name__)

    async def startup(self) -> None:
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._acp_hub.run())
            await stack.enter_async_context(self._channel_hub.run())

            group = await stack.enter_async_context(asyncio.TaskGroup())
            group.create_task(self._mcp_server.start())

            await self._shutdown.wait()

            self._router.stop_accepting()

    def shutdown(self) -> None:
        self._shutdown.set()
