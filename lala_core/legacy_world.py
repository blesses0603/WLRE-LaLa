"""Strict offline/experimental decoder of S3-1 world-player snapshot.

Reviewed against legacy WLRe_lala/wlre/network/layouts.py::world_player.
No server I/O, no credentials, no disk writes. The old 1262 layout has not
been independently certified for the current official protocol.
"""
from dataclasses import dataclass
from .wire import ObservedPacket, ReadOnlyReader, WireDecodeError


@dataclass(frozen=True, slots=True)
class LegacyWorldPlayer:
    role_id: int
    character_name: str
    scene: int
    x: int
    y: int
    schema: str = "legacy-1262"
    official_identity_verified: bool = False


def _unicode8(r: ReadOnlyReader, *, max_length=255) -> str:
    length = r.u8()
    if length > max_length or length % 2:
        raise WireDecodeError("舊版角色文字長度無效")
    try:
        return r.take(length).decode("utf-16le", errors="strict").rstrip("\x00")
    except UnicodeError as exc:
        raise WireDecodeError("舊版角色文字編碼不符") from None


def parse_legacy_world_player(packet: ObservedPacket) -> LegacyWorldPlayer:
    """Validate entire S3-1 packet, not merely its first ten bytes.

    Consume equipment, appearance, signature and contact-card fields without
    retaining them; expose only the local player's role/scene/coordinates.
    """
    if not isinstance(packet, ObservedPacket) or (packet.main, packet.sub) != (3, 1):
        raise WireDecodeError("不是舊版 S3-1 角色資料封包")
    r = ReadOnlyReader(packet.payload)
    role_id = r.u32()
    r.u8()  # sex, not exposed
    scene, x, y = r.u16(), r.u16(), r.u16()
    r.take(3)   # face, head, body
    r.take(8)   # appearance palettes
    r.take(2)   # header frame, second-job effect
    equips = r.u8()
    if equips > 32:
        raise WireDecodeError("角色裝備欄位數超出安全上限")
    r.take(equips * 6)  # id u16 + design id u32
    name = _unicode8(r, max_length=128)
    r.take(8)   # namecard fields; never persisted
    _unicode8(r)  # private signature, discarded
    r.u16()     # title ID
    r.end()     # no unknown extensions silently accepted
    if role_id == 0 or not name or any(ord(c) < 32 for c in name):
        raise WireDecodeError("角色編號或名稱無效")
    return LegacyWorldPlayer(role_id, name, scene, x, y)
