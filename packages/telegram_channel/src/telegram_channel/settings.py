from pydantic import BaseModel
from pydantic.fields import Field
from susie_core import ChannelSettings, ChannelType

# How to obtain your api_id and api_hash is described here: https://core.telegram.org/api/obtaining_api_id
# The default values get from here: https://github.com/telegramdesktop/tdesktop/blob/dev/docs/api_credentials.md
DEFAULT_TELEGRAM_API_ID = 17349
DEFAULT_TELEGRAM_API_HASH = "344583e45741c457fe1862106095a5eb"


TELEGRAM_PEER_ALL_INDICATOR = "*"


class TelegramChannelGroupPolicy(BaseModel):
    whitelist: list[str] = Field(default=[TELEGRAM_PEER_ALL_INDICATOR], description="The list of allowed users. peer id.")
    only_mention: bool = Field(default=True, description="Whether only responses to mentioned messages")


class TelegramChannelSettings(ChannelSettings):
    type: ChannelType = "telegram_user"

    session_name: str = Field(description="The session name for the Telegram client")

    allow_contacts: bool = Field(default=True, description="Whether to allow contacts")

    # will move to `users` and `TelegramChannelUserPolicy`, for now it's enough.
    whitelist: list[str] | None = Field(default=[], description="The list of allowed users. peer id")

    groups: dict[str, TelegramChannelGroupPolicy] = Field(
        default={TELEGRAM_PEER_ALL_INDICATOR: TelegramChannelGroupPolicy()},
        description="The list of allowed groups",
    )
