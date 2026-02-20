from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from tele_acp.config import load_config
from tele_acp.constant import VERSION
from tele_acp.telegram import TGClient
from tele_acp.types import Format
from tele_acp.utils import fmt, print

from .auth import auth_cli
from .mainloop import mainloop
from .types import SharedArgs

cli = typer.Typer(
    epilog="Made by Huanan",
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="""
    The Telegram CLI.

    Quick Start:

    1. tele auth login
    2. tele me
    3. tele dialog list
    4. tele message list <dialog_id> -n 20

    WARNING: DO NOT SUPPORT BOT FOR NOW.
    """,
)
cli.add_typer(auth_cli, name="auth")


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
    fmt: Annotated[
        Format,
        typer.Option("--format", "-f", help="Output format."),
    ] = Format.text,
) -> None:
    """Hei Hei"""
    _ = version

    ctx.obj = SharedArgs(fmt=fmt, config_file=config_file, session=session)


@cli.command(name="me")
def me_get(ctx: typer.Context) -> None:
    """
    Show the current authenticated Telegram account.
    """

    cli_args: SharedArgs = ctx.obj

    async def _run() -> bool:
        tg = await TGClient.create(session_name=cli_args.session, config=load_config(config_file=cli_args.config_file))

        async with tg as tg:
            me = await tg.get_user()

        if not me:
            return False

        print(fmt.format_me(me, cli_args.fmt), fmt=cli_args.fmt)
        return True

    ok = asyncio.run(_run())
    if not ok:
        raise typer.Exit(code=1)


@cli.command(name="start")
def start(ctx: typer.Context) -> None:
    cli_args: SharedArgs = ctx.obj

    ok = asyncio.run(mainloop(cli_args))
    if not ok:
        raise typer.Exit(code=1)
