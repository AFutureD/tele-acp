from pydantic import BaseModel, Field

from .agent import AgentConfig
from .channel import Channel, DialogBind, TelegramChannel


class Config(BaseModel):
    api_id: int = Field(description="Telegram api_id")
    api_hash: str = Field(description="Telegram api_hash")
    dialog_idle_timeout_minutes: int = Field(default=30, ge=1, description="Idle timeout for per-dialog context")

    channel: list[Channel] = [TelegramChannel()]
    agents: list[AgentConfig] = [AgentConfig()]
    binding: list[DialogBind] = []
