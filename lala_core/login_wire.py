"""Legacy 1262 C63-7/S63-7 codec: OFFLINE regression only.

The client uses a single-byte XOR obfuscation (0xAD), NOT cryptographic
encryption. Do not send current passwords using these packets until both the
current official endpoint identity AND protocol are independently verified.
No socket, no CLI, no logging, no persistent credentials.
"""
from dataclasses import dataclass
import struct

from .login import LoginError, validate_credentials
from .wire import ObservedPacket, ReadOnlyFrameDecoder, WireDecodeError


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
