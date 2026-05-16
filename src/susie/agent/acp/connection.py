import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Awaitable, Callable

import acp

from susie.constant import VERSION

from .client import ACPAgentConfig, ACPClient, ACPUpdateChunk


class ACPAgentConnection:
    def __init__(
        self,
        agent_config: ACPAgentConfig,
        cwd: str | Path | None = None,
        on_session_update: Callable[[str, ACPUpdateChunk], Awaitable[None]] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._agent_config = agent_config
        self._cwd = str(Path(cwd or Path.cwd()).resolve())
        self._on_session_update = on_session_update

        self.logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}:{agent_config.id}")

        self._lock = asyncio.Lock()
        self._stack: contextlib.AsyncExitStack | None = None
        self._conn: acp.core.ClientSideConnection | None = None
        self._proc: object | None = None

    @property
    def connection(self) -> acp.core.ClientSideConnection:
        if self._conn is None:
            raise RuntimeError("ACP Connection is not available.")
        return self._conn

    @property
    async def agent_config(self) -> ACPAgentConfig:
        return self._agent_config

    async def set_agent_config(self, agent_config: ACPAgentConfig | None) -> None:
        if agent_config:
            self._agent_config = agent_config

        await self._stop()
        await self._start()

    async def _start(self):
        if self._stack is not None:
            return

        agent_config = self._agent_config

        stack = contextlib.AsyncExitStack()
        try:
            acp_client = ACPClient(self._on_session_update, self.logger)

            conn, proc = await stack.enter_async_context(
                acp.spawn_agent_process(
                    acp_client,
                    agent_config.acp_path,
                    *agent_config.acp_args,
                    cwd=self._cwd,
                    transport_kwargs={
                        "limit": 10 * (2**10) * (2**10),  # Buffer Limit 10MB,
                    },
                )
            )

            # TODO: add jsonl logger
            conn._conn.add_observer(lambda x: self.logger.debug(f"JSONRPC: {x}"))

            ret = await conn.initialize(
                protocol_version=acp.PROTOCOL_VERSION,
                client_info=acp.schema.Implementation(name="tele-acp", title="tele-acp", version=VERSION),
            )
            self.logger.info(f"Initialized ACP agent process: {ret}")

            async with self._lock:
                self._stack = stack
                self._conn = conn
                self._proc = proc

        except Exception as e:
            self.logger.error(f"Failed to start ACP agent process, Error: {e}", e)
            await stack.aclose()
            raise

    async def _stop(self) -> None:
        async with self._lock:
            stack = self._stack

            self._stack = None
            self._conn = None
            self._proc = None

        if stack:
            await stack.aclose()

    async def __aenter__(self):
        await self._start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._stop()
