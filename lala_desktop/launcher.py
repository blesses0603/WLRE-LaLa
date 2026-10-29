"""Windows BAT 的 GUI 啟動橋接器。

BAT 的官方資源檢查可能故意以非零碼結束，但離線 GUI 應正常開啟。
使用一個獨立的 Python subprocess.Popen，回傳*本次*建立程序的結果，
避免 cmd.exe 的 start 命令沿用前一段的 ERRORLEVEL 誤報失敗。
"""
from pathlib import Path
from lala_core.resource_bootstrap import verify_installed
import subprocess
import sys


def launch_gui(python_executable=None, *, popen=None):
    """在 Windows 使用 pythonw 建立無主控台 GUI，啟動失敗則擲出 OSError。"""
    python_executable = Path(sys.executable if python_executable is None
                             else python_executable)
    pythonw = python_executable.with_name("pythonw.exe")
    if not pythonw.is_file():
        raise FileNotFoundError("專案虛擬環境缺少 pythonw.exe")
    # Also blocks launching GUI directly via the Pythonw bridge when BAT
    # validation was skipped. No installation = no GUI entry.
    verify_installed()
    spawn = subprocess.Popen if popen is None else popen
    # 沒有傳入 env，讓子程序繼承 BAT 設定的離線自檢狀態；
    # 不觸碰全域 Python、遊戲安裝路徑或角色資料。
    spawn(
        [str(pythonw), "-m", "lala_desktop"],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return 0


def main():
    try:
        return launch_gui()
    except (OSError, ValueError) as exc:
        # 僅輸出安全的錯誤型別，不複製可能含私人路徑的詳細例外文字。
        print(f"[LaLa] 無法建立 GUI 子程序：{type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
