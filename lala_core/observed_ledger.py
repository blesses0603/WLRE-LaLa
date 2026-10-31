"""離線、只讀、版本鎖定的遊戲事件投影，不得用作正式服發送授權。

明確要求 profile=legacy-1262 才能重播。所有投影均帶上
server_verified=False；若值不一致，標記 unreliable 並要求完整快照。
"""
from dataclasses import dataclass
from .observed_events import ObservedEvent


@dataclass(frozen=True, slots=True)
class ObservedSnapshot:
    revision: int
    profile: str
    gold: int | None
    gold_reliable: bool
    role_id: int | None
    scene: int | None
    x: int | None
    y: int | None
    slots: tuple[tuple[int, int, int], ...]
    bag_reliable: bool
    battle_round: int | None
    server_verified: bool = False


class ObservedLedger:
    """This projector does not accept user/game commands and has no socket."""
    def __init__(self, *, profile: str):
        if profile != "legacy-1262":
            raise ValueError("目前正式服版本未驗證，不建立遊戲資料投影")
        self.profile = profile
        self.reset()

    def reset(self):
        self._revision = 0
        self._gold = None
        self._gold_reliable = False
        self._position = (None, None, None, None)
        self._slots: tuple[tuple[int, int, int], ...] = ()
        self._bag_reliable = False
        self._round = None

    def apply(self, event: ObservedEvent) -> bool:
        if not isinstance(event, ObservedEvent) or event.authoritative:
            return False
        values = dict(event.values)
        kind = event.kind
        if kind == "gold_snapshot":
            self._gold = values["amount"]
            self._gold_reliable = True
        elif kind == "gold_delta":
            change = values["delta"]
            if self._gold is None or not self._gold_reliable or not 0 <= self._gold + change <= 0xffffffff:
                self._gold = None
                self._gold_reliable = False
            else:
                self._gold += change
        elif kind == "gold_limit":
            self._gold = None
            self._gold_reliable = False
        elif kind == "position":
            new = tuple(values[k] for k in ("role_id", "scene", "x", "y"))
            # A different local role must not inherit the previous bag/gold.
            if self._position[0] is not None and new[0] != self._position[0]:
                self._gold = None
                self._gold_reliable = False
                self._slots = ()
                self._bag_reliable = False
                self._round = None
            self._position = new
        elif kind == "bag_snapshot":
            self._slots = tuple(event.slots)
            self._bag_reliable = True
        elif kind == "round_start":
            self._round = values["round"]
        elif kind == "winner":
            self._round = None
        elif kind == "initial_data_complete":
            pass
        else:
            return False
        self._revision += 1
        return True

    def snapshot(self) -> ObservedSnapshot:
        return ObservedSnapshot(
            self._revision, self.profile, self._gold, self._gold_reliable,
            *self._position, self._slots, self._bag_reliable, self._round,
        )
