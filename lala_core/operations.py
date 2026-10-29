"""操作的安全狀態骨架，尚未連接任何遊戲封包或工作排程。"""
from dataclasses import dataclass
from enum import Enum
from threading import Lock


class OperationState(str, Enum):
    IDLE = 'idle'
    PENDING = 'pending'
    UNCERTAIN = 'uncertain'


@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    operation: str
    state: OperationState


class OperationGuard:
    """防止重複發送；不會自行重試結果不明的操作。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._states: dict[str, OperationState] = {}

    def begin(self, operation: str, *, session_ready: bool, resources_verified: bool) -> bool:
        if not operation or not session_ready or not resources_verified:
            return False
        with self._lock:
            if self._states.get(operation, OperationState.IDLE) != OperationState.IDLE:
                return False
            self._states[operation] = OperationState.PENDING
            return True

    def mark_uncertain(self, operation: str) -> bool:
        with self._lock:
            if self._states.get(operation) != OperationState.PENDING:
                return False
            self._states[operation] = OperationState.UNCERTAIN
            return True

    def confirmed(self, operation: str) -> bool:
        """僅在已驗證的伺服器確認後，呼叫者才可清除操作狀態。"""
        with self._lock:
            if self._states.get(operation) != OperationState.PENDING:
                return False
            self._states.pop(operation)
            return True

    def reset_from_authoritative_sync(self, operation: str) -> None:
        """結果不明需重新同步伺服器權威狀態後，由上層明確解除。"""
        with self._lock:
            self._states.pop(operation, None)

    def status(self, operation: str) -> OperationState:
        with self._lock:
            return self._states.get(operation, OperationState.IDLE)
