# import asyncio
# import logging
# from contextlib import AsyncExitStack

# from tele_acp.mcp import MCP
# from tele_acp.types.config import Config

# from .channels import ChannelsGateway, InboundMessage
# from .dialog import DialogManager


# class APP:
#     def __init__(self, config: Config) -> None:
#         from tele_acp.mcp import mcp_server

#         self.logger = logging.getLogger(__name__)

#         self._config = config
#         self._mcp_server: MCP = mcp_server

#         self._dialog_manager = DialogManager(
#             config,
#             mcp_server_url=self._mcp_server.mcp_url,
#         )

#         self._telegram_manager = ChannelsGateway(
#             config,
#             mcp_server=self._mcp_server,
#             on_message=self.dispatch_tele_message,
#         )

#     async def run_until_finish(self):
#         async with AsyncExitStack() as stack:
#             stack.push_async_callback(self._shutdown)

#             await stack.enter_async_context(self._telegram_manager.run())
#             await stack.enter_async_context(self._dialog_manager.run())

#             group = await stack.enter_async_context(asyncio.TaskGroup())
#             group.create_task(self._mcp_server.run_streamable_http_async())
#             # group.create_task(self._telegram_manager.wait_until_disconnect())

#     async def dispatch_tele_message(self, envelope: InboundMessage):
#         await self._dialog_manager.handle_message(envelope)

#     async def _shutdown(self) -> None:
#         self.logger.info("Finished")
