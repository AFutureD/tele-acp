# from __future__ import annotations

# import asyncio
# import logging
# from contextlib import AsyncExitStack
# from pathlib import Path

# import acp
# from acp.client.connection import ClientSideConnection
# from acp.schema import HttpMcpServer, Implementation, McpServerStdio, SseMcpServer
# from anyio.streams.memory import MemoryObjectSendStream

# from tele_acp.acp import ACPAgentConfig, ACPClient, ACPUpdateChunk
# from tele_acp.constant import VERSION


# class ACPAgentRuntime:
#     """Owns ACP process/connection lifecycle for one AgentThread."""

#     def __init__(
#         self,
#         *,
#         agent_config: ACPAgentConfig,
#         outbound: MemoryObjectSendStream[ACPUpdateChunk],
#         logger: logging.Logger,
#         cwd: Path,
#         mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
#     ) -> None:
#         self._logger = logger

#         self._outbound = outbound

#         self._agent_config_lock = asyncio.Lock()
#         self._agent_config = agent_config

#         self._cwd = str(cwd.resolve().absolute())
#         self._mcp_servers = mcp_servers

#         self._lock = asyncio.Lock()
#         self._stack: AsyncExitStack | None = None
#         self._conn: ClientSideConnection | None = None
#         self._proc: object | None = None

#         self._session_lock = asyncio.Lock()
#         self._session: acp.NewSessionResponse | None = None

#     @property
#     async def agent_config(self) -> ACPAgentConfig:
#         async with self._agent_config_lock:
#             return self._agent_config

#     async def restart(self, agent_config: ACPAgentConfig | None) -> None:
#         if agent_config:
#             async with self._agent_config_lock:
#                 self._agent_config = agent_config

#         await self._stop()
#         await self._start()

#     async def _ensure_conn(self) -> ClientSideConnection:
#         await self._start()
#         if self._conn is None:
#             raise RuntimeError("ACP connection is not available.")
#         return self._conn

#     async def _ensure_session(self) -> acp.NewSessionResponse:
#         if self._session:
#             return self._session

#         session = await self._new_session()
#         return session

#     async def send_immediately(self, *, contents: list[str]) -> acp.PromptResponse:
#         conn = await self._ensure_conn()
#         session = await self._ensure_session()

#         prompt = map(lambda m: acp.text_block(m), contents)
#         return await conn.prompt(prompt=list(prompt), session_id=session.session_id)

#     async def stop(self) -> None:
#         conn = await self._ensure_conn()
#         session = await self._ensure_session()
#         await conn.cancel(session_id=session.session_id)

#     async def _new_session(self) -> acp.NewSessionResponse:
#         conn = await self._ensure_conn()

#         session = await conn.new_session(cwd=self._cwd, mcp_servers=self._mcp_servers)
#         async with self._session_lock:
#             self._session = session

#         return session

#     async def _start(self):
#         if self._stack is not None:
#             return

#         async with self._agent_config_lock:
#             agent_config = self._agent_config

#         stack = AsyncExitStack()
#         try:
#             conn, proc = await stack.enter_async_context(
#                 acp.spawn_agent_process(
#                     ACPClient(self._outbound, self._logger),
#                     agent_config.acp_path,
#                     *agent_config.acp_args,
#                     cwd=self._cwd,
#                     transport_kwargs={
#                         "limit": 10 * (2**10) * (2**10),  # Buffer Limit 10MB,
#                     },
#                 )
#             )
#             await conn.initialize(
#                 protocol_version=acp.PROTOCOL_VERSION,
#                 client_info=Implementation(name="tele-acp", title="tele-acp", version=VERSION),
#             )

#             async with self._lock:
#                 self._stack = stack
#                 self._conn = conn
#                 self._proc = proc
#         except Exception as e:
#             self._logger.error(f"Failed to start ACP agent process, Error: {e}", e)
#             await stack.aclose()
#             raise

#     async def _stop(self) -> None:
#         async with self._lock:
#             stack = self._stack
#             self._stack = None
#             self._conn = None
#             self._proc = None

#         if stack is None:
#             return

#         await stack.aclose()

#     async def __aenter__(self):
#         await self._start()
#         return self

#     async def __aexit__(self, exc_type, exc_val, exc_tb):
#         await self._stop()

#     async def new_session(self) -> str:
#         session = await self._new_session()
#         return session.session_id
