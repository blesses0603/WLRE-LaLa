"""未有已驗證協定前不可對正式伺服器發送任何命令。

此模組只定義授權、安全門檻和手動確認的交易入口，不猜測 C/S 封包。
真正 send adapter 需要個別指令的官方證據、正式服測試及審核。
"""
from dataclasses import dataclass
from typing import Protocol
from .operations import OperationGuard, OperationState
from .session import SessionStore


class PermissionDenied(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Command:
    key: str
    capability: str
    arguments: tuple[tuple[str, str], ...] = ()
    requires_confirmation: bool = True


class VerifiedAdapter(Protocol):
    def supports(self, capability: str) -> bool: ...
    def send(self, command: Command) -> None: ...


class DisabledAdapter:
    """P1 預設 fail-closed；未接入官方協定時不可假裝已連線。"""
    def supports(self, capability: str) -> bool:
        return False

    def send(self, command: Command) -> None:
        raise PermissionDenied("未安裝已驗證的伺服器通訊 Adapter")


class CommandGate:
    def __init__(self, session: SessionStore, adapter: VerifiedAdapter | None = None):
        self.session = session
        self.adapter = adapter if adapter is not None else DisabledAdapter()
        self.guard = OperationGuard()

    def submit(self, command: Command, *, user_confirmed: bool = False) -> bool:
        if not command.key or not command.capability:
            raise ValueError("操作與能力識別碼不可為空")
        view = self.session.view()
        if (not view.connected or not view.resource_verified
                or view.revision < 0):
            raise PermissionDenied("尚無已驗證的完整角色快照，禁止發送操作")
        if command.requires_confirmation and not user_confirmed:
            raise PermissionDenied("操作尚未經使用者確認")
        if not self.adapter.supports(command.capability):
            raise PermissionDenied("未完成協定驗證，禁止送出")
        if not self.guard.begin(command.key, session_ready=True, resources_verified=True):
            raise PermissionDenied("相同操作進行中或結果不明，不可重送")
        try:
            self.adapter.send(command)
        except Exception:
            # send 可能已寫到 socket；即使拋出異常也不能保證沒送到。
            self.guard.mark_uncertain(command.key)
            raise
        return True

    def acknowledge(self, key: str, *, authoritative: bool, success: bool) -> bool:
        """失敗或結果不明不會清鎖；須另有權威重新同步證據。"""
        if not authoritative or not success:
            self.guard.mark_uncertain(key)
            return False
        return self.guard.confirmed(key)

    def reset_after_sync(self, key: str, *, authoritative: bool) -> bool:
        if not authoritative:
            return False
        self.guard.reset_from_authoritative_sync(key)
        return True

    def status(self, key: str) -> OperationState:
        return self.guard.status(key)
