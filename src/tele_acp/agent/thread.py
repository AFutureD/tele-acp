# from __future__ import annotations

# import asyncio
# import logging
# from contextlib import AsyncExitStack, asynccontextmanager, suppress
# from pathlib import Path
# from typing import AsyncIterator

# import acp
# import anyio
# from acp.schema import HttpMcpServer, McpServerStdio, SseMcpServer
# from telethon.custom import Message

# from tele_acp.acp import ACPAgentConfig, ACPUpdateChunk
# from tele_acp.shared import get_app_user_defualt_dir
# from tele_acp.types import OutBoundMessage
# from tele_acp.types.acp import AcpMessage
# from tele_acp.types.agent import AgentConfig

# from .agent import ACPAgentRuntime


# def _get_agent_work_folder():
#     ret = get_app_user_defualt_dir() / "workspace"
#     ret.mkdir(parents=True, exist_ok=True)
#     return ret


# def get_agent_work_dir(id: str) -> Path:
#     agent_dir = _get_agent_work_folder() / id
#     agent_dir.mkdir(parents=True, exist_ok=True)
#     return agent_dir


# class AgentBaseThread:
#     def __init__(
#         self,
#         agent_config: AgentConfig,
#         acp_config: ACPAgentConfig,
#         mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
#         logger: logging.Logger | None = None,
#     ) -> None:
#         self.logger = logger or logging.getLogger(f"{__name__}")

#         self.id = agent_config.id
#         self.agent_config = agent_config

#         inner_outbound_writer, inner_outbound = anyio.create_memory_object_stream[
#             acp.schema.UserMessageChunk
#             | acp.schema.AgentMessageChunk
#             | acp.schema.AgentThoughtChunk
#             | acp.schema.ToolCallStart
#             | acp.schema.ToolCallProgress
#             | acp.schema.AgentPlanUpdate
#             | acp.schema.AvailableCommandsUpdate
#             | acp.schema.CurrentModeUpdate
#             | acp.schema.ConfigOptionUpdate
#             | acp.schema.SessionInfoUpdate
#             | acp.schema.UsageUpdate
#         ](0)
#         self._inner_outbound = inner_outbound

#         self._runtime = ACPAgentRuntime(
#             agent_config=acp_config,
#             outbound=inner_outbound_writer,
#             logger=self.logger,
#             cwd=self.work_dir(agent_config.id, agent_config.work_dir),
#             mcp_servers=mcp_servers,
#         )

#         self.queue_message_when_idle = False
#         self._turn_task: asyncio.Task | None = None

#         self._message_lock = asyncio.Lock()
#         self.message: AcpMessage | None = None

#     @staticmethod
#     def work_dir(acp_id: str, work_dir: str | None) -> Path:
#         if work_dir:
#             path = Path(work_dir)
#             if path.exists():
#                 return path

#         return get_agent_work_dir(acp_id)

#     @asynccontextmanager
#     async def run_until_finish(self):
#         async with AsyncExitStack() as ts:
#             await ts.enter_async_context(self._runtime)
#             await ts.enter_async_context(self._handler_acp_message())
#             yield

#     def build_runtime_messages(self, content: str) -> list[str]:
#         return [content]

#     async def run_turn(self, content: str) -> None:
#         async with self._in_turn() as message, self.turn_context():
#             message.prompt = content

#             contents = self.build_runtime_messages(content)
#             response = await self._runtime.send_immediately(contents=contents)
#             message.stopReason = response.stopReason

#     async def handle_inbound_message(self, message: Message):
#         content = message.message
#         if not content or not isinstance(content, str):
#             return

#         if not self.queue_message_when_idle:
#             if self.message and self.message.stopReason is None:
#                 await self._runtime.stop()

#             self._turn_task = asyncio.create_task(self.run_turn(content))
#         else:
#             raise RuntimeError("Queue message when idle is not supported")

#     @asynccontextmanager
#     async def _handler_acp_message(self):
#         task = asyncio.create_task(self._run_acp_message_handler())
#         try:
#             yield
#         finally:
#             task.cancel()
#             with suppress(asyncio.CancelledError):
#                 await task

#     async def _run_acp_message_handler(self) -> None:
#         async with self._inner_outbound:
#             async for chunk in self._inner_outbound:
#                 async with self._message_lock:
#                     await self.handle_session_update(chunk)

#     async def handle_session_update(
#         self,
#         chunk: ACPUpdateChunk,
#     ):
#         if self.message is None:
#             return

#         match chunk:
#             case acp.schema.AgentMessageChunk():
#                 self.message.chunks.append(chunk)
#             case acp.schema.AgentThoughtChunk():
#                 self.message.chunks.append(chunk)
#             case acp.schema.ToolCallStart():
#                 self.message.chunks.append(chunk)
#             case acp.schema.ToolCallProgress():
#                 self.message.chunks.append(chunk)
#             case acp.schema.AgentPlanUpdate():
#                 self.message.chunks.append(chunk)
#             case acp.schema.UsageUpdate():
#                 self.message.usage = chunk

#     @asynccontextmanager
#     async def turn_context(self) -> AsyncIterator[None]:
#         yield

#     @asynccontextmanager
#     async def _in_turn(self) -> AsyncIterator[AcpMessage]:
#         async with self._message_lock:
#             message = self.message
#             if not (message is not None and message.stopReason == "cancelled"):
#                 message = AcpMessage(
#                     prompt=None,
#                     model=None,
#                     chunks=[],
#                     usage=None,
#                 )
#             else:
#                 message.usage = None
#                 message.stopReason = None

#             self.message = message

#         try:
#             yield message
#         finally:
#             self.logger.info(f"Agent turn has end {message.markdown()}")

#             async with self._message_lock:
#                 if not (message.stopReason and message.stopReason == "cancelled"):
#                     self.message = None

#             await self.handle_outbound_message(message)

#     async def handle_outbound_message(self, message: OutBoundMessage):
#         pass
