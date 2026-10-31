"""只接受已驗證來源的會話快照；不連線、不產生虛構遊戲資料。

一旦斷線、換角色或換來源，舊快照不得出現在 UI 或操作驗證路徑。
"""
from dataclasses import dataclass, field
from threading import RLock
from types import MappingProxyType
from collections.abc import Mapping
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionView:
    generation: int
    connected: bool
    resource_verified: bool
    revision: int
    server_state: Mapping[str, Any] = field(default_factory=dict)


class SessionStore:
    """權威快照容器；generation 跨登入遞增，revision 在同一會話嚴格遞增。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._generation = 0
        self._connected = False
        self._resource_verified = False
        self._revision = -1
        self._data: dict[str, Any] = {}

    def start(self, *, authenticated: bool, resources_verified: bool) -> int:
        """只有已驗證的伺服器登入完成，才能將 session 設為 ready。"""
        with self._lock:
            self._generation += 1
            self._connected = bool(authenticated)
            self._resource_verified = bool(authenticated and resources_verified)
            self._revision = -1
            self._data = {}
            return self._generation

    def disconnect(self) -> None:
        with self._lock:
            self._generation += 1
            self._connected = False
            self._resource_verified = False
            self._revision = -1
            self._data = {}

    def apply(self, *, generation: int, revision: int, data: Mapping[str, Any],
              authoritative: bool) -> bool:
        """拒絕未授權、跨會話、逆序或重複資料；不可套用推測狀態。

        只接受已驗證 adapter 提供的權威來源標記；呼叫端仍需
        驗證實際伺服器訊息，不應以任意網路輸入直接標 authoritative=True。
        """
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            return False
        if not isinstance(data, Mapping):
            return False
        with self._lock:
            if not (authoritative and self._connected and self._resource_verified):
                return False
            if generation != self._generation or revision <= self._revision:
                return False
            # 避免 UI 取得可變容器的來源參照，且拒絕未預期的物件型態。
            safe = _copy_json(data)
            self._data = safe
            self._revision = revision
            return True

    def view(self) -> SessionView:
        with self._lock:
            return SessionView(
                self._generation, self._connected, self._resource_verified,
                self._revision, MappingProxyType(_copy_json(self._data)),
            )


def _copy_json(data):
    """防止共用參照洩漏及錯誤型別穿透；僅允許可驗證的簡單快照資料。"""
    if isinstance(data, Mapping):
        if not all(isinstance(k, str) for k in data):
            raise TypeError("快照欄位名稱必須為文字")
        return {k: _copy_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return tuple(_copy_json(v) for v in data)
    if data is None or isinstance(data, (str, int, float, bool)):
        return data
    raise TypeError("快照包含不支援的資料型態")
