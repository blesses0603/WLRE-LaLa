"""唯讀事件訊息記錄器，僅接受已驗證的伺服器事件，不支援發言。"""
from collections import deque
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True, slots=True)
class SocialEvent:
    channel: str
    text: str
    revision: int


class SocialHistory:
    def __init__(self, capacity: int = 120):
        if type(capacity) is not int or capacity < 1 or capacity > 1000:
            raise ValueError("訊息上限無效")
        self._lock = RLock()
        self._lines: deque[SocialEvent] = deque(maxlen=capacity)
        self._last_revision = -1

    def ingest(self, *, channel: str, text: str, revision: int,
               authoritative: bool) -> bool:
        """不保存原始封包、未知頻道或未授權資料，亦不在本地偽造訊息。"""
        if not authoritative or channel not in {"system", "party", "guild", "world"}:
            return False
        if type(revision) is not int or revision < 0 or not isinstance(text, str):
            return False
        if len(text) > 2048:
            return False
        with self._lock:
            if revision <= self._last_revision:
                return False
            # 不將伺服器訊息渲染成 Tk 標記；顯示層只使用純文字。
            self._lines.append(SocialEvent(channel, text, revision))
            self._last_revision = revision
            return True

    def view(self) -> tuple[SocialEvent, ...]:
        with self._lock:
            return tuple(self._lines)

    def reset(self):
        with self._lock:
            self._lines.clear()
            self._last_revision = -1
