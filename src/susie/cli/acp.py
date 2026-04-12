from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from susie.acp.models import ACPRegistry, ACPRegistryAgent
from susie.acp.registry import ACPRegisteryManage, ACPRegisteryStatus, ACPRegistryCache

acp_cli = typer.Typer(
    no_args_is_help=True,
    help="""
    Manage ACP agents from the registry.
    """,
)

console = Console()


async def _prepare_manager(refresh: bool) -> tuple[ACPRegisteryManage, ACPRegistry]:
    cache = ACPRegistryCache()
    manager = ACPRegisteryManage(cache)

    registry = await cache.get_registry()
    if refresh or registry is None:
        registry = await cache.fetch_registery_and_cache()

    return manager, registry


def _build_status_rows(
    registry: ACPRegistry, statuses: Sequence[ACPRegisteryStatus], agents: Sequence[ACPRegistryAgent] | None = None
) -> list[tuple[ACPRegistryAgent, ACPRegisteryStatus]]:
    status_map = {status.acp_id: status for status in statuses}
    selected_agents = list(agents) if agents is not None else list(registry.agents)

    rows: list[tuple[ACPRegistryAgent, ACPRegisteryStatus]] = []
    for agent in sorted(selected_agents, key=lambda item: item.id):
        status = status_map.get(agent.id)
        if status is None:
            continue
        rows.append((agent, status))
    return rows


def _render_status_table(title: str, rows: Sequence[tuple[ACPRegistryAgent, ACPRegisteryStatus]]) -> None:
    table = Table(title=title)
    table.add_column("ACP ID", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Installed")
    table.add_column("Provider")
    table.add_column("Installed Version")
    table.add_column("Latest Version")
    table.add_column("Update")

    for agent, status in rows:
        table.add_row(
            agent.id,
            agent.name,
            "yes" if status.installed else "no",
            status.provider,
            status.version if status.installed else "-",
            agent.version,
            status.new_version or "-",
        )

    console.print(table)


def _exit_with_error(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


@acp_cli.command("list", help="List all ACP agents and their current status.")
def acp_list(
    refresh: Annotated[bool, typer.Option("--refresh", help="Refresh the cached ACP registry before listing.")] = False,
) -> None:
    async def _run() -> list[tuple[ACPRegistryAgent, ACPRegisteryStatus]]:
        manager, registry = await _prepare_manager(refresh)
        statuses = await manager.list_acp_status()
        return _build_status_rows(registry, statuses)

    try:
        rows = asyncio.run(_run())
    except RuntimeError as exc:
        _exit_with_error(str(exc))

    _render_status_table("ACP Agents", rows)


@acp_cli.command("search", help="Search ACP agents by acp-id or name.")
def acp_search(
    query: Annotated[str, typer.Argument(help="Search text matched against acp-id and name.")],
    refresh: Annotated[bool, typer.Option("--refresh", help="Refresh the cached ACP registry before searching.")] = False,
) -> None:
    async def _run() -> list[tuple[ACPRegistryAgent, ACPRegisteryStatus]]:
        manager, registry = await _prepare_manager(refresh)
        statuses = await manager.list_acp_status()
        query_text = query.casefold()
        matched_agents = [agent for agent in registry.agents if query_text in agent.id.casefold() or query_text in agent.name.casefold()]
        return _build_status_rows(registry, statuses, matched_agents)

    try:
        rows = asyncio.run(_run())
    except RuntimeError as exc:
        _exit_with_error(str(exc))

    if not rows:
        console.print(f"No ACP agents matched `{query}`.")
        raise typer.Exit()

    _render_status_table(f"Search: {query}", rows)


@acp_cli.command("install", help="Install an ACP agent by registry id.")
def acp_install(
    acp_id: Annotated[str, typer.Argument(help="ACP registry id to install.")],
    refresh: Annotated[bool, typer.Option("--refresh", help="Refresh the cached ACP registry before install.")] = False,
) -> None:
    async def _run() -> None:
        manager, _ = await _prepare_manager(refresh)
        await manager.install_acp(acp_id)

    try:
        asyncio.run(_run())
    except RuntimeError as exc:
        _exit_with_error(str(exc))

    console.print(f"Installed ACP agent `{acp_id}`.")


@acp_cli.command("update", help="Update one ACP agent, or all installed ACP agents when no id is given.")
def acp_update(
    acp_id: Annotated[str | None, typer.Argument(help="Optional ACP registry id to update.")] = None,
    refresh: Annotated[bool, typer.Option("--refresh", help="Refresh the cached ACP registry before update.")] = False,
) -> None:
    async def _run() -> list[str]:
        manager, _ = await _prepare_manager(refresh)
        targets: list[str]

        if acp_id is not None:
            targets = [acp_id]
        else:
            statuses = await manager.list_acp_status()
            targets = [status.acp_id for status in statuses if status.installed]

        for target in targets:
            await manager.install_acp(target)

        return targets

    try:
        updated = asyncio.run(_run())
    except RuntimeError as exc:
        _exit_with_error(str(exc))

    if not updated:
        console.print("No installed ACP agents to update.")
        raise typer.Exit()

    console.print(f"Updated {len(updated)} ACP agent(s): {', '.join(updated)}")


@acp_cli.command("uninstall", help="Uninstall an ACP agent.")
def acp_uninstall(
    acp_id: Annotated[str, typer.Argument(help="ACP registry id to uninstall.")],
    refresh: Annotated[bool, typer.Option("--refresh", help="Refresh the cached ACP registry before uninstall.")] = False,
) -> None:
    async def _run() -> None:
        manager, _ = await _prepare_manager(refresh)
        await manager.uninstall_acp(acp_id)

    try:
        asyncio.run(_run())
    except RuntimeError as exc:
        _exit_with_error(str(exc))

    console.print(f"Uninstalled ACP agent `{acp_id}`.")
