from telethon import types


def peer_id_into_chat_id(peer_id: types.TypePeer) -> str:
    match peer_id:
        case types.PeerUser():
            return f"U{peer_id.user_id}"
        case types.PeerChat():
            return f"G{peer_id.chat_id}"
        case types.PeerChannel():
            return f"C{peer_id.channel_id}"


def chat_id_into_peer_id(chat_id: str) -> types.TypePeer | str:
    if chat_id == "":
        return chat_id

    type_str = chat_id[0].upper()
    id_str = chat_id.removeprefix(type_str)

    match type_str:
        case "U":
            return types.PeerUser(int(id_str))
        case "C":
            return types.PeerChat(int(id_str))
        case "G":
            return types.PeerChannel(int(id_str))
        case _:
            return chat_id
