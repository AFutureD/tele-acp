from __future__ import annotations

from pathlib import Path

from .constant import NAME


def get_app_user_config_dir() -> Path:
    """Get the application config directory path."""
    # TODO: respect XDG and other environment variable.
    path = Path.home() / ".config" / NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_app_user_data_dir() -> Path:
    """Get the application data directory path."""
    # TODO: respect XDG and other environment variable.
    path = Path.home() / ".local" / "share" / NAME
    path.mkdir(parents=True, exist_ok=True)
    return path
