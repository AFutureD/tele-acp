from pathlib import Path
import sqlite3
from typing import Callable
from tele_acp import types
from tele_acp.session import TGSession, load_session, session_ensure_current_valid
from tele_acp.utils.fmt import format_me
import telethon
import inspect

from telethon.errors import RPCError
from telethon.tl.functions.account import GetAuthorizationsRequest


class TGClient(telethon.TelegramClient):
    @staticmethod
    async def create(session_name: str | None, config: types.Config, with_current: bool = True) -> TGClient:
        session: TGSession = load_session(session_name, with_current=with_current)

        return TGClient(
            session=session,
            api_id=config.api_id,
            api_hash=config.api_hash,
        )

    async def _start_without_login(self) -> "TGClient":
        if not self.is_connected():
            await self.connect()
        return self

    async def __aenter__(self):
        """
        override super `__aenter__` to avoid login process.
        """
        return await self._start_without_login()

    def get_session(self) -> TGSession | None:
        return self.session

    async def get_user(self) -> telethon.types.User | None:
        await self.is_user_authorized()
        me = await self.get_me()
        return me if isinstance(me, telethon.types.User) else None

    async def get_authorizations(self) -> telethon.types.account.Authorizations:
        result = await self(GetAuthorizationsRequest())

        return result

    async def logout(self) -> telethon.types.User | None:
        me = await self.get_me()
        await self.log_out()
        session_ensure_current_valid(session=None)
        return me if isinstance(me, telethon.types.User) else None

    async def login(
        self,
        phone: Callable[[], str],
        code: Callable[[], str],
        password: Callable[[], str],
    ) -> telethon.types.User | None:
        try:
            result = self.start(phone=phone, password=password, code_callback=code)
            if inspect.isawaitable(result):
                await result
            me = await self.get_me()

            session_ensure_current_valid(session=self.session)

            return me if isinstance(me, telethon.types.User) else None
        except RPCError:
            session_ensure_current_valid(session=None)
        except KeyboardInterrupt:
            session_ensure_current_valid(session=None)

    async def get_session_info(self) -> types.SessionInfo | None:
        try:
            me = await self.get_user()
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).casefold():
                return None

        if not me:
            return None
        session = self.session

        if not isinstance(session, TGSession):
            return None

        session_path = Path(session.filename)

        return types.SessionInfo(
            path=session_path,
            session_name=session_path.stem,
            user_id=me.id,
            user_name=me.username,
            user_phone=me.phone,
            user_display_name=format_me(me),
        )
