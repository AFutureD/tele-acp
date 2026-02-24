import inspect
import sqlite3
import typing
from pathlib import Path
from sre_compile import SUBPATTERN
from typing import Callable

import telethon
from telethon import hints
from telethon.errors import RPCError
from telethon.tl.functions.account import GetAuthorizationsRequest

from tele_acp import types
from tele_acp.session import TGSession, load_session, session_ensure_current_valid
from tele_acp.utils.fmt import format_me


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
        if not isinstance(self.session, TGSession):
            return None
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

    async def send_message(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        entity: hints.EntityLike,
        message: hints.MessageLike = "",
        *,
        reply_to: None | int | telethon.types.Message = None,
        attributes: list[telethon.types.TypeDocumentAttribute] | None = None,
        parse_mode: str | None = None,
        formatting_entities: None | typing.List[telethon.types.TypeMessageEntity] = None,
        link_preview: bool = True,
        file: hints.FileLike | list[hints.FileLike] | None = None,
        thumb: hints.FileLike | None = None,
        force_document: bool = False,
        clear_draft: bool = False,
        buttons: hints.MarkupLike | None = None,
        silent: bool | None = None,
        background: bool | None = None,
        supports_streaming: bool = False,
        schedule: "hints.DateLike" = None,
        comment_to: int | telethon.types.Message | None = None,
        nosound_video: bool | None = None,
        send_as: hints.EntityLike | None = None,
        message_effect_id: int | None = None,
    ) -> types.Message:
        """
        Send a message to a Telegram entity.

        entity resolution:
        - `int`: treated as a peer ID (see https://core.telegram.org/api/peers#peer-id).
        - `str`: first try Telethon's resolver (username, phone, etc).
          If that fails, fall back to scanning dialogs and picking the *unique* match by:
          - dialog name contains `receiver` (case-insensitive), or
          - dialog peer id equals `receiver`, or
          - dialog entity id equals `receiver`.
        """

        async def _resolve_entity(target: str | int) -> hints.EntityLike:
            # Fast path: let Telethon resolve usernames/phones/IDs without scanning dialogs.
            try:
                return await self.get_input_entity(target)
            except Exception:
                pass

            # NOTICE: do not convert str to int by default.
            #         the phone and the peer_id can not be determined.

            # if input is int, it must be peer_id, and we do not need do any matching.
            if isinstance(target, int):
                return target

            # Fallback: scan dialogs for a unique match (avoid building the full list).
            target_norm = target.casefold()
            async for dialog in self.iter_dialogs():
                name = (dialog.name or "").casefold()
                if target_norm and target_norm in name:
                    return dialog.entity

                if str(dialog.id) == target or str(dialog.entity.id) == target:
                    return dialog.entity

            # If no match found, return the original target
            return target

        if isinstance(entity, str) or isinstance(entity, int):
            entity = await _resolve_entity(entity)

        return await super().send_message(
            entity=entity,
            message=message,
            reply_to=reply_to,  # type: ignore[arg-type]
            attributes=attributes,  # type: ignore[arg-type]
            parse_mode=parse_mode,
            formatting_entities=formatting_entities,
            link_preview=link_preview,
            file=file,  # type: ignore[arg-type]
            thumb=thumb,  # type: ignore[arg-type]
            force_document=force_document,
            clear_draft=clear_draft,
            buttons=buttons,
            silent=silent,  # type: ignore[arg-type]
            background=background,  # type: ignore[arg-type]
            supports_streaming=supports_streaming,
            schedule=schedule,
            comment_to=comment_to,  # type: ignore[arg-type]
            nosound_video=nosound_video,  # type: ignore[arg-type]
            send_as=send_as,
            message_effect_id=message_effect_id,
        )
