import enum
from typing import Self, TypeAlias

from pydantic import BaseModel, Field, model_validator

from .agent import DEFAULT_AGENT_ID, AgentConfig

DEFAULT_TELEGRAM_API_ID = 611335
DEFAULT_TELEGRAM_API_HASH = "d524b414d21f4d37f08684c1df41ac9c"


class ChannelType(str, enum.Enum):
    TELEGRAM_USER = "telegram_user"
    TELEGRAM_BOT = "telegram_bot"


class ChannelSettings(BaseModel):
    type: ChannelType


class TelegramChannel(ChannelSettings):
    session_name: str = Field(description="The session name for the Telegram client")

    whitelist: list[str] | None = Field(default=[], description="The list of allowed users. peer id or group id")


class TelegramUserChannel(TelegramChannel):
    type: ChannelType = ChannelType.TELEGRAM_USER

    allow_contacts: bool = Field(default=True, description="Whether to allow contacts")


class TelegramBotChannel(TelegramChannel):
    type: ChannelType = ChannelType.TELEGRAM_BOT

    token: str = Field(description="Telegram bot token")


TypeTelegramChannel: TypeAlias = TelegramUserChannel | TelegramBotChannel


class ChatSettings(BaseModel):
    channel: str = Field(description="The id of the `Channel`")
    agent: str = Field(default=DEFAULT_AGENT_ID, description="The id of the `Agent`")
    forward_to: str | None = Field(default=None, description="Peer used for report messages of this binding")


class Config(BaseModel):
    api_id: int | None = Field(default=None, description="Telegram api_id")
    api_hash: str | None = Field(default=None, description="Telegram api_hash")
    dialog_idle_timeout_minutes: int = Field(default=30, ge=1, description="Idle timeout for per-dialog context")

    channels: dict[str, TypeTelegramChannel] = {}
    agents: list[AgentConfig] = [AgentConfig(id=DEFAULT_AGENT_ID)]
    bindings: list[ChatSettings] = []

    @model_validator(mode="after")
    def check_bindings(self) -> Self:
        # Validate Channels
        # if default_channel := self.default_channel:
        #     assert len(self.channels) != 0, "default_channel must be provided when channels is not empty"
        #     assert default_channel in self.channels, "default_channel must be present in channels"
        # else:
        #     assert len(self.channels) == 0, "default_channel can only be None when channels is empty"

        # Validate Agents
        agent_ids = map(lambda x: x.id, self.agents)
        agent_id_set = set(agent_ids)
        assert len(self.agents) >= 1, "At least one agent is required"
        assert DEFAULT_AGENT_ID in agent_id_set, "Default agent must be present"
        assert len(self.agents) == len(agent_id_set), "Agent ids must be unique"

        return self
