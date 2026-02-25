from pydantic.dataclasses import dataclass
from .client import ACPClient

__all__ = ["ACPClient"]


# curl https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json
# https://github.com/agentclientprotocol/registry/blob/main/agent.schema.json


@dataclass
class ACPAgentConfig:
    id: str
    name: str
    acp_path: str
    acp_args: list[str]
