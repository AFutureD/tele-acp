from pydantic import BaseModel, Field

DEFAULT_AGENT_ID = "default"


class AgentConfig(BaseModel):
    id: str = Field(description="The id of the agent")
    acp_id: str = Field(default="codex-acp", description="The acp id which agent will use")
    work_dir: str | None = None
    forward_to: str | None = Field(default=None, description="Peer used for report messages of this binding")
