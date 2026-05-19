from pydantic import BaseModel, ConfigDict, Field

DEFAULT_ASSISTANT_ID = "default"


class AssistantConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="The id of the assistant")
    agent_id: str = Field(default="codex", description="The agent id which assistant will use")
    work_dir: str | None = None
    forward_to: str | None = Field(default=None, description="Peer used for report messages of this binding")


class AgentModelOption(BaseModel):
    value: str = Field(description="The value to set for the model option")
    name: str = Field(description="The display name of the model option")
