import asyncio
import logging

import telethon
from telethon import events
from telethon.custom import Message

from tele_acp.config import load_config
from tele_acp.mcp import mcp_server
from tele_acp.telegram import TGClient
from tele_acp.thread import AgentThread
from tele_acp.types import peer_hash_into_str

from .types import SharedArgs


async def mainloop(cli_args: SharedArgs) -> bool:
    logger = logging.getLogger(__name__)

    lock = asyncio.Lock()
    conn_dict: dict[str, AgentThread] = {}

    async def on_message(event: events.NewMessage.Event):
        _ = event
        message: Message = event.message
        logger.info(f"New message received {message}")

        if not isinstance(message.peer_id, telethon.types.PeerUser):
            return
        if message.out:
            return

        async with lock:
            conn = conn_dict.get(peer_hash_into_str(message.peer_id))
            if not conn:
                conn = AgentThread(message.peer_id, tg)
                conn_dict[peer_hash_into_str(message.peer_id)] = conn

        await conn.handle(message)

    tg = await TGClient.create(session_name=cli_args.session, config=load_config(config_file=cli_args.config_file))
    tg.add_event_handler(on_message, events.NewMessage())

    # start tg client
    async with tg as tg:
        mcp_server.set_tg_client(tg)

        async def _wait_for_disconnect() -> None:
            await tg.disconnected

        async with asyncio.TaskGroup() as group:
            group.create_task(mcp_server.run_streamable_http_async())
            group.create_task(_wait_for_disconnect())

        logger.info("Finished")

    return True
