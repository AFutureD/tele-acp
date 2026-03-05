import enum

from pydantic import BaseModel, Field


class ChannelType(str, enum.Enum):
    TELEGRAM = "telegram"
    TELEGRAM_BOT = "telegram_bot"


class Channel(BaseModel):
    id: str
    type: ChannelType = ChannelType.TELEGRAM


class TelegramChannel(Channel):
    id: str = "default"
    allow_contacts: bool = Field(default=True, description="Whether to allow contacts")
    whitelist: list[str] | None = Field(default=[], description="The list of allowed users. peer id or group id")


class TelegramBotChannel(Channel):
    token: str = Field(description="Telegram bot token")


class DialogBind(BaseModel):
    agent: str = Field(default="default", description="The id of the `Agent`")
    channel: str = Field(default="default", description="The id of the `Channel`")
