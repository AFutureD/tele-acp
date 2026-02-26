import asyncio
import logging
import os

import acp
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

import telethon
from acp.schema import HttpMcpServer

from tele_acp.acp import ACPClient
from tele_acp.telegram import TGClient
from tele_acp.utils.throttle import Throttler
from telethon.custom import Message

from .agent import Agent, ACPAgentConfig


class AgentThread:
    def __init__(
        self, dialog_id, agent_config: ACPAgentConfig, inbound_recv: MemoryObjectReceiveStream[Message], outbound_send: MemoryObjectSendStream[str | None]
    ) -> None:
        self.dialog_id = dialog_id
        self.agent_config = agent_config
        self.inbound_recv = inbound_recv
        self.outbound_send = outbound_send
        self.logger = logging.getLogger(__name__ + ":" + dialog_id)
        self.session: acp.schema.NewSessionResponse | None = None

        self.agent = Agent(agent_config)

    async def run_until_finish(self):
        async with self.outbound_send, self.inbound_recv:
            try:
                acp_command = self.agent.acp_agent_config.acp_path
                acp_args = self.agent.acp_agent_config.acp_args
                async with acp.spawn_agent_process(ACPClient(self.outbound_send, self.logger), acp_command, *acp_args) as (conn, proc):
                    _ = proc

                    # DEBUG
                    conn._conn.add_observer(lambda x: self.logger.debug(f"RAW JSONC: {x}"))

                    await conn.initialize(
                        protocol_version=acp.PROTOCOL_VERSION,
                        client_info=acp.schema.Implementation(name="tele-acp", title="tele-acp", version="2026.1.0"),
                    )

                    mcp = HttpMcpServer(name="Telegram ACP Interface", url="http://127.0.0.1:9998/mcp", headers=[], type="http")
                    session = await conn.new_session(cwd=os.getcwd(), mcp_servers=[mcp])

                    self.session = session
                    session_id = session.session_id

                    async for message in self.inbound_recv:
                        content = message.message
                        if not content:
                            continue
                        self.logger.info(f"Agent receive {content}")

                        try:
                            await conn.prompt(prompt=[acp.text_block(content)], session_id=session_id)
                        except Exception:
                            self.logger.exception("Failed to prompt ACP agent")
                        finally:
                            # Indicate a prompt turn has end.
                            await self.outbound_send.send(None)
            except Exception:
                self.logger.error("Failed to spawn_agent_process ACP agent")
