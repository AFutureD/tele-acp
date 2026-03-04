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


class TelegramBotChannel(Channel):
    token: str = Field(description="Telegram bot token")


class ChatDialog(BaseModel):
    id: str = "default"
    channel: Channel = TelegramChannel()


class DialogBind(BaseModel):
    agent: str = Field(default="default", description="The id of the `Agent`")
    channel: str = Field(default="default", description="The id of the `Channel`")
