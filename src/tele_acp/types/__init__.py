from typing import TypeAlias

from .acp import AcpContentBlock, AcpMessage, AcpMessageChunk
from .agent import AgentConfig
from .channel import DEFAULT_TELEGRAM_API_HASH, DEFAULT_TELEGRAM_API_ID, TelegramBotChannel, TelegramUserChannel, TypeTelegramChannel
from .config import Config
from .error import ConfigError, CurrentSessionPathNotValidError, unreachable
from .serialization import Format, Order
from .session import SessionInfo
from .tl import peer_hash_into_str

OutBoundMessage: TypeAlias = str | AcpMessage

__all__ = [
    "Config",
    "ConfigError",
    "CurrentSessionPathNotValidError",
    "SessionInfo",
    "Format",
    "Order",
    "peer_hash_into_str",
    "unreachable",
    "AgentConfig",
    "AcpMessageChunk",
    "AcpContentBlock",
    "AcpMessage",
    "OutBoundMessage",
    "TelegramUserChannel",
    "TelegramBotChannel",
    "TypeTelegramChannel",
    "DEFAULT_TELEGRAM_API_ID",
    "DEFAULT_TELEGRAM_API_HASH",
]
