import enum
from typing import TypeAlias

from pydantic.fields import Field
from tele_acp_core import ChannelSettings, ChannelType

DEFAULT_TELEGRAM_API_ID = 611335
DEFAULT_TELEGRAM_API_HASH = "d524b414d21f4d37f08684c1df41ac9c"


class TelegramChannelType(ChannelType, enum.Enum):
    TELEGRAM_USER = "telegram_user"
    TELEGRAM_BOT = "telegram_bot"


class TelegramChannel(ChannelSettings):
    session_name: str = Field(description="The session name for the Telegram client")

    whitelist: list[str] | None = Field(default=[], description="The list of allowed users. peer id or group id")


class TelegramUserChannel(TelegramChannel):
    type: ChannelType = TelegramChannelType.TELEGRAM_USER

    allow_contacts: bool = Field(default=True, description="Whether to allow contacts")


class TelegramBotChannel(TelegramChannel):
    type: ChannelType = TelegramChannelType.TELEGRAM_BOT

    token: str = Field(description="Telegram bot token")


TypeTelegramChannel: TypeAlias = TelegramUserChannel | TelegramBotChannel
