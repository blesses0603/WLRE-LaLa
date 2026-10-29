"""只儲存白名單 UI 偏好，不儲存帳號密碼、Token 或伺服器封包。"""
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
import json
import os


@dataclass(frozen=True, slots=True)
class LocalPreferences:
    show_event_log: bool = True
    show_map_grid: bool = True
    log_limit: int = 120


_ALLOWED = frozenset(asdict(LocalPreferences()))


def validate(preferences: LocalPreferences) -> None:
    if not isinstance(preferences.show_event_log, bool) or not isinstance(preferences.show_map_grid, bool):
        raise ValueError("偏好開關必須是布林值")
    if type(preferences.log_limit) is not int or not 10 <= preferences.log_limit <= 1000:
        raise ValueError("事件紀錄上限需介於 10 到 1000")


def save_preferences(path: str | Path, preferences: LocalPreferences) -> None:
    """以同目錄暫存檔原子替換，不讓半寫入的 JSON 損壞原設定。"""
    validate(preferences)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(preferences), ensure_ascii=False, sort_keys=True) + "\n"
    temp_name = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                prefix=".lala-prefs-", delete=False) as output:
            temp_name = output.name
            os.chmod(temp_name, 0o600)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, target)
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            os.unlink(temp_name)


def load_preferences(path: str | Path) -> LocalPreferences:
    target = Path(path)
    if not target.is_file():
        return LocalPreferences()
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != _ALLOWED:
        raise ValueError("設定欄位不符白名單；不允許憑證欄位")
    result = LocalPreferences(**data)
    validate(result)
    return result
