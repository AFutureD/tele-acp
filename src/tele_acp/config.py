from __future__ import annotations

from pathlib import Path

import tomlkit
from pydantic import ValidationError
from tomlkit.exceptions import TOMLKitError

from .shared import get_app_user_defualt_dir
from .types import Config, ConfigError


def get_config_default_path() -> Path:
    return get_app_user_defualt_dir() / "config.toml"


def get_config_default() -> Config:
    return Config(api_id=611335, api_hash="d524b414d21f4d37f08684c1df41ac9c")


def save_config(config: Config, config_file: Path):
    config_file.parent.mkdir(parents=True, exist_ok=True)

    with open(config_file, "w", encoding="utf-8") as f:
        tomlkit.dump(config.model_dump(mode="json"), f)


def load_config(config_file: Path | None = None) -> Config:
    config_file = config_file or get_config_default_path()

    if not config_file.exists():
        config = get_config_default()
        save_config(config=config, config_file=config_file)
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
