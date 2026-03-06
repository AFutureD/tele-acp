import logging

from tele_acp.app import APP
from tele_acp.config import load_config

from .types import SharedArgs


async def mainloop(cli_args: SharedArgs) -> bool:
    logging.getLogger(__name__)

    config = load_config(config_file=cli_args.config_file)
    app = APP(config)

    await app.run_until_finish()

    return True
