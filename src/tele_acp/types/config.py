import enum
from typing import Self, TypeAlias

from pydantic import BaseModel, Field

from .agent import DEFAULT_AGENT_ID, AgentConfig

DEFAULT_CHANNEL_ID = "default"
DEFAULT_TELEGRAM_API_ID = 611335
DEFAULT_TELEGRAM_API_HASH = "d524b414d21f4d37f08684c1df41ac9c"


class ChannelType(str, enum.Enum):
    TELEGRAM_USER = "telegram_user"
    TELEGRAM_BOT = "telegram_bot"


class ChannelSettings(BaseModel):
    id: str
    type: ChannelType


class TelegramChannel(ChannelSettings):
    session_name: str | None = Field(default=None, description="The session name for the Telegram client")

    whitelist: list[str] | None = Field(default=[], description="The list of allowed users. peer id or group id")


class TelegramUserChannel(TelegramChannel):
    type: ChannelType = ChannelType.TELEGRAM_USER

    require_pre_authentication: bool = Field(default=True, description="Whether to require pre-authentication", exclude=True)
    allow_contacts: bool = Field(default=True, description="Whether to allow contacts")


class TelegramBotChannel(TelegramChannel):
    type: ChannelType = ChannelType.TELEGRAM_BOT

    token: str = Field(description="Telegram bot token")


TypeTelegramChannel: TypeAlias = TelegramUserChannel | TelegramBotChannel


class DialogBind(BaseModel):
    agent: str = Field(default=DEFAULT_AGENT_ID, description="The id of the `Agent`")
    channel: str = Field(default=DEFAULT_CHANNEL_ID, description="The id of the `Channel`")
    reporter: str | int | None = Field(default=None, description="Peer used for report messages of this binding")


class Config(BaseModel):
    api_id: int | None = Field(default=None, description="Telegram api_id")
    api_hash: str | None = Field(default=None, description="Telegram api_hash")
    dialog_idle_timeout_minutes: int = Field(default=30, ge=1, description="Idle timeout for per-dialog context")

    channels: list[TelegramUserChannel | TelegramBotChannel] = []
    agents: list[AgentConfig] = [AgentConfig(id=DEFAULT_AGENT_ID)]
    bindings: list[DialogBind] = []

    # @model_validator(mode="after")
    def check_bindings(self) -> Self:
        # Valiate Channels
        channel_ids = map(lambda x: x.id, self.channels)
        channel_id_set = set(channel_ids)
        assert len(self.channels) >= 1, "At least one channel is required"
        assert DEFAULT_CHANNEL_ID in channel_id_set, "Default channel must be present"
        assert len(self.channels) == len(channel_id_set), "Channel ids must be unique"
        assert len(self.channels) <= 1 or all(channel.session_name is not None for channel in self.channels), "session_name must be provided for all channels"

        # Valiate Agents
        agent_ids = map(lambda x: x.id, self.agents)
        agent_id_set = set(agent_ids)
        assert len(self.agents) >= 1, "At least one agent is required"
        assert DEFAULT_AGENT_ID in agent_id_set, "Default agent must be present"
        assert len(self.agents) == len(agent_id_set), "Agent ids must be unique"

        return self
