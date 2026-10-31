"""已審核 Adapter 的世界會話生命週期；完全不連線、不解碼原始封包。

只有已獨立核對端點／登入協定／世界 Schema 的 Adapter 才能呼叫。
舊版 XOR 試驗、S3-1 截圖和封包長度吻合都不能提供此驗證。
無任何 send、密碼、重連或遊戲操作能力。若無可信驗證，fail closed。
"""
from dataclasses import dataclass
from enum import Enum
from threading import RLock
import time

from .login import VerifiedLoginOutcome
from .session import SessionStore


class WorldPhase(str, Enum):
    DISCONNECTED = "disconnected"
    WAITING_SNAPSHOT = "waiting_snapshot"
    READY = "ready"
    RESYNC_REQUIRED = "resync_required"


@dataclass(frozen=True, slots=True)
class WorldStatus:
    phase: WorldPhase
    generation: int | None
    revision: int
    role_id: int | None
    reason: str
    authoritative: bool = False


@dataclass(frozen=True, slots=True)
class VerifiedPosition:
    """已審核 World Adapter 產生的結構化事件，不是原始 1262 封包。"""
    generation: int
    revision: int
    role_id: int
    scene: int
    x: int
    y: int
    schema_verified: bool = False


def _valid_position(item: VerifiedPosition) -> bool:
    return (
        isinstance(item, VerifiedPosition)
        and item.schema_verified is True
        and type(item.generation) is int and item.generation >= 0
        and type(item.revision) is int and item.revision >= 0
        and type(item.role_id) is int and item.role_id > 0
        and type(item.scene) is int and 0 <= item.scene <= 65535
        and type(item.x) is int and 0 <= item.x <= 65535
        and type(item.y) is int and 0 <= item.y <= 65535
    )


class WorldSync:
    """綁定既有 SessionStore 的可信會話；事件須同一世代且 revision 連續。

    只處理 Adapter 已驗證的「完整初始位置快照」與「連續位置事件」。
    一旦資料跳號、角色不符、閒置失聯，就中止該會話、清空快照，
    並要求人工重新登入及新的完整快照，不會自動重連或重送操作。
    """

    def __init__(self, session: SessionStore, *, clock=None, idle_timeout=90):
        if not isinstance(session, SessionStore):
            raise TypeError("需要共用 SessionStore")
        if (type(idle_timeout) not in (int, float)
                or not 15 <= idle_timeout <= 300):
            raise ValueError("閒置逾時需為 15～300 秒")
        self.session = session
        self._clock = clock if clock is not None else time.monotonic
        self._timeout = idle_timeout
        self._lock = RLock()
        self._phase = WorldPhase.DISCONNECTED
        self._generation = None
        self._role_id = None
        self._revision = -1
        self._last_seen = None
        self._reason = "尚未建立可信會話"

    def view(self) -> WorldStatus:
        with self._lock:
            current = self.session.view()
            valid = (self._phase is WorldPhase.READY
                     and current.generation == self._generation
                     and current.connected and current.resource_verified
                     and current.revision == self._revision)
            return WorldStatus(
                self._phase, self._generation, self._revision, self._role_id,
                self._reason, authoritative=valid)

    def attach(self, *, generation: int, role_id: int,
               outcome: VerifiedLoginOutcome, world_schema_verified=False) -> bool:
        """選角 Adapter 對身分、端點、角色及 World Schema 完成核對後呼叫。

        呼叫端有責任核對實際的伺服器回覆，無法僅靠傳入 True
        或 XOR 1262 實驗資料來證明官方身分。
        """
        with self._lock:
            current = self.session.view()
            verified = (
                isinstance(outcome, VerifiedLoginOutcome)
                and outcome.authenticated is True
                and outcome.protocol_verified is True
                and outcome.endpoint_verified is True
                and world_schema_verified is True
                and type(generation) is int
                and current.generation == generation
                and current.connected and current.resource_verified
                and current.revision == -1
                and type(role_id) is int and role_id > 0
                and self._phase in (WorldPhase.DISCONNECTED,
                                    WorldPhase.RESYNC_REQUIRED))
            if not verified:
                return False
            self._phase = WorldPhase.WAITING_SNAPSHOT
            self._generation = generation
            self._role_id = role_id
            self._revision = -1
            self._last_seen = self._clock()
            self._reason = "等待可信初始角色快照"
            return True

    def _invalidate(self, reason: str, *, resync: bool) -> None:
        self.session.disconnect()
        self._phase = (WorldPhase.RESYNC_REQUIRED if resync
                       else WorldPhase.DISCONNECTED)
        self._generation = None
        self._role_id = None
        self._revision = -1
        self._last_seen = None
        self._reason = reason

    def disconnect(self) -> None:
        with self._lock:
            self._invalidate("連線已中斷，需重新登入", resync=False)

    def full_snapshot(self, packet: VerifiedPosition) -> bool:
        with self._lock:
            if self._phase is not WorldPhase.WAITING_SNAPSHOT:
                return False
            if (isinstance(packet, VerifiedPosition)
                    and type(packet.generation) is int
                    and packet.generation != self._generation):
                return False  # delayed worker event must not kill a new session
            if not self._matches(packet):
                self._invalidate("初始角色資料不合法，拒絕同步", resync=True)
                return False
            # The first snapshot must be revision 0, otherwise we cannot
            # distinguish preceding unseen events from a complete baseline.
            if packet.revision != 0:
                self._invalidate("缺少初始快照序號，需重新登入", resync=True)
                return False
            if not self._commit(packet):
                self._invalidate("初始快照遭拒絕", resync=True)
                return False
            self._phase = WorldPhase.READY
            self._reason = "角色位置快照已驗證"
            return True

    def position(self, packet: VerifiedPosition) -> bool:
        with self._lock:
            if self._phase is not WorldPhase.READY:
                return False
            if (isinstance(packet, VerifiedPosition)
                    and type(packet.generation) is int
                    and packet.generation != self._generation):
                return False  # ignore old generation without invalidating new
            if not self._matches(packet):
                self._invalidate("角色或世界 Schema 不符，需重新登入", resync=True)
                return False
            if packet.revision <= self._revision:
                # Retransmitted or stale events are ignored; no state rollback.
                return False
            if packet.revision != self._revision + 1:
                self._invalidate("角色事件序號中斷，需新的完整快照", resync=True)
                return False
            if not self._commit(packet):
                self._invalidate("角色快照更新失敗，需重新登入", resync=True)
                return False
            return True

    def _matches(self, packet) -> bool:
        return (
            _valid_position(packet) and packet.generation == self._generation
            and packet.role_id == self._role_id
            and self.session.view().generation == self._generation
        )

    def _commit(self, packet: VerifiedPosition) -> bool:
        data = {"role_id": packet.role_id, "scene": packet.scene,
                "x": packet.x, "y": packet.y}
        if not self.session.apply(
                generation=packet.generation, revision=packet.revision,
                data=data, authoritative=True):
            return False
        self._revision = packet.revision
        self._last_seen = self._clock()
        return True

    def tick(self) -> bool:
        """由已審核的接收迴圈定時呼叫；逾時失效，絕不自行發心跳。"""
        with self._lock:
            if self._phase not in (WorldPhase.WAITING_SNAPSHOT, WorldPhase.READY):
                return False
            if self.session.view().generation != self._generation:
                self._invalidate("會話已更換，清除過期世界資料", resync=False)
                return False
            if self._clock() - self._last_seen >= self._timeout:
                self._invalidate("超過接收閒置上限，請重新登入", resync=True)
                return False
            return True
