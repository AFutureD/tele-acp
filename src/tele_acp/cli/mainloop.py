import asyncio
import logging

import telethon
from telethon import events
from telethon.custom import Message

from tele_acp.app import APP, AgentThread
from tele_acp.config import load_config
from tele_acp.mcp import mcp_server
from tele_acp.telegram import TGClient
from tele_acp.types import peer_hash_into_str

from .types import SharedArgs


async def mainloop(cli_args: SharedArgs) -> bool:
    logger = logging.getLogger(__name__)

    config = load_config(config_file=cli_args.config_file)
    app = APP(config)

    await app.run_until_finish()

    return True
