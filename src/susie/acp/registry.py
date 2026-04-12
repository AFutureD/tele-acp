from __future__ import annotations

import json
import logging
import platform
import shutil
import sys
from pathlib import Path
from typing import Literal

import aiohttp
from pydantic import BaseModel

from susie.shared import get_app_user_data_dir

from .client import ACPAgentConfig
from .models import (
    ACPRegistry,
    ACPRegistryAgent,
    ACPRegistryDistributionPlatformTarget,
)

ACP_REGISTRY_URL = "https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json"


def get_normalized_os() -> str:
    value = sys.platform
    if value.startswith("darwin"):
        return "darwin"
    if value.startswith("linux"):
        return "linux"
    if value.startswith("win"):
        return "windows"
    raise RuntimeError(f"Unsupported operating system for ACP registry: {value}")


def get_normalized_arch() -> str:
    arch = platform.machine()

    match arch:
        case "x86_64" | "AMD64":
            return "x86_64"
        case "arm64":
            return "aarch64"
        case _:
            raise RuntimeError(f"Unsupported architecture for ACP registry: {arch}")


def get_normalized_bin_key() -> ACPRegistryDistributionPlatformTarget:
    match (get_normalized_os(), get_normalized_arch()):
        case ("darwin", "aarch64"):
            return ACPRegistryDistributionPlatformTarget.DARWIN_AARCH64
        case ("darwin", "x86_64"):
            return ACPRegistryDistributionPlatformTarget.DARWIN_X86_64
        case ("linux", "aarch64"):
            return ACPRegistryDistributionPlatformTarget.LINUX_AARCH64
        case ("linux", "x86_64"):
            return ACPRegistryDistributionPlatformTarget.LINUX_X86_64
        case _:
            raise RuntimeError("Unsupported platform target")


class ACPRegistryCache:
    def __init__(
        self,
        *,
        data_root: Path | None = None,
        registry_url: str = ACP_REGISTRY_URL,
        logger: logging.Logger | None = None,
    ) -> None:
        self._data_root = data_root or get_app_user_data_dir()
        self._registry_url = registry_url
        self.logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.acp_root_dir = self._data_root / "acp"

        self.acp_registry_dir = self.acp_root_dir / "registry"
        self.acp_registry_file_path = self.acp_registry_dir / "registry.json"
        self.acp_agents_dir = self.acp_root_dir / "agents"

        self._cache: ACPRegistry | None = None

    async def fetch_registery_and_cache(self) -> ACPRegistry:
        async with aiohttp.ClientSession() as session, session.get(self._registry_url) as response:
            response.raise_for_status()
            payload = await response.text()

        registry = ACPRegistry.model_validate_json(payload)
        self._write_registry_cache(registry)
        return registry

    async def get_registry(self) -> ACPRegistry | None:
        if cache := self._cache:
            return cache

        # we do not fetch it from network,
        # the downloaded archive may not match the registry.json
        registry = self._read_cached_registry()
        self._cachce = registry
        return registry

    async def require_registery(self) -> ACPRegistry:
        registry = await self.get_registry()
        if registry is None:
            raise RuntimeError("No ACP registry available.")
        return registry

    async def list_agent_id(self) -> list[str]:
        registry = await self.require_registery()
        return [agent.id for agent in registry.agents]

    async def get_agent(self, acp_id: str) -> ACPRegistryAgent | None:
        registry = await self.require_registery()
        agent = next((agent for agent in registry.agents if agent.id == acp_id), None)
        return agent

    async def get_agent_config(self, acp_id: str) -> ACPAgentConfig | None:
        registry = await self.require_registery()
        agent = next((agent for agent in registry.agents if agent.id == acp_id), None)
        if agent is None:
            return None

        distribution = agent.distribution

        if binary := distribution.binary:
            platform = binary.get(get_normalized_bin_key())
            if platform is None:
                raise RuntimeError()

            path = self.acp_agents_dir / acp_id / platform.cmd
            path = path.resolve()
            if not path.exists():
                raise RuntimeError()

            return ACPAgentConfig(id=acp_id, name=agent.name, acp_path=platform.cmd, acp_args=platform.args)

        if npx := distribution.npx:
            if shutil.which("npx") is None:
                raise RuntimeError()
            return ACPAgentConfig(id=acp_id, name=agent.name, acp_path="npx", acp_args=[npx.package] + npx.args)

        if uvx := distribution.uvx:
            if shutil.which("uvx") is None:
                raise RuntimeError()
            return ACPAgentConfig(id=acp_id, name=agent.name, acp_path="uvx", acp_args=[uvx.package] + uvx.args)

        raise RuntimeError()

    def _read_cached_registry(self) -> ACPRegistry | None:
        if not self.acp_registry_file_path.exists():
            return None
        return ACPRegistry.model_validate_json(self.acp_registry_file_path.read_text(encoding="utf-8"))

    def _write_registry_cache(self, registry: ACPRegistry) -> None:
        self.acp_registry_dir.mkdir(parents=True, exist_ok=True)
        self.acp_registry_file_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")


class ACPRegisteryStatus(BaseModel):
    acp_id: str
    installed: bool
    provider: Literal["susie", "uvx", "npx"]
    version: str
    new_version: str | None


class ACPRegisteryManage:
    def __init__(self, registry_cache: ACPRegistryCache) -> None:
        self._registry_cache = registry_cache

    async def initial(self) -> None:
        await self._registry_cache.fetch_registery_and_cache()

    async def list_acp_status(self) -> list[ACPRegisteryStatus]:
        return []

    async def install_acp(self, acp_id: str) -> None:
        """
        install acp agent

        if distribution is binary, install in `~/.local/share/susie/acp/agents/<acp_id>`
        if distribution is npx or uvx, call `npx` or `uvx` to install
        """
        pass

    async def uninstall_acp(self, acp_id: str) -> None:
        """remove acp agent"""
        pass
