import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich import print
from telegram_channel import TGClient, TGSession, format_me

from susie.config import delete_channel_config_by_session_name, load_config

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
            agent_id="default",
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


# @auth_cli.command(name="list", help="List all local Telegram sessions.")
# def auth_list(ctx: typer.Context):
#     cli_args: SharedArgs = ctx.obj

#     async def _run() -> bool:
#         session_name_list = await list_session_name()
#         config = load_config(config_file=cli_args.config_file)

#         session_info_list = []
#         for session_name in session_name_list:
#             tg = TGClient.create(session_name=session_name, config=config)
#             async with tg as tg:
#                 session_info = await tg.get_session_info()
#             if session_info is None:
#                 continue
#             session_info_list.append(session_info)

#         print(format_session_info_list(session_info_list, fmt=cli_args.fmt), fmt=cli_args.fmt)
#         return True

#     ok = asyncio.run(_run())
#     if not ok:
#         raise typer.Exit(code=1)


# @auth_cli.command(
#     name="authorizations",
#     help="""
#     List active Telegram authorizations (sessions/devices) for the current account.
#     """,
# )
# def auth_authorizations(ctx: typer.Context):
#     cli_args: SharedArgs = ctx.obj

#     async def _run() -> bool:
#         app = TGClient.create(session_name=cli_args.session, config=load_config(config_file=cli_args.config_file))
#         authorizations = await app.get_authorizations()
#         print(utils.fmt.format_authorizations(authorizations, cli_args.fmt), fmt=cli_args.fmt)
#         return True

#     ok = asyncio.run(_run())
#     if not ok:
#         raise typer.Exit(code=1)


# @auth_cli.command(
#     name="switch",
#     help="""
#     Switch the active Telegram account.

#     This command switches the active session used by subsequent commands.

#     To list authenticated accounts, run `tele auth list`.
#     """,
# )
# def auth_switch(
#     ctx: typer.Context,
#     user_id: Annotated[
#         int | None,
#         typer.Option("--uid", help="Telegram user peer id to switch to (e.g. 7820000665)."),
#     ] = None,
#     username: Annotated[
#         str | None,
#         typer.Option(help="Telegram username to switch to (e.g. @alice)."),
#     ] = None,
#     session_name: Annotated[
#         str | None,
#         typer.Option("--session", help="Session name to use (as shown in `tele auth list`)."),
#     ] = None,
# ):
#     cli_args: SharedArgs = ctx.obj

#     if username and username.startswith("@"):
#         username = username.removeprefix("@")

#     async def _run() -> bool:
#         if not user_id and not username and not session_name:
#             raise typer.BadParameter("Provide at least one of: user_id, username, or session.")

#         session__name_list = await list_session_name()

#         client_lists = [await TGClient.create(session_name=session, config=load_config(config_file=cli_args.config_file)) for session in session__name_list]

#         async def predicator(app: TGClient) -> bool:
#             session_info = await app.get_session_info()
#             if session_info is None:
#                 return False

#             cond_1 = True if session_name and session_name == session_info.session_name else False
#             cond_2 = True if username and username == session_info.user_name else False
#             cond_3 = True if user_id and user_id == session_info.user_id else False

#             return cond_1 or cond_2 or cond_3

#         client_lists = [s for s in client_lists if await predicator(s)]

#         if len(client_lists) == 0:
#             raise typer.BadParameter("No Session Matched")

#         if len(client_lists) > 1:
#             raise typer.BadParameter("Multiple Sessions Matched")

#         session = client_lists[0].get_session()
#         if not session:
#             return False
#         session_switch(session=session)

#         return True

#     ok = asyncio.run(_run())
#     if not ok:
#         raise typer.Exit(code=1)
