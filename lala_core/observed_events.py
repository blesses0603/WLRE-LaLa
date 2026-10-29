"""舊版 1262 已知事件的唯讀投影。新版本未獨立驗證前僅供離線測試。

拒絕截斷與額外欄位；絕不將角色暱稱、密碼、聊天或原始封包回傳。
"""
from dataclasses import dataclass
import math
import struct
from .wire import ObservedPacket, ReadOnlyReader, WireDecodeError


@dataclass(frozen=True, slots=True)
class ObservedEvent:
    category: str
    kind: str
    values: tuple[tuple[str, int], ...] = ()
    slots: tuple[tuple[int, int, int], ...] = ()
    # Always explicitly distinguish from game-server certification.
    authoritative: bool = False


def _item(r: ReadOnlyReader, index: int) -> tuple[int, int, int]:
    """Read 1262 S23 item layout but project ONLY slot/item/count.

    Non-display fields are consumed, not cached; no assumptions about 1286.
    """
    item_id = r.u16()
    count = r.u8()
    r.take(1 + 1 + 4)  # damage, serial version, serial
    r.take(4 + 4)  # durable, firing
    r.take(2)  # magic spar
    available, limited = struct.unpack("<dd", r.take(16))
    if not (math.isfinite(available) and math.isfinite(limited)):
        raise WireDecodeError("物品有效時間欄位異常")
    r.take(1 + 1 + 2)  # beat, differ, modeling
    r.take(2)  # get_item_id
    r.take(1 + 2 + 4)  # saddle, enhance, design
    r.take(4 * 3)  # plugins
    r.take(1 + 1 + 1 + 1)  # lock, star kind/level, show message
    if not 1 <= item_id <= 65535 or not 1 <= count <= 255:
        raise WireDecodeError("物品編號或數量無效")
    return index, item_id, count


def decode_observed(packet: ObservedPacket, *, profile: str) -> ObservedEvent:
    if profile != "legacy-1262":
        raise WireDecodeError("此事件佈局尚未對目前正式服版本驗證")
    if not isinstance(packet, ObservedPacket):
        raise WireDecodeError("事件型態無效")
    r = ReadOnlyReader(packet.payload)
    key = (packet.main, packet.sub)
    if key == (26, 4):
        event = ObservedEvent("inventory", "gold_snapshot", (("amount", r.u32()),))
    elif key in ((26, 1), (26, 2)):
        amount, notify = r.u32(), r.u8()
        if notify not in (0, 1):
            raise WireDecodeError("金幣變化通知旗標無效")
        event = ObservedEvent(
            "inventory", "gold_delta",
            (("delta", amount if packet.sub == 1 else -amount),),
        )
    elif key == (26, 3):
        event = ObservedEvent("inventory", "gold_limit")
    elif key in ((7, 1), (12, 1)):
        role, scene, x, y = r.u32(), r.u16(), r.u16(), r.u16()
        event = ObservedEvent("world", "position",
                              (("role_id", role), ("scene", scene),
                               ("x", x), ("y", y)))
        # Old client allows future extension bytes on position snapshots.
        # They are intentionally not interpreted or stored.
        r.take(r.remaining)
    elif key == (52, 1):
        event = ObservedEvent("battle", "round_start", (("round", r.u16()),))
    elif key == (11, 12):
        event = ObservedEvent("battle", "winner", (("side", r.u8()),))
    elif key == (1, 11):
        event = ObservedEvent("session", "initial_data_complete")
    elif key == (23, 5):
        capacity = r.u8()
        if capacity < 1:
            raise WireDecodeError("背包容量不合理")
        slots = []
        seen = set()
        while r.remaining:
            index = r.u8()
            if not 1 <= index <= capacity or index in seen or len(slots) >= capacity:
                raise WireDecodeError("背包格位不合法或重複")
            seen.add(index)
            slots.append(_item(r, index))
        event = ObservedEvent(
            "inventory", "bag_snapshot", (("capacity", capacity),),
            tuple(sorted(slots)),
        )
    else:
        # This is not an interpreter for unknown game messages. Discard
        # payload and return *only* numeric source IDs and byte count.
        return ObservedEvent(
            "unknown", "unimplemented",
            (("main", packet.main), ("sub", packet.sub),
             ("payload_bytes", len(packet.payload))),
        )
    r.end()
    return event
