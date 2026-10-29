# WLRe-LaLa — 全新 LaLa（P1 功能服務開發中）

此專案是 **從零編寫** 的 LaLa 起始版本。舊版 `WLRe_lala` 與 `WLRe_lala_Android` 作為需求及行為參考，不直接沿用舊版遊戲邏輯；介面依使用者要求，從其舊版倉庫沿用少量 1262 原始按鈕與功能圖示 PNG（來源與切片規則見 `lala_desktop/assets/**/SOURCE.md`），不包含完整遊戲資源。這些遊戲圖檔的對外散布權仍須由專案擁有者確認。

## 開發狀態

- Windows（`0.2.0-dev`，P1 開發候選）：Tkinter 經典 LaLa 首頁（十張資訊卡、圓形功能入口、左下聊天、右側小地圖與事件／戰場分頁），並保留 27 項功能的搜尋與獨立視窗；**所有桌面視窗固定 16:9，停用最大化與拖曳縮放**。
- Android（`0.1.0-dev`）：Kivy 深藍圓角卡片與橫向圓形快捷列原型；沒有 APK、前景服務或懸浮窗。
- 共用 Core：27 項功能需求註冊表、操作安全閘門、權威快照、官方資源 SHA-256 稽核、**官方版本／兩包 Manifest 唯讀檢查**、製作／遠征／地圖離線規劃、經驗效率計算、唯讀戰鬥候選、社交事件記錄、UI 偏好安全存檔及診斷資訊遮罩。
- Windows 可用離線工具：經驗效率、材料與背包、遠征資格（使用者手動輸入，不連線或送出封包）。新增使用者**手動觸發**的官方公開版本與 Manifest 查詢，不需帳密、不送出遊戲命令。
- 測試：純 Python `unittest` 與 CI 語法檢查。
- **尚無遊戲伺服器登入會話、完整資源解析／Bundle 同步、戰鬥、自動化、真實角色資料。** 公開官方版本／Manifest 的唯讀查詢不代表遊戲服務已接通。

請勿在此預覽程式輸入真實帳密。後續實作會嚴格分離 Windows／Android UI 及共用協定、會話與安全控制。

## Windows 啟動

需 Windows 10／11 及已安裝的 **Python 3.11～3.15（需包含 Tkinter）**。目前統一使用 **Pillow 13.0.0**；由於 Pillow 13 不支援 Python 3.10，僅安裝 3.10 時 BAT 會顯示版本不相容，建議安裝 Python 3.11 以上。

**從 GitHub PR 的開發分支下載完整 ZIP、解壓縮後，直接雙擊 `run_lala.bat` 即可。** 目前會依序檢查 Python／Pillow 13、**自動讀取官方公開版本及兩份 Manifest 傳輸完整性**，最後才啟動 LaLa。Windows 安裝了正常的 `pythonw.exe` 時，主視窗啟動後 CMD 會自動結束，避免黑色命令視窗擋住畫面；沒有 `pythonw.exe` 時退回可顯示錯誤的一般 Python 啟動方式。全程不用手動輸入 `python -m lala_core.resource_inspector`。若官方網路/CDN 自檢失敗仍開啟離線介面，CMD 會顯示更精確的版本表錯誤欄位與筆數（不直接印出官方原始內容），主視窗會標示「自檢失敗／離線」，登入及所有尚未驗證的伺服器功能保持禁用；這不是自動登入。 第一次啟動時會在專案資料夾建立 `.venv`，統一安裝 Pillow 13.0.0（通常需要網路）；之後雙擊會使用同一份環境，不必再手動執行 pip。BAT 會**先自動偵測 Windows 的 `py`（Python Launcher）**，先嘗試 `py -3` 的預設版本，再依序嘗試已註冊的 3.15／3.14／3.13／3.12／3.11；若沒有 `py` 或該 Launcher 沒有相容版本，再偵測 `python`、`python3`（PATH）。不需手動設定 Python 路徑，且不會因僅安裝 Python 3.14／3.15 就顯示找不到 Python。找不到時顯示安裝說明與 `py -0p` 檢查指令，而**不會自動下載或安裝 Python 本體**。若已有使用 Python 3.11 以上的 `.venv`，BAT 會檢查並更新 Pillow 至 13.0.0；若舊 `.venv` 使用 Python 3.10 或環境損壞，BAT 會提示自行重新命名 `.venv` 後再啟動，不會擅自刪除舊環境。資料夾唯讀或下載失敗時，BAT 會顯示錯誤並保留視窗。

啟動前的官方 HTTPS 請求逐筆逾時設為 3 秒；檢查過程可能受網路延遲影響，無法保證固定總時間。若不需要官方資源檢查而只想驗證 Python 環境，使用下列 CI／開發參數（完全不連官方主機、不啟動 GUI）：

    run_lala.bat --check

僅測試 `py` Launcher 自動偵測的 CI 專用方式（不啟動 GUI）：

    run_lala.bat --check --py-only

另外可在虛擬環境執行：

    .venv\Scripts\python.exe -m lala_desktop

目前沒有 EXE 或內建可攜式 Python。BAT 並非免安裝 Python 的獨立執行檔；若無法安裝 Pillow，啟動流程會明確停止，不以備援圖示冒充原版圖片。

Windows 主畫面右側小地圖、事件紀錄與戰場陣形**共用使用者截圖的固定窄版**：1280px 主視窗時右欄為 **350px**（約占 27%），讓左側保有寬敞的角色與功能卡片空間；切換分頁不改變左右欄寬。若選用較小的 16:9 主視窗尺寸，右欄等比例縮小。

桌面版統一 **16:9 固定視窗政策**：主視窗預設 1280×720，功能與清單視窗預設 800×450，禁止使用者調整大小或最大化；如果螢幕可用空間不足，啟動時選擇較小的 16:9 預設，開啟後仍固定。**移除 Windows 白色系統標題列**，沿用 LaLa 深藍頁首，可拖曳頁首移動視窗；主視窗頁首提供最小化及關閉，功能視窗上方提供關閉。Windows 工作列最小化／還原行為仍待實機驗證。介面外觀採 **舊版按鈕＋圓角面板**：主視窗 20px 外框（Windows 以 Win32 Window Region 裁切）、資訊卡及面板 Canvas 圓角、青色細描邊；按鈕則使用舊版 1262 的藍色 Btn_004、橘色 Btn_014、灰色 Btn_016 及原版圓形圖示，沿用水平切片與滑入／按下效果；不改變 16:9 與既有功能。Android 是原生觸控全螢幕頁面，不套用 Windows 視窗規則。

## 官方公開資源唯讀檢查（P1）

一般雙擊 run_lala.bat 時，會**先自動執行一次完整的官方版本＋兩包 Manifest 唯讀自檢**再啟動主畫面，結果在首頁上方顯示（只代表 Manifest 傳輸檢查；不解鎖登入）。若檢查失敗可繼續使用離線計算工具，也能在「全部功能」的「官方資源」視窗手動重查。手動重查僅影響該視窗的結果，不會自行解鎖遊戲操作。

開發／診斷時也可在命令列單獨執行；除 BAT 一鍵啟動外無需再手動輸入。

命令列亦可明確執行：

    py -3 -m lala_core.resource_inspector --online
    py -3 -m lala_core.resource_inspector --online --manifests --json

- 只查詢官方公開 HTTPS 版本對照、兩包獨立修訂號與選用的 Manifest .hash/.bytes；不將 1275 寫死。
- 版本查詢與 CRC32LE／SHA-256 完整性檢查成功**不代表完成 YooAsset 全量解碼、Schema、伺服器協定驗證**；can_login 永遠為 false。
- 不輸出帳密、不寫入遊戲安裝目錄、不儲存原始 Manifest 或下載 Bundle；GitHub CI 使用模擬資料，不主動連官方站。

詳細操作與安全範圍見 docs/官方資源唯讀檢查.md。

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
- `docs/功能實作追蹤.md`：27 功能逐項實作與正式服驗收進度
- `docs/舊版介面承襲.md`：舊版 UI 來源、經典版型、素材使用限制
- `docs/驗收標準.md`：P0 自動化與實機驗收準則
- `tests/`：純 Python 離線測試
- `.github/workflows/core-checks.yml`：GitHub Actions 測試

桌面版與 Android 版各自維護版本號：桌面目前為 P1 開發候選 `0.2.0-dev`，Android 仍為 `0.1.0-dev`。此 P1 PR 尚未合併 main，也沒有正式版、Tag 或 Release。
