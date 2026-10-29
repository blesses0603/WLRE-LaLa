"""只讀取觀察到的舊版二進位框架；不含編碼、send 或登入功能。

1262 格式為舊版 LaLa 參考，不代表目前官方資料包／伺服器協定相容。
輸入可以來自*受控離線測試*；此模組不開 socket、不儲存封包。
"""
from dataclasses import dataclass
import struct


class WireDecodeError(ValueError):
    """Frame invalid; never include raw contents or credentials in the error."""


MAX_PAYLOAD = 65535
MAX_BUFFER = MAX_PAYLOAD + 4


@dataclass(frozen=True, slots=True)
class ObservedPacket:
    main: int
    sub: int
    payload: bytes


class ReadOnlyFrameDecoder:
    """Bounded 1262 XOR frame reader. No outbound encoder intentionally exists."""

    def __init__(self, *, xor_key: int, profile: str):
        if profile != "legacy-1262":
            raise WireDecodeError("未核對目前正式服框架，不能啟用此解碼器")
        if type(xor_key) is not int or not 0 <= xor_key <= 255:
            raise WireDecodeError("解碼參數無效")
        self._xor = xor_key
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> tuple[ObservedPacket, ...]:
        if not isinstance(chunk, bytes):
            raise WireDecodeError("封包片段型態無效")
        # Streaming chunks can contain multiple frames. Iterate without ever
        # retaining more than one bounded partial frame in memory.
        produced = []
        for offset in range(0, len(chunk), MAX_BUFFER):
            part = chunk[offset:offset + MAX_BUFFER]
            self._buffer.extend(value ^ self._xor for value in part)
            while len(self._buffer) >= 4:
                if self._buffer[:2] != b"\xc4\xc6":
                    self._buffer.clear()
                    raise WireDecodeError("未知框架標頭，拒絕繼續解析")
                body_len = struct.unpack_from("<H", self._buffer, 2)[0]
                if body_len < 2:
                    self._buffer.clear()
                    raise WireDecodeError("框架長度不足")
                end = 4 + body_len
                if len(self._buffer) < end:
                    break
                produced.append(ObservedPacket(
                    self._buffer[4], self._buffer[5],
                    bytes(self._buffer[6:end]),
                ))
                del self._buffer[:end]
            if len(self._buffer) > MAX_BUFFER:
                self._buffer.clear()
                raise WireDecodeError("未完成框架超過安全長度上限")
        return tuple(produced)

    def finish(self) -> None:
        if self._buffer:
            size = len(self._buffer)
            self._buffer.clear()
            raise WireDecodeError(f"不完整框架，殘留 {size} 位元組")

    def reset(self) -> None:
        self._buffer.clear()


class ReadOnlyReader:
    """Bounded little-endian reader; private fields never leave parser."""

    def __init__(self, data: bytes):
        if not isinstance(data, bytes) or len(data) > MAX_PAYLOAD:
            raise WireDecodeError("事件資料長度無效")
        self._data = data
        self._offset = 0

    @property
    def remaining(self) -> int:
        return len(self._data) - self._offset

    def take(self, size: int) -> bytes:
        if type(size) is not int or size < 0 or size > self.remaining:
            raise WireDecodeError("封包欄位截斷")
        start = self._offset
        self._offset += size
        return self._data[start:self._offset]

    def _number(self, size: int, *, signed=False) -> int:
        return int.from_bytes(self.take(size), "little", signed=signed)

    def u8(self) -> int: return self._number(1)
    def u16(self) -> int: return self._number(2)
    def u32(self) -> int: return self._number(4)
    def i64(self) -> int: return self._number(8, signed=True)

    def end(self) -> None:
        if self.remaining:
            raise WireDecodeError("封包資料尾端有未知欄位，拒絕套用")
