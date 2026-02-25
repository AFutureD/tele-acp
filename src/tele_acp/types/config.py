from pydantic import BaseModel, Field


class Config(BaseModel):
    api_id: int = Field(default=0, description="Telegram api_id")
    api_hash: str = Field(default="", description="Telegram api_hash")
    dialog_idle_timeout_minutes: int = Field(default=30, ge=1, description="Idle timeout for per-dialog context")
