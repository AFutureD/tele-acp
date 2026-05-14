from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

import tomlkit
from pydantic import BaseModel, ValidationError, model_validator
from pydantic.fields import Field
from susie_core import DEFAULT_AGENT_ID, AgentConfig, ChannelSettings, ConfigError
from telegram_bot_channel import TelegramBotChannelSettings
from telegram_channel import DEFAULT_TELEGRAM_API_HASH, DEFAULT_TELEGRAM_API_ID, TelegramChannelSettings
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import AoT, Table

from .shared import get_app_user_config_dir

SUSIE_CHAT_ALL_INDICATOR = "*"

ChannelConfig = Annotated[TelegramChannelSettings | TelegramBotChannelSettings, Field(discriminator="type")]


class ChatSettings(BaseModel):
    channel: str = Field(description="The id of the `Channel`")
    chat_ids: list[str] = Field(default=[SUSIE_CHAT_ALL_INDICATOR], description="Optional chat IDs matched by this binding")
    agent: str = Field(default=DEFAULT_AGENT_ID, description="The id of the `Agent`")


class Config(BaseModel):
    api_id: int | None = Field(default=None, description="Telegram api_id")
    api_hash: str | None = Field(default=None, description="Telegram api_hash")

    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    agents: list[AgentConfig] = Field(default_factory=lambda: [AgentConfig(id=DEFAULT_AGENT_ID)])
    bindings: list[ChatSettings] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_bindings(self) -> Self:
        agent_ids = map(lambda x: x.id, self.agents)
        agent_id_set = set(agent_ids)
        assert len(self.agents) >= 1, "At least one agent is required"
        assert DEFAULT_AGENT_ID in agent_id_set, "Default agent must be present"
        assert len(self.agents) == len(agent_id_set), "Agent ids must be unique"

        return self


def get_config_default_path() -> Path:
    return get_app_user_config_dir() / "config.toml"


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


def _load_config_toml(config_file: Path | None = None):
    config_file = config_file or get_config_default_path()
    if not config_file.exists():
        _ = load_config(config_file=config_file)

    config_text = config_file.read_text(encoding="utf-8")
    return config_file, tomlkit.loads(config_text)


def _save_config_toml(data, config_file: Path) -> None:
    with open(config_file, "w", encoding="utf-8") as f:
        tomlkit.dump(data, f)


def _require_table(data, key: str) -> Table:
    table = data.get(key)
    if not isinstance(table, Table):
        table = tomlkit.table()
        data[key] = table
    return table


def _ensure_aot(data, key: str) -> AoT:
    item = data.get(key)
    if isinstance(item, AoT):
        return item

    aot = tomlkit.aot()
    if isinstance(item, list):
        for old_item in item:
            if not isinstance(old_item, dict):
                continue
            table = tomlkit.table()
            for old_key, old_value in old_item.items():
                table[old_key] = old_value
            aot.append(table)

    data[key] = aot
    return aot


def update_api_config(api_id: int | None = None, api_hash: str | None = None, config_file: Path | None = None) -> None:
    config_file, data = _load_config_toml(config_file)

    if api_id is not None:
        data["api_id"] = api_id
    if api_hash is not None:
        data["api_hash"] = api_hash

    Config.model_validate(data)
    _save_config_toml(data, config_file)


def update_or_save_channel_config(channel_id: str, channel: ChannelSettings, config_file: Path | None = None) -> None:
    config_file, data = _load_config_toml(config_file)
    channels = _require_table(data, "channels")

    channel_item = tomlkit.item(channel.model_dump(mode="json", exclude_none=True))
    channels[channel_id] = channel_item

    data["channels"] = channels

    Config.model_validate(data)
    _save_config_toml(data, config_file)


def upsert_binding_config(channel_id: str, agent_id: str = DEFAULT_AGENT_ID, chat_ids: list[str] | None = None, config_file: Path | None = None) -> None:
    config_file, data = _load_config_toml(config_file)
    bindings = _ensure_aot(data, "bindings")

    if not isinstance(chat_ids, list):
        chat_ids = [SUSIE_CHAT_ALL_INDICATOR]

    target = None
    for item in bindings:
        if item.get("channel") != channel_id:
            continue
        raw_chat_ids = item.get("chat_ids", [SUSIE_CHAT_ALL_INDICATOR])
        existing_chat_ids = [raw_chat_ids] if isinstance(raw_chat_ids, str) else list(raw_chat_ids)
        if existing_chat_ids == chat_ids:
            target = item
            break

    if target is None:
        target = tomlkit.table()
        bindings.append(target)

    target["channel"] = channel_id
    target["agent"] = agent_id
    target["chat_ids"] = chat_ids

    Config.model_validate(data)
    _save_config_toml(data, config_file)


def delete_channel_config_by_id(channel_id: str, config_file: Path | None = None) -> None:
    config_file = config_file or get_config_default_path()

    if not config_file.exists():
        return

    config_text = config_file.read_text(encoding="utf-8")
    data = tomlkit.loads(config_text)

    channels = data.get("channels")

    if not isinstance(channels, Table):  # create channels entry if not exists
        raise ConfigError("Invalid channels entry.")

    channels.pop(channel_id, None)

    data["channels"] = channels

    with open(config_file, "w", encoding="utf-8") as f:
        tomlkit.dump(data, f)


def delete_channel_config(session_name: str, config_file: Path | None = None) -> None:
    delete_channel_config_by_session_name(session_name=session_name, config_file=config_file)


def delete_channel_config_by_session_name(session_name: str, config_file: Path | None = None) -> None:
    config_file, data = _load_config_toml(config_file)
    channels = _require_table(data, "channels")

    for key, item in list(channels.items()):
        if item.get("session_name") == session_name:
            channels.pop(key)
            break

    Config.model_validate(data)
    _save_config_toml(data, config_file)
