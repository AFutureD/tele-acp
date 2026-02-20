import json

from tele_acp.types import Format, SessionInfo
import telethon
import arrow
from telethon.tl.tlobject import _json_default

from .output import get_str_len_for_int


def json_default_callback(value):
    return _json_default(value)


def format_me(me: telethon.types.User, fmt: None | Format = None) -> str:
    output_fmt = fmt or Format.text
    match output_fmt:
        case Format.text:
            return telethon.utils.get_display_name(me)
        case Format.json:
            return json.dumps(me.to_json(), ensure_ascii=False)


def _format_session_info_to_str(x: SessionInfo) -> str:
    username = f"@{x.user_name}" if x.user_name else "unknown"
    return f"{x.user_id: <12} {x.user_display_name or 'unknown'} ({username}) {x.session_name}"


def format_session_info_list(session_info_list: list[SessionInfo], fmt: None | Format = None) -> str:
    output_fmt = fmt or Format.text

    match output_fmt:
        case Format.text:
            return "\n".join([_format_session_info_to_str(obj) for obj in session_info_list])
        case Format.json:
            obj_list = [item.model_dump(mode="json") for item in session_info_list]
            return json.dumps(obj_list, ensure_ascii=False)


def _format_authorization_to_str(x: telethon.types.Authorization, max_hash_len: int, max_device_model_len: int) -> str:
    is_current = x.current or False
    current = ">" if is_current else " "

    date_active = x.date_active and arrow.get(x.date_active).humanize()

    return f"{current} [{x.hash: <{max_hash_len}}] {date_active:14} {x.device_model: <{max_device_model_len}} - {x.app_name} {x.app_version} "


def format_authorizations(
    authorizations: telethon.types.account.Authorizations,
    fmt: None | Format = None,
) -> str:
    output_fmt = fmt or Format.text

    match output_fmt:
        case Format.text:
            max_hash_len = max(list(map(lambda x: get_str_len_for_int(x.hash), authorizations.authorizations)))
            max_device_model_len = max(list(map(lambda x: len(x.device_model), authorizations.authorizations)))

            rows = [_format_authorization_to_str(item, max_hash_len, max_device_model_len) for item in authorizations.authorizations]
            return "\n".join(rows)
        case Format.json:
            return json.dumps(authorizations.to_dict(), default=json_default_callback, ensure_ascii=False)
