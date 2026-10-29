"""LaLa login lifecycle: credentials are never persisted or logged.

This is a safe integration boundary; a legacy 1262 game client is NOT a
verified present-day authentication adapter. The production default is
DisabledLoginAdapter and never sends credentials to an unverified server.
"""
from dataclasses import dataclass
from threading import RLock
from typing import Protocol
from .server_probe import LINE_SNAPSHOT
from .session import SessionStore


class LoginError(ValueError):
    """Safe-to-display reason; never include server payloads or credentials."""


@dataclass(frozen=True, slots=True)
class LoginView:
    generation: int
    phase: str
    line_id: int | None
    authenticated: bool
    role_ids: tuple[int, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class VerifiedLoginOutcome:
    """Only a protocol/endpoint-audited adapter may return this result."""
    authenticated: bool
    role_ids: tuple[int, ...]
    protocol_verified: bool
    endpoint_verified: bool


class LoginAdapter(Protocol):
    protocol_verified: bool
    endpoint_verified: bool

    def authenticate(self, *, endpoint: tuple[str, int], account: str,
                     password: str) -> VerifiedLoginOutcome: ...


class DisabledLoginAdapter:
    """Default until currently deployed official protocol is independently checked."""
    protocol_verified = False
    endpoint_verified = False

    def authenticate(self, *, endpoint, account, password):
        raise LoginError("目前正式服端點／登入協定尚未驗證，禁止傳送帳密")


def validate_credentials(account: str, password: str) -> None:
    """Legacy byte fields are at most 255 bytes; non-ASCII codec is unverified."""
    for field, value in (("帳號", account), ("密碼", password)):
        if not isinstance(value, str) or not value or len(value) > 255:
            raise LoginError(field + "須為 1～255 個字元")
        if not value.isascii() or any(ord(ch) < 33 or ord(ch) > 126 for ch in value):
            raise LoginError(field + "目前僅支援不含空白的 ASCII 文字")


class LoginCoordinator:
    """Thread-safe session generation; blocking adapter work runs outside this class.

    begin() validates UI intent and resource gate; call complete() with the
    same generation from an audited worker. Old worker results cannot revive a
    disconnected/changed account. No account/password appears in LoginView.
    """
    def __init__(self, session: SessionStore | None = None,
                 adapter: LoginAdapter | None = None):
        self.session = session if session is not None else SessionStore()
        self.adapter = adapter if adapter is not None else DisabledLoginAdapter()
        self._lock = RLock()
        self._generation = 0
        self._phase = "idle"
        self._line = None
        self._roles: tuple[int, ...] = ()
        self._reason = "尚未登入"

    def view(self) -> LoginView:
        with self._lock:
            return LoginView(self._generation, self._phase, self._line,
                             self._phase in ("role_selection", "world_ready"),
                             self._roles, self._reason)

    def begin(self, *, line_id: int, account: str, password: str,
              resources_verified: bool) -> int:
        # Clear previous session before validating a new login intent.
        with self._lock:
            self._generation += 1
            current = self._generation
            self.session.disconnect()
            self._roles = ()
            self._line = line_id if type(line_id) is int and line_id in LINE_SNAPSHOT else None
            self._phase = "blocked"
            self._reason = "無法開始登入"
            if not resources_verified:
                self._reason = "LaLa 必要官方資源未安裝完成"
                raise LoginError(self._reason)
            if self._line is None:
                self._reason = "請選擇已核對的分流"
                raise LoginError(self._reason)
            validate_credentials(account, password)
            if not (self.adapter.protocol_verified is True and
                    self.adapter.endpoint_verified is True):
                self._reason = "目前正式服登入協定／分流身分尚未核對，禁止傳送密碼"
                raise LoginError(self._reason)
            self._phase = "authenticating"
            self._reason = "等待伺服器登入結果"
            return current

    def authenticate(self, *, generation: int, account: str,
                     password: str) -> VerifiedLoginOutcome:
        """Call only from worker thread after begin() has passed the gate."""
        with self._lock:
            if generation != self._generation or self._phase != "authenticating":
                raise LoginError("登入已取消，拒絕沿用過期請求")
            line_id = self._line
            # Selected endpoint is NEVER an arbitrary user URL.
            name, host, port = LINE_SNAPSHOT[line_id]
        result = self.adapter.authenticate(endpoint=(host, port),
                                           account=account, password=password)
        if not isinstance(result, VerifiedLoginOutcome):
            raise LoginError("登入 Adapter 沒有提供可信驗證結果")
        return result

    def complete(self, generation: int, outcome: VerifiedLoginOutcome | None,
                 *, failed_reason="登入未成功") -> bool:
        with self._lock:
            if generation != self._generation or self._phase != "authenticating":
                return False
            if (not isinstance(outcome, VerifiedLoginOutcome)
                    or outcome.authenticated is not True
                    or outcome.protocol_verified is not True
                    or outcome.endpoint_verified is not True
                    or not isinstance(outcome.role_ids, tuple)
                    or any(type(x) is not int or not 0 < x <= 0xffffffff
                           for x in outcome.role_ids)
                    or len(outcome.role_ids) > 2
                    or len(outcome.role_ids) != len(set(outcome.role_ids))):
                self.session.disconnect()
                self._phase = "rejected"
                self._reason = failed_reason
                return False
            self.session.start(authenticated=True, resources_verified=True)
            self._roles = outcome.role_ids
            self._phase = "role_selection"
            self._reason = "伺服器驗證已回覆；等待選擇角色"
            return True

    def cancel(self) -> None:
        with self._lock:
            self._generation += 1
            self.session.disconnect()
            self._line = None
            self._roles = ()
            self._phase = "disconnected"
            self._reason = "已中斷登入，清除舊角色／會話資料"

    def choose_role(self, *, role_id: int) -> bool:
        # Role selection is only a local intention; sending a real C63-2
        # requires a separate audited adapter and a server acknowledgement.
        with self._lock:
            if self._phase != "role_selection" or role_id not in self._roles:
                return False
            self._reason = "角色選擇尚待新版協定發送／伺服器回覆確認"
            return False
