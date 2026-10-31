"""27 功能共用的舊版事件「尺寸證據」橋接器，僅限短時唯讀觀測。

只驗證已核對的固定 Payload 位元組數，絕不把事件內容當成權威角色
狀態。沒有 socket、send、登入、持久化、原始封包或自動操作權限。
所有未驗證的功能保持 0 筆及 server_verified=False。
"""
from collections import Counter
from dataclasses import dataclass

from .features import BY_KEY
from .wire import ObservedPacket


# 舊版來源及固定長度。長度相符不代表欄位值或當前協定已驗證：
# wlre/network/protocol.py:  S8-1 / S8-2 / S6-1 / S52-1 / S26-4
# wlre/network/social_protocol.py: S1-1 / S13-4
# wlre/network/instances.py: S186-6 / S85-15
# wlre/network/expedition.py: S31-12
_FIXED = {
    (8, 1): ("characters", 10),
    (8, 2): ("companions", 13),
    (6, 1): ("world", 8),
    (1, 1): ("chat", 4),
    (13, 4): ("party", 4),
    (186, 6): ("coop", 2),
    (26, 4): ("inventory", 4),
    (52, 1): ("battle", 2),
    (85, 15): ("dungeons", 0),
    (31, 12): ("expeditions", 2),
}
# 只記 ID 的舊版候選，不解析可變長度：公會檔案可能包含個資。
_CANDIDATE = {(39, 60): "guild"}
if any(key not in BY_KEY for key, _ in _FIXED.values()):
    raise RuntimeError("封包對應至不存在的功能")
if any(key not in BY_KEY for key in _CANDIDATE.values()):
    raise RuntimeError("公會功能不存在")


@dataclass(frozen=True, slots=True)
class FeatureWireEvidence:
    """所有 27 項功能在本次觀測的匿名證據，不代表伺服器接通。"""
    accepted: tuple[tuple[str, int], ...]
    rejected_lengths: tuple[tuple[str, int], ...]
    candidate_only: tuple[tuple[str, int], ...]
    server_verified: bool = False


class FeatureWireBridge:
    def __init__(self, *, profile: str):
        if profile != "legacy-1262":
            raise ValueError("只有舊版 1262 人工觀測可建立橋接")
        self._accepted = Counter()
        self._rejected = Counter()
        self._candidate = Counter()

    def observe(self, packet: ObservedPacket) -> None:
        if not isinstance(packet, ObservedPacket):
            raise TypeError("需要已拆框的唯讀事件")
        key = (packet.main, packet.sub)
        spec = _FIXED.get(key)
        if spec is not None:
            feature, expected_bytes = spec
            if len(packet.payload) == expected_bytes:
                self._accepted[feature] += 1
            else:
                self._rejected[feature] += 1
        elif key in _CANDIDATE:
            # Do not parse names, roles, permissions, unknown fields or body.
            self._candidate[_CANDIDATE[key]] += 1

    def report(self) -> FeatureWireEvidence:
        # Include all 27, including ones with no packet evidence.
        ordered = tuple(BY_KEY)
        return FeatureWireEvidence(
            accepted=tuple((k, self._accepted[k]) for k in ordered),
            rejected_lengths=tuple((k, self._rejected[k]) for k in ordered),
            candidate_only=tuple((k, self._candidate[k]) for k in ordered),
        )
