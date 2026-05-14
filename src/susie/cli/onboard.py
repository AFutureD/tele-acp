from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Annotated, Any

import qrcode
import typer
from rich import print
from susie_core import DEFAULT_AGENT_ID
from telegram_bot_channel import TelegramBotChannelSettings
from telegram_channel import TelegramChannelSettings, TGClient, TGSession, format_me, session_switch

from susie.config import load_config, update_or_save_channel_config, upsert_binding_config

from .shared import SharedArgs

onboard_cli = typer.Typer(
    no_args_is_help=True,
    help="""
    Onboard channels into Susie.
    """,
)


def _get_phone() -> str:
    print(
        """
        Telegram login requires your phone number.

        1. Enter your Telegram phone number with [bold green]country code[/bold green].
        2. Telegram will send a [bold green]login[/bold green] code to your Telegram app.
        3. Enter that [bold green]code[/bold green] in the next step.
        4. Your [bold green]password[/bold green] will be asked, if Two-Step Verification is enabled.

        [bold red]IMPORTANT: Your input will not be stored or shared.[/bold red]

        Example: 8615306541234
        """
    )

    return typer.prompt("Please enter phone number", type=str)


def _get_code() -> str:
    return typer.prompt("Please enter login code", type=str)


def _get_password() -> str:
    return typer.prompt("Please enter your password", type=str, hide_input=True)


def _format_qrcode_ascii(data: str) -> str:
    buffer = io.StringIO()
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make(fit=True)
    qr.print_ascii(out=buffer, tty=False, invert=True)
    return buffer.getvalue().rstrip()


def _show_qrcode(qr_login: Any) -> None:
    expires_at = qr_login.expires.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    qrcode_ascii = _format_qrcode_ascii(qr_login.url)

    print(
        f"""
        Telegram QR login requires a Telegram app that is [bold green]already logged in[/bold green].

        1. Open Telegram on another logged-in device.
        2. Open the login-by-QR flow in Telegram and scan the ASCII QR code below.
        3. Approve the login request in Telegram.
        4. Your [bold green]password[/bold green] will be asked if Two-Step Verification is enabled.

        [bold red]IMPORTANT: This login payload expires at {expires_at}.[/bold red]
        """
    )
    typer.echo(qrcode_ascii)
    print(f"\nRaw login URL: [bold cyan]{qr_login.url}[/bold cyan]")


async def onboard_telegram_user_channel(
    cli_args: SharedArgs,
    channel_id: str | None,
    use_qrcode: bool,
    switch_as_current: bool,
    bind: bool,
    agent_id: str,
    chat_ids: list[str],
) -> bool:
    config = load_config(config_file=cli_args.config_file)
    tele_client = TGClient.create_simple(
        config.api_id,
        config.api_hash,
        cli_args.session,
        with_current=False,
    )

    try:
        if use_qrcode:
            me = await tele_client.login_as_qrcode(password=_get_password, on_qrcode=_show_qrcode)
        else:
            me = await tele_client.login_as_user(phone=_get_phone, code=_get_code, password=_get_password)
    except Exception as e:
        print(f"Login failed: {e}")
        return False

    if not me:
        return False

    session = tele_client.session
    assert isinstance(session, TGSession), "Session must be a TGSession"

    if switch_as_current:
        session_switch(session=session)

    session_name = Path(session.filename).stem
    resolved_channel_id = channel_id or me.username or str(me.id)
    channel = TelegramChannelSettings(session_name=session_name)

    update_or_save_channel_config(resolved_channel_id, channel=channel, config_file=cli_args.config_file)
    if bind:
        upsert_binding_config(resolved_channel_id, agent_id=agent_id, chat_ids=chat_ids, config_file=cli_args.config_file)

    print(f"Onboarded telegram_user channel `{resolved_channel_id}` for {format_me(me)}")
    return True


@onboard_cli.command(
    name="telegram_user",
    help="""
    Onboard a Telegram user-account channel.

    Notes:
        If no session is active, the new session becomes active.
        If a session is already active, it remains active; the newly logged-in session is not activated unless you pass --switch.
    """,
)
def telegram_user(
    ctx: typer.Context,
    channel_id: Annotated[str | None, typer.Option("--id", help="Use the provided channel ID instead of the Telegram username/user id.")] = None,
    use_qrcode: Annotated[bool, typer.Option("--qrcode", help="Login as user through Telegram QR-login flow.")] = False,
    switch_as_current: Annotated[
        bool,
        typer.Option("--switch", "-s", help="Automatic set the login session as active one."),
    ] = False,
    bind: Annotated[bool, typer.Option("--bind/--no-bind", help="Create or update a default binding for this channel.")] = True,
    agent_id: Annotated[str, typer.Option("--agent", help="Agent id used by the default binding.")] = DEFAULT_AGENT_ID,
    chat_ids: Annotated[list[str] | None, typer.Option("--chat-id", help="Chat id matched by the default binding.")] = None,
) -> None:
    cli_args: SharedArgs = ctx.obj

    ok = asyncio.run(
        onboard_telegram_user_channel(
            cli_args=cli_args,
            channel_id=channel_id,
            use_qrcode=use_qrcode,
            switch_as_current=switch_as_current,
            bind=bind,
            agent_id=agent_id,
            chat_ids=chat_ids or ["*"],
        )
    )
    if not ok:
        raise typer.Exit(code=1)


@onboard_cli.command(
    name="telegram_bot",
    help="""
    Onboard a Telegram Bot API channel.
    """,
)
def telegram_bot(
    ctx: typer.Context,
    channel_id: Annotated[str, typer.Argument(help="Channel ID used in Susie's config and bindings.")],
    token: Annotated[str | None, typer.Option("--token", help="Telegram Bot API token. Prompts when omitted.")] = None,
    whitelist: Annotated[list[str] | None, typer.Option("--whitelist", help="Allowed private user id. Use '*' to allow all.")] = None,
    bind: Annotated[bool, typer.Option("--bind/--no-bind", help="Create or update a default binding for this channel.")] = True,
    agent_id: Annotated[str, typer.Option("--agent", help="Agent id used by the default binding.")] = DEFAULT_AGENT_ID,
    chat_ids: Annotated[list[str] | None, typer.Option("--chat-id", help="Chat id matched by the default binding.")] = None,
    drop_pending_updates: Annotated[bool, typer.Option("--drop-pending-updates", help="Drop pending bot updates when polling starts.")] = False,
) -> None:
    cli_args: SharedArgs = ctx.obj
    resolved_token = token or typer.prompt("Please enter Telegram Bot API token", type=str, hide_input=True)

    channel = TelegramBotChannelSettings(
        token=resolved_token,
        whitelist=whitelist or ["*"],
        drop_pending_updates=drop_pending_updates,
    )
    update_or_save_channel_config(channel_id, channel=channel, config_file=cli_args.config_file)
    if bind:
        upsert_binding_config(channel_id, agent_id=agent_id, chat_ids=chat_ids or ["*"], config_file=cli_args.config_file)

    print(f"Onboarded telegram_bot channel `{channel_id}`")
