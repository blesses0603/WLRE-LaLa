# WLRe-LaLa — 全新 LaLa（P0 UI 開發骨架）

此專案是 **從零編寫** 的 LaLa 起始版本。舊版 `WLRe_lala` 與 `WLRe_lala_Android` 僅作需求及行為參考；本倉庫不複製舊版程式碼或官方遊戲資源。

## 開發狀態

- Windows（`0.1.0-dev`）：Tkinter 深藍科技風離線 UI、功能導航、搜尋及佔位頁。
- Android（`0.1.0-dev`）：Kivy 可選介面原型；沒有 APK、前景服務或懸浮窗。
- 共用 Core：27 項功能需求註冊表、操作狀態保護骨架、診斷資訊敏感欄位遮罩。
- 測試：純 Python `unittest` 與 CI 語法檢查。
- **尚無正式遊戲伺服器連線、登入、下載、戰鬥、自動化、真實帳號資料與角色狀態。**

請勿在此預覽程式輸入真實帳密。後續實作會嚴格分離 Windows／Android UI 及共用協定、會話與安全控制。

## Windows 啟動

需本機安裝 Python 3.10 以上及 Tkinter。在 Windows 雙擊 `run_lala.bat`，或於專案根目錄執行：

    py -3 -m lala_desktop

Windows UI 不需額外 pip 安裝；目前沒有 EXE 或內建可攜式 Python。

## Android 介面預覽

安裝 Kivy 後，可於支援 Kivy 的 Python 環境執行：

    python -m lala_android

這不是 Android 安裝包，也尚未經手機實機驗證。

## 核心測試

    python -m unittest discover -s tests -v
    python -m compileall -q lala_core lala_desktop lala_android

此測試不等於 Windows 實機驗收、Android APK 測試或正式伺服器 E2E。

## 專案結構

- `lala_core/`：純 Python 共用功能清單、操作守門與診斷
- `lala_desktop/`：Windows／Tkinter UI
- `lala_android/`：Kivy 手機 UI 原型
- `docs/功能清單.md`：舊版功能需求與架構約束
- `docs/驗收標準.md`：P0 自動化與實機驗收準則
- `tests/`：純 Python 離線測試
- `.github/workflows/core-checks.yml`：GitHub Actions 測試

桌面版與 Android 版各自維護版本號；目前版本皆為 `0.1.0-dev`，尚無正式版、Tag 或 Release。
