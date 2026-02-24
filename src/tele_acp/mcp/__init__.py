from __future__ import annotations

from typing import cast

from mcp.server.fastmcp import Context, FastMCP

from tele_acp.telegram import TGClient


class MCP(FastMCP):
    def __init__(self):
        super().__init__(name="Telegram MCP Server", json_response=True, port=9998)
        self._tg: TGClient | None = None

    def set_tg_client(self, tg: TGClient) -> None:
        self._tg = tg

    @property
    def tg(self) -> TGClient:
        if self._tg is None:
            raise RuntimeError("Telegram client is not bound to MCP server.")

        if not self._tg.is_connected:
            raise RuntimeError("Telegram client is not connected.")

        return self._tg


mcp_server = MCP()


@mcp_server.tool()
async def get_self(ctx: Context) -> str | None:
    """Get Self Information."""
    me = await cast(MCP, ctx.fastmcp).tg.get_user()
    if not me:
        return None
    return me.to_json()


@mcp_server.tool()
async def send_message(
    ctx: Context,
    entity: str | int,
    message: str,
    file: str | list[str] | None = None,
) -> str | None:
    """
    Send a message to a Telegram entity.

    Args:
        entity:
            The entity id.

            - `int`: treated as a peer ID (see https://core.telegram.org/api/peers#peer-id).
            - `str`: first try Telethon's resolver (username, phone, etc).
              If that fails, fall back to scanning dialogs and picking the *unique* match by:
              - dialog name contains `entity` (case-insensitive), or
              - dialog peer id equals `entity`, or
              - dialog entity id equals `entity`.

        message: The content string of the message.

        file:
            The file path.

            - `str`: single file path.
            - `list[str]`: multiple file paths.
            - `None`: no file.

    Return:
        The sent message if succeed.
    """

    tg = cast(MCP, ctx.fastmcp).tg

    msg = await tg.send_message(entity=entity, message=message, file=file)
    return msg.to_json()
