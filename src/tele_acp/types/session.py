from pathlib import Path

from pydantic import BaseModel, Field


class SessionInfo(BaseModel):
    path: Path = Field(exclude=True)
    session_name: str = Field(...)
    user_id: int = Field(...)
    user_name: str | None = Field(...)
    user_phone: str | None = Field(...)
    user_display_name: str | None = Field(...)
