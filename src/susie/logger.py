import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

from .constant import NAME
from .shared import get_app_user_config_dir


def configure_logging(level: int = logging.WARN):
    log_dir = get_app_user_config_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_handler = TimedRotatingFileHandler(log_dir / f"{NAME}.log", when="midnight")
    log_handler.setLevel(logging.INFO)

    error_handler = RotatingFileHandler(log_dir / "error.log")
    error_handler.setLevel(logging.ERROR)

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=level,
        handlers=[logging.StreamHandler(), log_handler, error_handler],
    )
