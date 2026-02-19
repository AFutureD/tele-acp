from dataclasses import dataclass
from pathlib import Path

from tele_acp.types import Format


@dataclass
class SharedArgs:
    fmt: Format
    config_file: Path | None
    session: str | None
