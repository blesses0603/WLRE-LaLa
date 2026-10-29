"""Windows pythonw.exe 無主控台：啟動失敗須顯示清楚提示而非靜默退出。"""
from pathlib import Path
import sys

from .app import main


def run():
    try:
        return main()
    except Exception as exc:
        # 只有 console-less Windows pythonw 需要原生對話框；正常
        # python.exe 仍保留完整 traceback，供使用者在 CMD 自行排錯。
        if sys.platform == "win32" and Path(sys.executable).name.lower() == "pythonw.exe":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None,
                    ("LaLa 主介面啟動失敗：" + type(exc).__name__
                     + "\n請在 CMD 使用以下指令查看詳細錯誤：\n"
                     + ".venv\\Scripts\\python.exe -m lala_desktop"),
                    "LaLa 啟動失敗",
                    0x10,
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    run()
