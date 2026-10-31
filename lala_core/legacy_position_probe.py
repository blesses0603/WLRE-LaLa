"""實驗用舊版 1262 位置事件投影；永不建立正式 SessionStore。

只接受 S7-1 / S12-1 的既有 ReadOnlyReader 格式，且必須與
S3-1 初始角色的 role_id 相符。只保留最後一筆自己的坐標、
匿名計數及「未經認證」標記。舊協定沒有可驗證的序號，故無法
保證完整性、重播順序，也不會將局部更新送進 WorldSync。
"""
from dataclasses import dataclass

from .observed_events import decode_observed
from .wire import ObservedPacket, WireDecodeError


@dataclass(frozen=True, slots=True)
class LegacyPositionEvidence:
    own_messages: int
    changed_messages: int
    repeated_messages: int
    other_role_messages: int
    invalid_messages: int
    scene: int
    x: int
    y: int
    schema: str = "legacy-1262"
    authoritative: bool = False
    sequence_verified: bool = False


class LegacyPositionProbe:
    """綁定本次選角 S3-1，並以封包 role_id 做本地角色事件篩選。"""

    def __init__(self, *, role_id: int, scene: int, x: int, y: int):
        if (type(role_id) is not int or not 0 < role_id <= 0xffffffff
                or any(type(value) is not int or not 0 <= value <= 65535
                       for value in (scene, x, y))):
            raise ValueError("舊版初始角色位置不合法")
        self._role_id = role_id
        self._scene, self._x, self._y = scene, x, y
        self._own = self._changed = self._repeated = 0
        self._other = self._invalid = 0

    def observe(self, packet: ObservedPacket) -> None:
        """只看已知的 S7-1/S12-1；完全不儲存原始封包。"""
        if not isinstance(packet, ObservedPacket):
            raise TypeError("需要已拆框的觀測封包")
        if (packet.main, packet.sub) not in ((7, 1), (12, 1)):
            return
        try:
            event = decode_observed(packet, profile="legacy-1262")
            if event.category != "world" or event.kind != "position":
                raise WireDecodeError("非位置資料")
            fields = dict(event.values)
            role_id, scene, x, y = (fields[k] for k in
                                    ("role_id", "scene", "x", "y"))
            if (type(role_id) is not int or not 0 < role_id <= 0xffffffff
                    or any(type(value) is not int or not 0 <= value <= 65535
                           for value in (scene, x, y))):
                raise WireDecodeError("位置資料欄位不合法")
        except (WireDecodeError, KeyError, TypeError, ValueError):
            self._invalid += 1
            return
        if role_id != self._role_id:
            self._other += 1
            return
        self._own += 1
        next_position = (scene, x, y)
        if next_position == (self._scene, self._x, self._y):
            self._repeated += 1
            return
        self._changed += 1
        self._scene, self._x, self._y = next_position

    def report(self) -> LegacyPositionEvidence:
        return LegacyPositionEvidence(
            own_messages=self._own, changed_messages=self._changed,
            repeated_messages=self._repeated, other_role_messages=self._other,
            invalid_messages=self._invalid, scene=self._scene,
            x=self._x, y=self._y)
