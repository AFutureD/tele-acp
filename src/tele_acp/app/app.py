import asyncio
import contextlib

import acp

from tele_acp.acp import ACPRuntimeHub
from tele_acp.channel import ChannelHub
from tele_acp.chat import ChatManager
from tele_acp.config import Config
from tele_acp.replier import ChatReplierHub
from tele_acp.router import Router


class APP:
    def __init__(self, config: Config):
        from tele_acp.mcp import MCP, NAME, mcp_server

        builtin_mcp = acp.schema.HttpMcpServer(
            name=NAME,  # https://github.com/zed-industries/codex-acp/issues/55
            url=mcp_server.mcp_url,
            headers=[],
            type="http",
        )

        acp_hub = ACPRuntimeHub(config, mcp_servers=[builtin_mcp])
        replier_hub = ChatReplierHub(config, acp_hub)
        channel_hub = ChannelHub(config)
        chat_manager = ChatManager(config, channel_hub, replier_hub)
        router = Router(chat_manager)

        channel_hub.set_router(router)
        mcp_server.set_chat_manager(chat_manager)

        self._config = config
        self._chat_manager = chat_manager
        self._router = router
        self._channel_hub = channel_hub
        self._replier_hub = replier_hub
        self._acp_hub = acp_hub
        self._mcp_server: MCP = mcp_server

        self._shutdown = asyncio.Event()

    async def startup(self) -> None:
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._channel_hub.run())
            await stack.enter_async_context(self._acp_hub.run())

            group = await stack.enter_async_context(asyncio.TaskGroup())
            group.create_task(self._mcp_server.run_streamable_http_async())

            await self._shutdown.wait()

            self._router.stop_accepting()

    def shutdown(self) -> None:
        self._shutdown.set()
