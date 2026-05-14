from typing import Literal

from pydantic import BaseModel, Field
from susie_core import ChannelSettings

TELEGRAM_BOT_CHAT_ALL_INDICATOR = "*"


class TelegramBotChannelGroupPolicy(BaseModel):
    whitelist: list[str] = Field(default=[TELEGRAM_BOT_CHAT_ALL_INDICATOR], description="The list of allowed users. user id.")
    only_mention: bool = Field(default=True, description="Whether only responses to mentioned messages")


class TelegramBotChannelSettings(ChannelSettings):
    type: Literal["telegram_bot"] = "telegram_bot"  # pyright: ignore[reportIncompatibleVariableOverride]

    token: str = Field(description="The Telegram Bot API token")

    whitelist: list[str] = Field(default=[], description="The list of allowed users. user id")

    groups: dict[str, TelegramBotChannelGroupPolicy] = Field(
        default={TELEGRAM_BOT_CHAT_ALL_INDICATOR: TelegramBotChannelGroupPolicy()},
        description="The list of allowed groups",
    )

    drop_pending_updates: bool = Field(default=False, description="Whether to drop pending updates when polling starts")
