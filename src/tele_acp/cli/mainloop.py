import asyncio
import logging

import telethon
from telethon import events
from telethon.custom import Message

from tele_acp.config import load_config
from tele_acp.connection import AgentConnection
from tele_acp.telegram import TGClient
from tele_acp.types import peer_hash_into_str

from .types import SharedArgs


async def mainloop(cli_args: SharedArgs) -> bool:
    logger = logging.getLogger(__name__)

    lock = asyncio.Lock()
    conn_dict: dict[str, AgentConnection] = {}

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
                conn = AgentConnection(message.peer_id, tg)
                conn_dict[peer_hash_into_str(message.peer_id)] = conn

        await conn.handle(message)

    tg = await TGClient.create(session_name=cli_args.session, config=load_config(config_file=cli_args.config_file))
    tg.add_event_handler(on_message, events.NewMessage())

    async with tg as tg:
        await tg.disconnected

    return True
