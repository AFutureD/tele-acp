import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich import print
from susie_core import DEFAULT_ASSISTANT_ID
from telegram_channel import TGClient, TGSession, format_me

from susie.settings import delete_channel_config_by_session_name, load_config

from .onboard import onboard_telegram_user_channel
from .shared import SharedArgs

auth_cli = typer.Typer(
    no_args_is_help=True,
    help="""
    Authenticate and Session Management.
    """,
)


@auth_cli.command(name="me")
def me_get(ctx: typer.Context) -> None:
    """Show the current authenticated Telegram account."""

    cli_args: SharedArgs = ctx.obj

    async def _run() -> bool:
        config = load_config(config_file=cli_args.config_file)
        tele_client = TGClient.create_simple(
            config.api_id,
            config.api_hash,
            cli_args.session,
            with_current=False,
        )

        async with tele_client as tg:
            me = await tg.get_user()

        if not me:
            return False

        print(format_me(me))
        return True

    ok = asyncio.run(_run())
    if not ok:
        raise typer.Exit(code=1)


@auth_cli.command(
    name="login",
    help="""
    Log in to Telegram and create a local session.

    Notes:
        If no session is active, the new session becomes active.
        If a session is already active, it remains active; the newly logged-in session is not activated unless you pass --switch.
    """,
)
def auth_login(
    ctx: typer.Context,
    channel_id: Annotated[str | None, typer.Option("--id", help="Login as channel using the provided channel ID.")] = None,
    use_qrcode: Annotated[bool, typer.Option("--qrcode", help="Login as user through Telegram QR-login flow.")] = False,
    switch_as_current: Annotated[
        bool,
        typer.Option("--switch", "-s", help="Automatic set the login session as active one."),
    ] = False,
):
    cli_args: SharedArgs = ctx.obj

    ok = asyncio.run(
        onboard_telegram_user_channel(
            cli_args=cli_args,
            channel_id=channel_id,
            use_qrcode=use_qrcode,
            switch_as_current=switch_as_current,
            bind=False,
            assistant_id=DEFAULT_ASSISTANT_ID,
            chat_ids=["*"],
        )
    )
    if not ok:
        raise typer.Exit(code=1)


@auth_cli.command(name="logout", help="Logout from the selected session.")
def auth_logout(ctx: typer.Context):
    cli_args: SharedArgs = ctx.obj

    async def _run() -> bool:
        config = load_config(config_file=cli_args.config_file)
        tele_client = TGClient.create_simple(
            config.api_id,
            config.api_hash,
            cli_args.session,
            with_current=False,
        )

        session = tele_client.session
        assert isinstance(session, TGSession), "Session must be a TGSession"

        session_name = Path(session.filename).stem

        async with tele_client:
            me = await tele_client.logout()

        delete_channel_config_by_session_name(session_name=session_name, config_file=cli_args.config_file)

        if me:
            print(f"Bye {format_me(me)}")
        return True

    ok = asyncio.run(_run())
    if not ok:
        raise typer.Exit(code=1)
