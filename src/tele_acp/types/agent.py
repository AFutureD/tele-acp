from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    id: str = Field(default="default", description="The id of the agent")
    acp_id: str = Field(default="codex", description="The acp id which agent will use")
    work_dir: str | None = None
