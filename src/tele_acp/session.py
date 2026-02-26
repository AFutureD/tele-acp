import uuid
from pathlib import Path

from telethon.sessions import SQLiteSession

from tele_acp.shared import get_app_user_defualt_dir

from .types import CurrentSessionPathNotValidError


class TGSession(SQLiteSession):
    pass


def get_app_session_folder() -> Path:
    ret = get_app_user_defualt_dir() / "sessions"
    ret.mkdir(parents=True, exist_ok=True)
    return ret


def get_app_session_current() -> Path:
    return get_app_session_folder() / "Current.session"


def _get_session_path(session_name: str | None, with_current: bool) -> Path:
    if session_name:
        return get_app_session_folder() / session_name

    current = get_app_session_current()
    if with_current and current.exists():
        return current

    return get_app_session_folder() / str(uuid.uuid4())


def load_session(session_name: str | None, with_current: bool = True) -> TGSession:
    session_path = _get_session_path(session_name=session_name, with_current=with_current)
    return TGSession(str(session_path))


def session_ensure_current_valid(session: object = None) -> None:
    """Check if current session path is symlink, throw error if not.
    check if current session is point to a valid session path, and remove if not valid.
    create a current session path if it does not exist and point to given session path.

    notice: this function will not switch to the give session if current session has pointed to a valid session.
    """
    path = get_app_session_current()
    if path.exists() and not path.is_symlink():
        raise CurrentSessionPathNotValidError()

    # skip, if a current session is exists
    # notice: we do not validate session's state for now.
    if path.exists():
        return

    # force unlink
    path.unlink(missing_ok=True)

    if not isinstance(session, TGSession):
        return

    # before perform create the symlink of current session path,
    # we should check the session path is valid.
    session_path = Path(session.filename)
    if not session_path.exists():
        return

    path.symlink_to(session_path)


async def list_session_name() -> list[str]:
    folder = get_app_session_folder()
    session_name_list = [item.stem for item in folder.glob("*.session") if not item.is_symlink() and item.is_file()]
    return session_name_list


def session_switch(session: TGSession) -> None:
    session_path = Path(session.filename)

    if not session_path.exists():
        return

    path = get_app_session_current()
    path.unlink(missing_ok=True)

    path.symlink_to(session_path)
