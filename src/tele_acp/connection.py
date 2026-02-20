import asyncio
import logging
import os

import acp
import telethon
from throttler import Throttler

from tele_acp.acp import ACPClient
from tele_acp.telegram import TGClient


class AgentConnection:
    def __init__(self, peer: telethon.types.TypePeer, tg: TGClient) -> None:
        self.peer = peer
        self._tg = tg
        self._inbound_queue = asyncio.Queue[str]()
        self.logger = logging.getLogger(__name__ + str(self.peer))
        self.response_queue = asyncio.Queue[str | None]()

        self.session: acp.schema.NewSessionResponse | None = None

        loop = asyncio.get_running_loop()
        self._inbound_task = loop.create_task(self._handle_inbound())
        self._outbound_task = loop.create_task(self._handle_outbound())

    async def _handle_inbound(self) -> None:
        try:
            async with acp.spawn_agent_process(ACPClient(self.response_queue, self.logger), "/opt/homebrew/bin/codex-acp") as (conn, proc):
                # DEBUG
                conn._conn.add_observer(lambda x: self.logger.debug(f"RAW JSONC: {x}"))

                _ = proc
                await conn.initialize(
                    protocol_version=acp.PROTOCOL_VERSION,
                    client_capabilities=acp.schema.ClientCapabilities(
                        fs=acp.schema.FileSystemCapability(read_text_file=False, write_text_file=False),
                        terminal=False,
                    ),
                    client_info=acp.schema.Implementation(name="tele-acp", title="tele-acp", version="2026.1.0"),
                )
                session = await conn.new_session(cwd=os.getcwd())
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
                        await self.response_queue.put(None)

        except Exception as e:
            self.logger.exception(f"Failed to handle inbound message: {e}")

    async def _handle_outbound(self) -> None:

        sending_message: telethon.types.TypeMessage | None = None
        sending_content: str = ""  # we can't reuse sending_message as it will strip empty charactors.

        throttler = Throttler(rate_limit=1, period=1)

        # IMPORTANT: outbound loop
        while True:
            msg = await self.response_queue.get()

            if not msg:
                # IMPORTANT: when received a none from queue it meams a prompt turn has end.
                sending_message = None
                sending_content = ""
                continue

            if msg.strip() == "":
                # telegram requirement. when edit message, content should not be the same.
                continue

            sending_content += msg

            async with throttler:
                try:
                    if sending_message:
                        sending_message = await self._tg.edit_message(self.peer, sending_message.id, sending_content)
                    else:
                        sending_message = await self._tg.send_message(self.peer, sending_content)

                except Exception:
                    self.logger.exception("Failed to forward ACP response to telegram")

    async def handle(self, message: telethon.custom.Message) -> None:
        text = (message.raw_text or "").strip()
        if not text:
            return
        await self._inbound_queue.put(text)
