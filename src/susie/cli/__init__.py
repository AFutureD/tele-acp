from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer

from susie.constant import VERSION
from susie.logger import configure_logging

from .acp import acp_cli
from .auth import auth_cli
from .mainloop import mainloop
from .shared import SharedArgs

cli = typer.Typer(
    epilog="Made by Huanan",
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="""
    Tele-ACP

    Chat with agents on Telegram through ACP.

    Quick Start:

    1. tele auth login
    2. tele auth me
    3. tele dialog list
    4. tele message list <dialog_id> -n 20

    WARNING: DO NOT SUPPORT BOT FOR NOW.
    """,
)
cli.add_typer(auth_cli, name="auth")
cli.add_typer(acp_cli, name="acp")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"tele-cli, version {VERSION}")
        raise typer.Exit()


@cli.callback()
def main(
    ctx: typer.Context,
    # meta
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
    # shared args
    config_file: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Path to config TOML file. \\[default: ~/.config/tele/config.toml]",
            file_okay=True,
            writable=True,
            readable=True,
            resolve_path=True,
        ),
    ] = None,
    session: Annotated[
        str | None,
        typer.Option(help="Session name. List via `tele auth list`. \\[default: Current]"),
    ] = None,
) -> None:
    """Hei Hei"""
    _ = version

    ctx.obj = SharedArgs(config_file=config_file, session=session)

    log_level = logging.INFO if ctx.invoked_subcommand == "start" else logging.WARN
    configure_logging(log_level)


@cli.command(name="start")
def start(ctx: typer.Context) -> None:
    cli_args: SharedArgs = ctx.obj

    ok = asyncio.run(mainloop(cli_args))
    if not ok:
        raise typer.Exit(code=1)
