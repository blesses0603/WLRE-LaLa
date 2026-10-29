# WLRe-LaLa — 全新 LaLa（P0 UI 開發骨架）

此專案是 **從零編寫** 的 LaLa 起始版本。舊版 `WLRe_lala` 與 `WLRe_lala_Android` 作為需求及行為參考，不直接沿用舊版遊戲邏輯；介面依使用者要求，從其舊版倉庫沿用少量 1262 原始按鈕與功能圖示 PNG（來源與切片規則見 `lala_desktop/assets/**/SOURCE.md`），不包含完整遊戲資源。這些遊戲圖檔的對外散布權仍須由專案擁有者確認。

## 開發狀態

- Windows（`0.1.0-dev`）：Tkinter 經典 LaLa 首頁（十張資訊卡、圓形功能入口、左下聊天、右側小地圖與事件／戰場分頁），並保留 27 項功能的搜尋與獨立視窗；**所有桌面視窗固定 16:9，停用最大化與拖曳縮放**。
- Android（`0.1.0-dev`）：Kivy 深藍圓角卡片與橫向圓形快捷列原型；沒有 APK、前景服務或懸浮窗。
- 共用 Core：27 項功能需求註冊表、操作狀態保護骨架、診斷資訊敏感欄位遮罩。
- 測試：純 Python `unittest` 與 CI 語法檢查。
- **尚無正式遊戲伺服器連線、登入、下載、戰鬥、自動化、真實帳號資料與角色狀態。**

請勿在此預覽程式輸入真實帳密。後續實作會嚴格分離 Windows／Android UI 及共用協定、會話與安全控制。

## Windows 啟動

需本機安裝 Python 3.10 以上及 Tkinter。為顯示**舊版原始 PNG 按鈕**，先在專案根目錄執行：

    py -3 -m pip install -r requirements-desktop.txt

接著雙擊 `run_lala.bat`，或執行：

    py -3 -m lala_desktop

目前沒有 EXE 或內建可攜式 Python。未安裝 Pillow 時 UI 仍可啟動，但原版貼圖會改用 Canvas 備援按鈕。

桌面版統一 **16:9 固定視窗政策**：主視窗預設 1280×720，功能與清單視窗預設 800×450，禁止使用者調整大小或最大化；如果螢幕可用空間不足，啟動時選擇較小的 16:9 預設，開啟後仍固定。**移除 Windows 白色系統標題列**，沿用 LaLa 深藍頁首，可拖曳頁首移動視窗；主視窗頁首提供最小化及關閉，功能視窗上方提供關閉。Windows 工作列最小化／還原行為仍待實機驗證。介面外觀採 **舊版按鈕＋圓角面板**：主視窗 20px 外框（Windows 以 Win32 Window Region 裁切）、資訊卡及面板 Canvas 圓角、青色細描邊；按鈕則使用舊版 1262 的藍色 Btn_004、橘色 Btn_014、灰色 Btn_016 及原版圓形圖示，沿用水平切片與滑入／按下效果；不改變 16:9 與既有功能。Android 是原生觸控全螢幕頁面，不套用 Windows 視窗規則。

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
- `docs/舊版介面承襲.md`：舊版 UI 來源、經典版型、素材使用限制
- `docs/驗收標準.md`：P0 自動化與實機驗收準則
- `tests/`：純 Python 離線測試
- `.github/workflows/core-checks.yml`：GitHub Actions 測試

桌面版與 Android 版各自維護版本號；目前版本皆為 `0.1.0-dev`，尚無正式版、Tag 或 Release。
