from __future__ import annotations

import asyncio
import json
import logging
import platform
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

import aiohttp
from pydantic import BaseModel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from susie.shared import get_app_user_data_dir

from .client import ACPAgentConfig
from .models import (
    ACPRegistry,
    ACPRegistryAgent,
    ACPRegistryDistributionPlatformTarget,
)

ACP_REGISTRY_URL = "https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json"
ACP_BINARY_MANIFEST_FILE = "install.json"


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
        self._cache = registry
        return registry

    async def get_registry(self) -> ACPRegistry | None:
        if cache := self._cache:
            return cache

        # we do not fetch it from network,
        # the downloaded archive may not match the registry.json
        registry = self._read_cached_registry()
        self._cache = registry
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


class ACPBinaryInstallManifest(BaseModel):
    acp_id: str
    version: str
    archive: str
    cmd: str


class ACPRegisteryManage:
    def __init__(self, registry_cache: ACPRegistryCache) -> None:
        self._registry_cache = registry_cache

    async def initial(self) -> None:
        await self._registry_cache.fetch_registery_and_cache()

    async def get_agent_config(self, acp_id: str) -> ACPAgentConfig | None:
        agent = await self._registry_cache.get_agent(acp_id)
        if agent is None:
            return None

        distribution = agent.distribution

        if binary := distribution.binary:
            platform = binary.get(get_normalized_bin_key())
            if platform is None:
                raise RuntimeError(f"ACP agent `{acp_id}` does not support platform `{get_normalized_bin_key().value}`.")

            path = self._get_managed_binary_path(acp_id, platform.cmd)
            if path is None:
                raise RuntimeError(f"ACP agent `{acp_id}` is not installed.")

            return ACPAgentConfig(id=acp_id, name=agent.name, acp_path=str(path), acp_args=platform.args)

        if npx := distribution.npx:
            if shutil.which("npx") is None:
                raise RuntimeError("`npx` is required but not available on PATH.")
            return ACPAgentConfig(id=acp_id, name=agent.name, acp_path="npx", acp_args=[npx.package] + npx.args)

        if uvx := distribution.uvx:
            if shutil.which("uvx") is None:
                raise RuntimeError("`uvx` is required but not available on PATH.")
            return ACPAgentConfig(id=acp_id, name=agent.name, acp_path="uvx", acp_args=[uvx.package] + uvx.args)

        raise RuntimeError(f"ACP agent `{acp_id}` has no supported distribution.")

    async def list_acp_status(self) -> list[ACPRegisteryStatus]:
        registry = await self._registry_cache.require_registery()

        statuses: list[ACPRegisteryStatus] = []
        for agent in registry.agents:
            status = await self._get_agent_status(agent)
            statuses.append(status)

        return statuses

    async def install_acp(self, acp_id: str) -> None:
        """
        install acp agent

        if distribution is binary, install in `~/.local/share/susie/acp/agents/<acp_id>`
        if distribution is npx or uvx, call `npx` or `uvx` to install
        """
        agent = await self._registry_cache.get_agent(acp_id)
        if agent is None:
            raise RuntimeError(f"ACP agent `{acp_id}` not found in registry.")

        distribution = agent.distribution
        if binary := distribution.binary:
            platform = binary.get(get_normalized_bin_key())
            if platform is None:
                raise RuntimeError(f"ACP agent `{acp_id}` does not support platform `{get_normalized_bin_key().value}`.")

            await self._install_binary_agent(agent, platform.archive, platform.cmd)
            return

        if npx := distribution.npx:
            if shutil.which("npm") is None:
                raise RuntimeError("`npm` is required to install npx-based ACP agents.")
            await self._run_command("npm", "install", "--global", "--yes", npx.package)
            return

        if uvx := distribution.uvx:
            if shutil.which("uv") is None:
                raise RuntimeError("`uv` is required to install uvx-based ACP agents.")
            await self._run_command("uv", "tool", "install", uvx.package)
            return

        raise RuntimeError(f"ACP agent `{acp_id}` has no installable distribution.")

    async def uninstall_acp(self, acp_id: str) -> None:
        """remove acp agent"""
        agent = await self._registry_cache.get_agent(acp_id)
        if agent is None:
            raise RuntimeError(f"ACP agent `{acp_id}` not found in registry.")

        distribution = agent.distribution
        if distribution.binary:
            install_dir = self._get_agent_install_dir(acp_id)
            if install_dir.exists():
                shutil.rmtree(install_dir)
            return

        if npx := distribution.npx:
            if shutil.which("npm") is None:
                raise RuntimeError("`npm` is required to uninstall npx-based ACP agents.")
            await self._run_command("npm", "uninstall", "--global", self._get_npm_package_name(npx.package))
            return

        if uvx := distribution.uvx:
            if shutil.which("uv") is None:
                raise RuntimeError("`uv` is required to uninstall uvx-based ACP agents.")
            await self._run_command("uv", "tool", "uninstall", self._get_uv_tool_name(uvx.package))
            return

        raise RuntimeError(f"ACP agent `{acp_id}` has no uninstallable distribution.")

    async def _get_agent_status(self, agent: ACPRegistryAgent) -> ACPRegisteryStatus:
        distribution = agent.distribution
        if binary := distribution.binary:
            platform = binary.get(get_normalized_bin_key())
            if platform is None:
                return ACPRegisteryStatus(acp_id=agent.id, installed=False, provider="susie", version=agent.version, new_version=None)

            manifest = self._read_binary_manifest(agent.id)
            managed_path = self._get_managed_binary_path(agent.id, platform.cmd)
            if managed_path is not None:
                installed_version = manifest.version if manifest is not None else agent.version
                return ACPRegisteryStatus(
                    acp_id=agent.id,
                    installed=True,
                    provider="susie",
                    version=installed_version,
                    new_version=agent.version if installed_version != agent.version else None,
                )

            return ACPRegisteryStatus(acp_id=agent.id, installed=False, provider="susie", version=agent.version, new_version=None)

        if npx := distribution.npx:
            installed = await self._is_npm_package_installed(npx.package)
            return ACPRegisteryStatus(acp_id=agent.id, installed=installed, provider="npx", version=agent.version, new_version=None)

        if uvx := distribution.uvx:
            installed = await self._is_uv_tool_installed(uvx.package)
            return ACPRegisteryStatus(acp_id=agent.id, installed=installed, provider="uvx", version=agent.version, new_version=None)

        raise RuntimeError(f"ACP agent `{agent.id}` has no supported distribution.")

    async def _install_binary_agent(self, agent: ACPRegistryAgent, archive_url: str, cmd: str) -> None:
        install_dir = self._get_agent_install_dir(agent.id)
        install_dir.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=self._registry_cache.acp_root_dir) as temp_dir:
            archive_path = Path(temp_dir) / "archive"

            async with aiohttp.ClientSession() as session, session.get(archive_url) as response:
                response.raise_for_status()
                await self._download_archive(response, archive_path, agent.id)

            if install_dir.exists():
                shutil.rmtree(install_dir)

            install_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._extract_archive(archive_path, install_dir)
                binary_path = self._resolve_binary_path(install_dir, cmd)
                if not binary_path.exists():
                    raise RuntimeError(f"Installed ACP binary not found at `{binary_path}`.")
                if get_normalized_os() != "windows":
                    binary_path.chmod(binary_path.stat().st_mode | 0o111)

                manifest = ACPBinaryInstallManifest(acp_id=agent.id, version=agent.version, archive=archive_url, cmd=cmd)
                self._get_binary_manifest_path(agent.id).write_text(
                    json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
                    encoding="utf-8",
                )
            except Exception:
                shutil.rmtree(install_dir, ignore_errors=True)
                raise

    async def _download_archive(self, response: aiohttp.ClientResponse, archive_path: Path, acp_id: str) -> None:
        total = response.content_length
        progress = Progress(
            TextColumn("[bold blue]Downloading[/bold blue]"),
            TextColumn("{task.fields[acp_id]}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        )

        with progress, archive_path.open("wb") as file:
            task_id = progress.add_task("download", total=total, acp_id=acp_id)
            async for chunk in response.content.iter_chunked(64 * 1024):
                file.write(chunk)
                progress.update(task_id, advance=len(chunk))

    async def _run_command(self, *args: str) -> None:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
            raise RuntimeError(message or f"Command failed: {' '.join(args)}")

    async def _is_npm_package_installed(self, package_spec: str) -> bool:
        if shutil.which("npm") is None:
            return False

        package_name = self._get_npm_package_name(package_spec)
        process = await asyncio.create_subprocess_exec(
            "npm",
            "list",
            "--global",
            "--depth=0",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return False

        payload = json.loads(stdout.decode("utf-8"))
        dependencies = payload.get("dependencies", {})
        return package_name in dependencies

    async def _is_uv_tool_installed(self, package_spec: str) -> bool:
        if shutil.which("uv") is None:
            return False

        tool_name = self._get_uv_tool_name(package_spec)
        process = await asyncio.create_subprocess_exec(
            "uv",
            "tool",
            "list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return False

        lines = [line.strip() for line in stdout.decode("utf-8").splitlines()]
        return any(line.startswith(f"{tool_name} ") or line == tool_name for line in lines)

    def _get_agent_install_dir(self, acp_id: str) -> Path:
        return self._registry_cache.acp_agents_dir / acp_id

    def _get_binary_manifest_path(self, acp_id: str) -> Path:
        return self._get_agent_install_dir(acp_id) / ACP_BINARY_MANIFEST_FILE

    def _read_binary_manifest(self, acp_id: str) -> ACPBinaryInstallManifest | None:
        manifest_path = self._get_binary_manifest_path(acp_id)
        if not manifest_path.exists():
            return None
        return ACPBinaryInstallManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    def _get_managed_binary_path(self, acp_id: str, cmd: str) -> Path | None:
        install_dir = self._get_agent_install_dir(acp_id)
        path = self._resolve_binary_path(install_dir, cmd)
        if not path.exists():
            return None
        return path

    def _resolve_binary_path(self, install_dir: Path, cmd: str) -> Path:
        path = (install_dir / cmd).resolve()
        try:
            path.relative_to(install_dir.resolve())
        except ValueError as exc:
            raise RuntimeError(f"ACP binary command `{cmd}` escapes install directory.") from exc
        return path

    def _extract_archive(self, archive_path: Path, destination: Path) -> None:
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    self._ensure_archive_path_safe(destination, member.filename)
                archive.extractall(destination)
            return

        if tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path) as archive:
                for member in archive.getmembers():
                    self._ensure_archive_path_safe(destination, member.name)
                archive.extractall(destination, filter="data")
            return

        raise RuntimeError(f"Unsupported ACP archive format: `{archive_path.name}`")

    def _ensure_archive_path_safe(self, destination: Path, member_name: str) -> None:
        resolved = (destination / member_name).resolve()
        try:
            resolved.relative_to(destination.resolve())
        except ValueError as exc:
            raise RuntimeError(f"Unsafe archive entry: `{member_name}`") from exc

    def _get_command_name(self, cmd: str) -> str:
        return Path(cmd).name

    def _get_npm_package_name(self, package_spec: str) -> str:
        spec = package_spec.strip()
        if spec.startswith("@"):
            second_at = spec.find("@", 1)
            return spec if second_at == -1 else spec[:second_at]
        return spec.split("@", 1)[0]

    def _get_uv_tool_name(self, package_spec: str) -> str:
        spec = package_spec.strip()
        for token in ("==", ">=", "<=", "!=", "~=", "@", ";", " ", "<", ">", "="):
            index = spec.find(token)
            if index > 0:
                spec = spec[:index]
                break
        return spec.split("[", 1)[0]
