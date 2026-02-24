import asyncio
import logging
import os

import acp
import telethon
from acp.schema import HttpMcpServer

from tele_acp.acp import ACPClient
from tele_acp.telegram import TGClient
from tele_acp.utils.throttle import Throttler


class AgentThread:
    def __init__(self, peer: telethon.types.TypePeer, tg: TGClient) -> None:
        self.peer = peer
        self._tg = tg
        self._inbound_queue = asyncio.Queue[str]()
        self.logger = logging.getLogger(__name__ + str(self.peer))
        self.outbound_queue = asyncio.Queue[str | None]()

        self.session: acp.schema.NewSessionResponse | None = None

        loop = asyncio.get_running_loop()
        self._inbound_task = loop.create_task(self._handle_inbound())
        self._outbound_task = loop.create_task(self._handle_outbound())

    async def _handle_inbound(self) -> None:
        try:
            async with acp.spawn_agent_process(ACPClient(self.outbound_queue, self.logger), "/Users/huanan/.local/bin/kimi", "acp") as (conn, proc):
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

                # IMPORTANT: inbound loop
                while True:
                    prompt_text = await self._inbound_queue.get()
                    try:
                        await conn.prompt(prompt=[acp.text_block(prompt_text)], session_id=session_id)
                    except Exception:
                        self.logger.exception("Failed to prompt ACP agent")
                    finally:
                        # Indicate a prompt turn has end.
                        await self.outbound_queue.put(None)

        except Exception as e:
            self.logger.exception(f"Failed to handle inbound message: {e}")

    async def _handle_outbound(self) -> None:

        sending_message: telethon.types.TypeMessage | None = None
        sending_content: str = ""  # we can't reuse sending_message as it will strip empty characters.

        limiter = Throttler(rate_limit=1, period=1)

        # IMPORTANT: outbound loop
        while True:
            msg = await self.outbound_queue.get()

            if not msg:
                # IMPORTANT: when received a none from queue it means a prompt turn has end.
                await limiter.flush()
                sending_message = None
                sending_content = ""
                continue

            sending_content += msg

            if msg.strip() == "":
                # telegram requirement. when edit message, content should not be unchanged.
                continue

            # main job: send message
            try:

                async def _t(content: str = sending_content):
                    nonlocal sending_message
                    message_id = sending_message.id if sending_message else None
                    sending_message = await self._send_message(message_id, content)

                await limiter.call(_t)

            except Exception:
                self.logger.exception("Failed to forward ACP response to telegram")

    async def _send_message(self, message_id: int | None, msg: str) -> telethon.types.TypeMessage:
        if message_id:
            message = await self._tg.edit_message(self.peer, message_id, msg)
        else:
            message = await self._tg.send_message(self.peer, msg)
        return message

    async def handle(self, message: telethon.custom.Message) -> None:
        text = (message.raw_text or "").strip()
        if not text:
            return
        await self._inbound_queue.put(text)
