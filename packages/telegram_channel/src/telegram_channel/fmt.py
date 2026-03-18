import arrow
import telethon
from tele_acp_core import SessionInfo
from telethon.tl.tlobject import _json_default
from telethon.tl.types import TypeAuthorization

from tele_acp.utils.output import get_str_len_for_int


def json_default_callback(value):
    return _json_default(value)


def format_me(me: telethon.types.User) -> str:
    return telethon.utils.get_display_name(me)


def _format_session_info_to_str(x: SessionInfo) -> str:
    username = f"@{x.user_name}" if x.user_name else "unknown"
    return f"{x.user_id: <12} {x.user_display_name or 'unknown'} ({username}) {x.session_name}"


def format_session_info_list(session_info_list: list[SessionInfo]) -> str:
    return "\n".join([_format_session_info_to_str(obj) for obj in session_info_list])


def _format_authorization_to_str(x: telethon.types.Authorization, max_hash_len: int, max_device_model_len: int) -> str:
    is_current = x.current or False
    current = ">" if is_current else " "

    date_active = x.date_active and arrow.get(x.date_active).humanize()

    return f"{current} [{x.hash: <{max_hash_len}}] {date_active:14} {x.device_model: <{max_device_model_len}} - {x.app_name} {x.app_version} "


def format_authorizations(authorizations: telethon.types.account.Authorizations) -> str:
    max_hash_len = max(list(map(lambda x: get_str_len_for_int(x.hash), authorizations.authorizations)))
    max_device_model_len = max(list(map(lambda x: len(x.device_model), authorizations.authorizations)))

    auths: list[TypeAuthorization] = authorizations.authorizations
    rows = [_format_authorization_to_str(item, max_hash_len, max_device_model_len) for item in auths]
    return "\n".join(rows)
