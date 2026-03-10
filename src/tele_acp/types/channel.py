import enum
from typing import TypeAlias

from pydantic import BaseModel, Field

from .agent import DEFAULT_AGENT_ID


class ChannelType(str, enum.Enum):
    TELEGRAM_USER = "telegram_user"
    TELEGRAM_BOT = "telegram_bot"


class ChannelConfig(BaseModel):
    id: str
    type: ChannelType


DEFAULT_TELEGRAM_ID = "default"
DEFAULT_TELEGRAM_API_ID = 611335
DEFAULT_TELEGRAM_API_HASH = "d524b414d21f4d37f08684c1df41ac9c"


class TelegramChannel(ChannelConfig):
    session_name: str | None = Field(default=None, description="The session name for the Telegram client")

    whitelist: list[str] | None = Field(default=[], description="The list of allowed users. peer id or group id")


class TelegramUserChannel(TelegramChannel):
    type: ChannelType = ChannelType.TELEGRAM_USER

    require_pre_authentication: bool = Field(default=True, description="Whether to require pre-authentication")
    allow_contacts: bool = Field(default=True, description="Whether to allow contacts")


class TelegramBotChannel(TelegramChannel):
    type: ChannelType = ChannelType.TELEGRAM_BOT

    token: str = Field(description="Telegram bot token")


TypeTelegramChannel: TypeAlias = TelegramUserChannel | TelegramBotChannel


class DialogBind(BaseModel):
    agent: str = Field(default=DEFAULT_AGENT_ID, description="The id of the `Agent`")
    channel: str = Field(default=DEFAULT_TELEGRAM_ID, description="The id of the `Channel`")
