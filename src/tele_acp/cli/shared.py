from pathlib import Path

from pydantic.dataclasses import dataclass


@dataclass
class SharedArgs:
    config_file: Path | None
    session: str | None
