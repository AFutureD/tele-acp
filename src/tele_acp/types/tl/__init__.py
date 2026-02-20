from telethon import types


def peer_hash_into_str(peer_id: types.TypePeer) -> str:
    match peer_id:
        case types.PeerUser():
            return f"U{peer_id.user_id}"
        case types.PeerChat():
            return f"G{peer_id.chat_id}"
        case types.PeerChannel():
            return f"C{peer_id.channel_id}"
