import asyncio
from typing import Annotated

import typer

from tele_acp import utils
from tele_acp.config import load_config
from tele_acp.session import TGSession, list_session_name, session_switch
from tele_acp.telegram import TGClient
from tele_acp.utils import print
from tele_acp.utils.fmt import format_session_info_list

from .types import SharedArgs

auth_cli = typer.Typer(
    no_args_is_help=True,
    help="""
    Authenticate and Session Management.
    """,
)


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
    switch_as_current: Annotated[
        bool,
        typer.Option("--switch", "-s", help="Automatic set the login session as active one."),
    ] = False,
):
    cli_args: SharedArgs = ctx.obj

    def get_phone() -> str:
        print(
            """
            Telegram login requires your phone number.

            1. Enter your Telegram phone number with [bold green]country code[/bold green].
            2. Telegram will send a [bold green]login[/bold green] code to your Telegram app (from the official [bold red]Telegram account[/bold red]).
            3. Enter that [bold green]code[/bold green] in the next step.
            4. Your [bold green]password[/bold green] will be asked, if Two-Step Verification is enabled (Settings → Privacy and Security).

            [bold red]IMPORTANT: Your input will not be stored or shared.[/bold red]

            Example: 8615306541234

            """,
            fmt=cli_args.fmt,
        )

        return typer.prompt("Please enter phone number", type=str)

    def get_code() -> str:
        return typer.prompt("Please enter login code", type=str)

    def get_password() -> str:
        return typer.prompt("Please enter your password", type=str, hide_input=True)

    async def _run() -> bool:
        tg = await TGClient.create(
            session_name=cli_args.session,
            config=load_config(config_file=cli_args.config_file),
            with_current=False,
        )

        me = await tg.login(phone=get_phone, code=get_code, password=get_password)
        if not me:
            return False

        session = tg.session
        if switch_as_current and isinstance(session, TGSession):
            session_switch(session=session)

        print(f"Hi {utils.fmt.format_me(me, cli_args.fmt)}", fmt=cli_args.fmt)
        return True

    ok = asyncio.run(_run())
    if not ok:
        raise typer.Exit(code=1)


@auth_cli.command(name="logout", help="Logout from the selected session.")
def auth_logout(ctx: typer.Context):
    cli_args: SharedArgs = ctx.obj

    async def _run() -> bool:
        tg = await TGClient.create(session_name=cli_args.session, config=load_config(config_file=cli_args.config_file))

        me = await tg.logout()
        if me:
            print(f"Bye {utils.fmt.format_me(me, cli_args.fmt)}", fmt=cli_args.fmt)
        return True

    ok = asyncio.run(_run())
    if not ok:
        raise typer.Exit(code=1)


@auth_cli.command(name="list", help="List all local Telegram sessions.")
def auth_list(ctx: typer.Context):
    cli_args: SharedArgs = ctx.obj

    async def _run() -> bool:
        session_name_list = await list_session_name()
        config = load_config(config_file=cli_args.config_file)

        session_info_list = []
        for session_name in session_name_list:
            tg = await TGClient.create(session_name=session_name, config=config)
            async with tg as tg:
                session_info = await tg.get_session_info()
            if session_info is None:
                continue
            session_info_list.append(session_info)

        print(format_session_info_list(session_info_list, fmt=cli_args.fmt), fmt=cli_args.fmt)
        return True

    ok = asyncio.run(_run())
    if not ok:
        raise typer.Exit(code=1)


@auth_cli.command(
    name="authorizations",
    help="""
    List active Telegram authorizations (sessions/devices) for the current account.
    """,
)
def auth_authorizations(ctx: typer.Context):
    cli_args: SharedArgs = ctx.obj

    async def _run() -> bool:
        app = await TGClient.create(session_name=cli_args.session, config=load_config(config_file=cli_args.config_file))
        authorizations = await app.get_authorizations()
        print(utils.fmt.format_authorizations(authorizations, cli_args.fmt), fmt=cli_args.fmt)
        return True

    ok = asyncio.run(_run())
    if not ok:
        raise typer.Exit(code=1)


@auth_cli.command(
    name="switch",
    help="""
    Switch the active Telegram account.

    This command switches the active session used by subsequent commands.

    To list authenticated accounts, run `tele auth list`.
    """,
)
def auth_switch(
    ctx: typer.Context,
    user_id: Annotated[
        int | None,
        typer.Option("--uid", help="Telegram user peer id to switch to (e.g. 7820000665)."),
    ] = None,
    username: Annotated[
        str | None,
        typer.Option(help="Telegram username to switch to (e.g. @alice)."),
    ] = None,
    session_name: Annotated[
        str | None,
        typer.Option("--session", help="Session name to use (as shown in `tele auth list`)."),
    ] = None,
):
    cli_args: SharedArgs = ctx.obj

    if username and username.startswith("@"):
        username = username.removeprefix("@")

    async def _run() -> bool:
        if not user_id and not username and not session_name:
            raise typer.BadParameter("Provide at least one of: user_id, username, or session.")

        session__name_list = await list_session_name()

        client_lists = [await TGClient.create(session_name=session, config=load_config(config_file=cli_args.config_file)) for session in session__name_list]

        async def predicator(app: TGClient) -> bool:
            session_info = await app.get_session_info()
            if session_info is None:
                return False

            cond_1 = True if session_name and session_name == session_info.session_name else False
            cond_2 = True if username and username == session_info.user_name else False
            cond_3 = True if user_id and user_id == session_info.user_id else False

            return cond_1 or cond_2 or cond_3

        client_lists = [s for s in client_lists if await predicator(s)]

        if len(client_lists) == 0:
            raise typer.BadParameter("No Session Matched")

        if len(client_lists) > 1:
            raise typer.BadParameter("Multiple Sessions Matched")

        session = client_lists[0].get_session()
        if not session:
            return False
        session_switch(session=session)

        return True

    ok = asyncio.run(_run())
    if not ok:
        raise typer.Exit(code=1)
