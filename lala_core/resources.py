"""本機唯讀資源 SHA-256/長度校驗，不下載、不執行、不信任未核對資料。

正式版 Manifest 的取得、信任錨與版本身份仍需獨立實作及實機驗證。
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ResourceCheck:
    path: str
    verified: bool
    reason: str


def audit_local_resources(root: str | Path, specs: Iterable[ResourceSpec]) -> tuple[ResourceCheck, ...]:
    root = Path(root).resolve()
    seen: set[str] = set()
    results = []
    for spec in specs:
        relative = PurePosixPath(spec.path)
        if (not spec.path or relative.is_absolute() or "\\" in spec.path or
                any(part in ("..", ".", "") for part in relative.parts) or
                spec.path in seen):
            results.append(ResourceCheck(spec.path, False, "路徑不安全或重複"))
            continue
        seen.add(spec.path)
        if (not isinstance(spec.size, int) or isinstance(spec.size, bool) or
                spec.size < 0 or len(spec.sha256) != 64 or
                any(ch not in "0123456789abcdefABCDEF" for ch in spec.sha256)):
            results.append(ResourceCheck(spec.path, False, "來源宣告不合法"))
            continue
        target = (root / Path(*relative.parts)).resolve()
        if not target.is_relative_to(root):
            results.append(ResourceCheck(spec.path, False, "超出根目錄"))
            continue
        if not target.is_file():
            results.append(ResourceCheck(spec.path, False, "缺少檔案"))
            continue
        if target.stat().st_size != spec.size:
            results.append(ResourceCheck(spec.path, False, "長度不符"))
            continue
        digest = sha256()
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        verified = digest.hexdigest() == spec.sha256.lower()
        results.append(ResourceCheck(spec.path, verified, "通過" if verified else "SHA-256 不符"))
    return tuple(results)
