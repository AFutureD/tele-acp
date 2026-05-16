from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ACPRegistryBinary(BaseModel):
    archive: str
    cmd: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class ACPRegistryPackageDistribution(BaseModel):
    package: str
    args: list[str] = Field(default_factory=list)


class ACPRegistryDistributionPlatformTarget(str, Enum):
    DARWIN_AARCH64 = "darwin-aarch64"
    """macOS Apple Silicon"""

    DARWIN_X86_64 = "darwin-x86_64"
    """macOS Intel"""

    LINUX_AARCH64 = "linux-aarch64"
    """Linux ARM64"""

    LINUX_X86_64 = "linux-x86_64"
    """Linux x86_64"""

    WINDOWNS_AARCH64 = "windows-aarch64"
    """Windows ARM64"""

    WINDOWNS_X86_64 = "windows-x86_64"
    """Windows x86_64"""


class ACPRegistryDistribution(BaseModel):
    binary: dict[ACPRegistryDistributionPlatformTarget, ACPRegistryBinary] | None = None
    npx: ACPRegistryPackageDistribution | None = None
    uvx: ACPRegistryPackageDistribution | None = None


class ACPRegistryAgent(BaseModel):
    id: str
    name: str
    version: str
    description: str
    distribution: ACPRegistryDistribution


class ACPRegistry(BaseModel):
    version: str
    agents: list[ACPRegistryAgent]


class ACPPlatform(BaseModel):
    os: str
    arch: str
    key: str
