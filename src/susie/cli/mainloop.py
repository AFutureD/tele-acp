import asyncio
import logging
import signal

from susie.app import APP
from susie.settings import load_config

from .shared import SharedArgs


async def mainloop(cli_args: SharedArgs) -> bool:
    logging.getLogger(__name__)

    config = load_config(config_file=cli_args.config_file)
    app = APP(config)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, app.shutdown)

    await app.startup()

    return True
