from __future__ import annotations

from pathlib import Path
from typing import Self

import tomlkit
from pydantic import BaseModel, ValidationError, model_validator
from pydantic.fields import Field
from tele_acp_core import DEFAULT_AGENT_ID, AgentConfig, ConfigError
from telegram_channel import DEFAULT_TELEGRAM_API_HASH, DEFAULT_TELEGRAM_API_ID, TypeTelegramChannel
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Table

from .shared import get_app_user_default_dir


class ChatSettings(BaseModel):
    channel: str = Field(description="The id of the `Channel`")
    agent: str = Field(default=DEFAULT_AGENT_ID, description="The id of the `Agent`")


class Config(BaseModel):
    api_id: int | None = Field(default=None, description="Telegram api_id")
    api_hash: str | None = Field(default=None, description="Telegram api_hash")
    dialog_idle_timeout_minutes: int = Field(default=30, ge=1, description="Idle timeout for per-dialog context")

    channels: dict[str, TypeTelegramChannel] = {}
    agents: list[AgentConfig] = [AgentConfig(id=DEFAULT_AGENT_ID)]
    bindings: list[ChatSettings] = []

    @model_validator(mode="after")
    def check_bindings(self) -> Self:
        agent_ids = map(lambda x: x.id, self.agents)
        agent_id_set = set(agent_ids)
        assert len(self.agents) >= 1, "At least one agent is required"
        assert DEFAULT_AGENT_ID in agent_id_set, "Default agent must be present"
        assert len(self.agents) == len(agent_id_set), "Agent ids must be unique"

        return self


def get_config_default_path() -> Path:
    return get_app_user_default_dir() / "config.toml"


def get_config_default() -> Config:
    return Config(api_id=DEFAULT_TELEGRAM_API_ID, api_hash=DEFAULT_TELEGRAM_API_HASH)


def load_config(config_file: Path | None = None) -> Config:
    config_file = config_file or get_config_default_path()

    if not config_file.exists():
        config = get_config_default()

        def _save_config(config: Config, config_file: Path):
            config_file.parent.mkdir(parents=True, exist_ok=True)

            with open(config_file, "w", encoding="utf-8") as f:
                # TOML has no null type; omit None-valued optional fields.
                tomlkit.dump(config.model_dump(mode="json", exclude_none=True), f)

        _save_config(config=config, config_file=config_file)
        return config

    try:
        config_text = config_file.read_text(encoding="utf-8")
        data = tomlkit.loads(config_text)
        config = Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(f"Invalid configuration file: {e}") from e
    except TOMLKitError as e:
        raise ConfigError(f"Invalid configuration file: {e}") from e

    return config


def update_or_save_channel_config(channel_id: str, channel: TypeTelegramChannel, config_file: Path | None = None):
    config_file = config_file or get_config_default_path()

    if not config_file.exists():
        return

    config_text = config_file.read_text(encoding="utf-8")
    data = tomlkit.loads(config_text)

    channels = data.get("channels")

    if not isinstance(channels, Table):  # create channels entry if not exists
        raise ConfigError("Invalid channels entry.")

    channel_item = tomlkit.item(channel.model_dump(mode="json", exclude_none=True))
    channels[channel_id] = channel_item

    data["channels"] = channels

    with open(config_file, "w", encoding="utf-8") as f:
        tomlkit.dump(data, f)


def delete_channel_config(session_name: str, config_file: Path | None = None):
    config_file = config_file or get_config_default_path()

    if not config_file.exists():
        return

    config_text = config_file.read_text(encoding="utf-8")
    data = tomlkit.loads(config_text)

    channels = data.get("channels")

    if not isinstance(channels, Table):  # create channels entry if not exists
        raise ConfigError("Invalid channels entry.")

    for key, item in channels.items():
        if item.get("session_name") != session_name:
            continue
        channels.pop(key)
        break

    data["channels"] = channels

    with open(config_file, "w", encoding="utf-8") as f:
        tomlkit.dump(data, f)
