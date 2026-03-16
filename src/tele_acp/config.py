from __future__ import annotations

from pathlib import Path

import tomlkit
from pydantic import ValidationError
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import AoT

from .shared import get_app_user_defualt_dir
from .types import Config, ConfigError, TypeTelegramChannel


def get_config_default_path() -> Path:
    return get_app_user_defualt_dir() / "config.toml"


def get_config_default() -> Config:
    return Config(api_id=611335, api_hash="d524b414d21f4d37f08684c1df41ac9c")


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


def update_or_save_channel_config(channel: TypeTelegramChannel, config_file: Path | None = None):
    config_file = config_file or get_config_default_path()

    if not config_file.exists():
        return

    config_text = config_file.read_text(encoding="utf-8")
    data = tomlkit.loads(config_text)

    channels = data.get("channels")

    if not isinstance(channels, AoT):  # create channels entry if not exists
        if (channels is None) or (isinstance(channels, list) and len(channels) == 0):
            channels = tomlkit.aot()
        else:
            raise ConfigError("Invalid channels entry.")

    for index, item in enumerate(list(channels)):
        if item.get("id") != channel.id:
            continue
        del channels[index]
        break

    channel_item = tomlkit.item(channel.model_dump(mode="json", exclude_none=True))
    channels.append(channel_item)

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

    if channels is None:
        channels = tomlkit.aot()

    for index, item in enumerate(list(channels)):
        if item.get("session_name") != session_name:
            continue
        del channels[index]
        break

    data["channels"] = channels

    with open(config_file, "w", encoding="utf-8") as f:
        tomlkit.dump(data, f)
