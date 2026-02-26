from __future__ import annotations

from pathlib import Path


def get_app_user_defualt_dir() -> Path:
    """Get the application default directory path."""
    # TODO: respect XDG and other enviroment variable.
    share_dir = Path.home() / ".config" / "tele"
    share_dir.mkdir(parents=True, exist_ok=True)
    return share_dir
