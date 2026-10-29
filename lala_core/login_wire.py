"""Legacy 1262 C63-7/S63-7 codec: OFFLINE regression only.

The client uses a single-byte XOR obfuscation (0xAD), NOT cryptographic
encryption. Do not send current passwords using these packets until both the
current official endpoint identity AND protocol are independently verified.
No socket, no CLI, no logging, no persistent credentials.
"""
from dataclasses import dataclass
import struct

from .login import LoginError, validate_credentials
from .wire import ObservedPacket, ReadOnlyFrameDecoder, WireDecodeError, ReadOnlyReader


OLD_RX_XOR = OLD_TX_XOR = 0xAD
OLD_PLATFORM = 3
OLD_LANGUAGE = 0


@dataclass(frozen=True, slots=True)
class LegacyLoginReply:
    kind: int
    result: int
    accepted: bool
    verified_current_server: bool = False


def build_legacy_request(account: str, password: str, *,
                         kind: int = 0) -> bytes:
    """Generate an old-protocol candidate frame in memory (no network send)."""
    validate_credentials(account, password)
    if type(kind) is not int or kind not in (0, 2):
        raise LoginError("舊版登入種類必須為帳號驗證 0 或正式登入 2")
    a, p = account.encode("ascii"), password.encode("ascii")
    payload = (
        bytes((kind, 0, OLD_PLATFORM, OLD_LANGUAGE, len(a)))
        + a + bytes((len(p),)) + p
    )
    body = bytes((63, 7)) + payload
    if len(body) > 65535:
        raise LoginError("舊版登入封包長度超限")
    plain = b"\xc4\xc6" + struct.pack("<H", len(body)) + body
    return bytes(b ^ OLD_TX_XOR for b in plain)


def decode_legacy_reply(packet: ObservedPacket, *, expected_kind: int
                        ) -> LegacyLoginReply:
    """Strictly recognize S63-7 result+login kind; fail on unknown extensions."""
    if not isinstance(packet, ObservedPacket) or (packet.main, packet.sub) != (63, 7):
        raise WireDecodeError("不是舊版登入結果封包")
    if type(expected_kind) is not int or expected_kind not in (0, 2):
        raise WireDecodeError("預期登入種類不合法")
    if len(packet.payload) != 2:
        raise WireDecodeError("舊版 S63-7 結果欄位長度不符")
    result, kind = packet.payload
    if kind != expected_kind:
        raise WireDecodeError("舊版登入結果種類與請求不符")
    return LegacyLoginReply(kind=kind, result=result,
                            accepted=result == 0)


def decoder_for_legacy_fixture() -> ReadOnlyFrameDecoder:
    """Not a current-live protocol adapter; deliberately requires explicit name."""
    return ReadOnlyFrameDecoder(xor_key=OLD_RX_XOR, profile="legacy-1262")


def parse_legacy_role_slots(packet: ObservedPacket) -> tuple[int, ...]:
    """Read-only, exact old S63-1 role records; names and account data discarded.

    The old client selects role *slots* 1/2, never guessed character IDs.
    This is not proof that the present-day official server uses this schema.
    """
    if not isinstance(packet, ObservedPacket) or (packet.main, packet.sub) != (63, 1):
        raise WireDecodeError("不是舊版角色清單")
    r = ReadOnlyReader(packet.payload)
    slots = []
    while r.remaining:
        if len(slots) >= 2:
            raise WireDecodeError("舊版角色清單槽位數超過限制")
        slot = r.u8()
        if slot not in (1, 2) or slot in slots:
            raise WireDecodeError("舊版角色槽位錯誤或重複")
        chars = r.u8()
        if chars % 2:
            raise WireDecodeError("舊版角色名稱 UTF-16LE 長度不合法")
        try:
            r.take(chars).decode("utf-16le")
        except UnicodeDecodeError as exc:
            raise WireDecodeError("舊版角色名稱編碼錯誤") from exc
        # Old layout: level, element, four HP/SP values, exp, gold,
        # sex/head/palettes/degree/job; discard all private details.
        r.take(1 + 1 + 4*4 + 8 + 4 + 1 + 1 + 4 + 4 + 1 + 1)
        r.u16()  # stage ID; no trust in the current official layout
        r.take(8)  # delete time double, uninterpreted
        locked = r.u8()
        if locked not in (0, 1):
            raise WireDecodeError("舊版角色鎖定旗標不合法")
        # 1262 role_list bonuses: four u32, u16, two i32, two u32.
        r.take(4*4 + 2 + 4*2 + 4*2)
        slots.append(slot)
    return tuple(sorted(slots))
