# WLRe-LaLa — 全新 LaLa（P1 功能服務開發中）

此專案是 **從零編寫** 的 LaLa 起始版本。舊版 `WLRe_lala` 與 `WLRe_lala_Android` 作為需求及行為參考，不直接沿用舊版遊戲邏輯；介面依使用者要求，從其舊版倉庫沿用少量 1262 原始按鈕與功能圖示 PNG（來源與切片規則見 `lala_desktop/assets/**/SOURCE.md`），不包含完整遊戲資源。這些遊戲圖檔的對外散布權仍須由專案擁有者確認。

## 開發狀態

- Windows（`0.2.0-dev`，P1 開發候選）：Tkinter 經典 LaLa 首頁（十張資訊卡、圓形功能入口、左下聊天、右側小地圖與事件／戰場分頁），並保留 27 項功能的搜尋與獨立視窗；**所有桌面視窗固定 16:9，停用最大化與拖曳縮放**。
- Android（`0.1.0-dev`）：Kivy 深藍圓角卡片與橫向圓形快捷列原型；沒有 APK、前景服務或懸浮窗。
- 共用 Core：27 項功能需求註冊表、操作安全閘門、權威快照、官方資源 SHA-256 稽核、**官方版本／兩包 Manifest 唯讀檢查、可選 YooAsset 2.2.5 全量 Asset/Bundle 索引解析、舊版 1262 封包唯讀回歸測試**、製作／遠征／地圖離線規劃、經驗效率計算、唯讀戰鬥候選、社交事件記錄、UI 偏好安全存檔及診斷資訊遮罩。
- Windows 可用離線工具：經驗效率、材料與背包、遠征資格（使用者手動輸入，不連線或送出封包）。新增使用者**手動觸發**的官方公開版本與 Manifest 查詢，不需帳密、不送出遊戲命令。
- 測試：純 Python `unittest` 與 CI 語法檢查。
- **已有 Manifest 全量索引解析與 Bundle 安裝程式，但尚無遊戲伺服器登入會話、遊戲資料 Schema 解析、戰鬥、自動化及真實角色資料。** 公開官方版本／Manifest 的唯讀查詢不代表遊戲服務已接通。

請勿在此預覽程式輸入真實帳密。後續實作會嚴格分離 Windows／Android UI 及共用協定、會話與安全控制。

## Windows 啟動

需 Windows 10／11 及已安裝的 **Python 3.11～3.15（需包含 Tkinter）**。目前統一使用 **Pillow 13.0.0**；由於 Pillow 13 不支援 Python 3.10，僅安裝 3.10 時 BAT 會顯示版本不相容，建議安裝 Python 3.11 以上。

**下載 PR #2 的最新開發分支，完整解壓縮後，雙擊 `run_lala.bat`。** 啟動器先檢查 Python／Pillow 13，再查詢當前官方版本，下載及完整解析 `DataPackage`、`MainPackage` 兩份 Manifest，依檔案索引下載**兩包列出的所有 Bundle**。每個 Bundle 都必須通過大小、MD5、CRC32LE 驗證，才會原子寫入私有快取。全部完成並通過複查後，才允許 LaLa 主介面開啟；斷線、磁碟不足、資料格式不同、雜湊不符或超過安全配額都會**停止啟動**，不會直接跳進離線介面。

快取路徑為 Windows `%LOCALAPPDATA%\\LaLa\\official_resources`，不會修改遊戲原始安裝目錄，也不會將遊戲素材加入 GitHub。首次下載可能需要較長時間與較大的硬碟空間；預設安全上限為 32 GiB、100,000 個 Bundle、單檔 256 MiB，另預留至少 512 MiB 空間。既有檔案必須重新驗證，通過則可重用；中斷後可再次雙擊繼續。若資源規模超過預設配額，程式會拒絕啟動，需要先確認實際下載量再調整設定，不會悄悄突破限制。

**資源安裝完整 ≠ 遊戲資料 Schema 已驗證或可以登入官方伺服器。** 目前正式服登入、戰鬥、交易等功能仍受安全閘門保護，不能僅憑安裝成功就解鎖。正常安裝後 CMD 會透過 Python 子程序開啟無主控台 LaLa；要保留索引診斷結果可使用 `run_lala.bat --diagnose`（只查版本及 Manifest，不下載全部 Bundle、不開 UI）。第一次啟動時會在專案資料夾建立 `.venv`、安裝 Pillow 13；之後會重用同一環境。

BAT 會**先自動偵測 Windows 的 `py`（Python Launcher）**，先嘗試 `py -3` 的預設版本，再依序嘗試已註冊的 3.15／3.14／3.13／3.12／3.11；若沒有 `py` 或該 Launcher 沒有相容版本，再偵測 `python`、`python3`（PATH）。不需手動設定 Python 路徑，且不會因僅安裝 Python 3.14／3.15 就顯示找不到 Python。找不到時顯示安裝說明與 `py -0p` 檢查指令，而**不會自動下載或安裝 Python 本體**。若已有使用 Python 3.11 以上的 `.venv`，BAT 會檢查並更新 Pillow 至 13.0.0；若舊 `.venv` 使用 Python 3.10 或環境損壞，BAT 會提示自行重新命名 `.venv` 後再啟動，不會擅自刪除舊環境。資料夾唯讀或下載失敗時，BAT 會顯示錯誤並保留視窗。

啟動時官方 HTTPS 每次請求的逾時上限為 20 秒；下載總時間依檔案數量及網路速度而異。若不需要官方資源檢查而只想驗證 Python 環境，使用下列 CI／開發參數（完全不連官方主機、不啟動 GUI）：

    run_lala.bat --check

僅測試 `py` Launcher 自動偵測的 CI 專用方式（不啟動 GUI）：

    run_lala.bat --check --py-only

另外可在虛擬環境執行：

    .venv\Scripts\python.exe -m lala_desktop

目前沒有 EXE 或內建可攜式 Python。BAT 並非免安裝 Python 的獨立執行檔；若無法安裝 Pillow，啟動流程會明確停止，不以備援圖示冒充原版圖片。

Windows 主畫面右側小地圖、事件紀錄與戰場陣形**共用使用者截圖的固定窄版**：1280px 主視窗時右欄為 **350px**（約占 27%），讓左側保有寬敞的角色與功能卡片空間；切換分頁不改變左右欄寬。若選用較小的 16:9 主視窗尺寸，右欄等比例縮小。

桌面版統一 **16:9 固定視窗政策**：主視窗預設 1280×720，功能與清單視窗預設 800×450，禁止使用者調整大小或最大化；如果螢幕可用空間不足，啟動時選擇較小的 16:9 預設，開啟後仍固定。**移除 Windows 白色系統標題列**，沿用 LaLa 深藍頁首，可拖曳頁首移動視窗；主視窗頁首提供最小化及關閉，功能視窗上方提供關閉。Windows 工作列最小化／還原行為仍待實機驗證。介面外觀採 **舊版按鈕＋圓角面板**：主視窗 20px 外框（Windows 以 Win32 Window Region 裁切）、資訊卡及面板 Canvas 圓角、青色細描邊；按鈕則使用舊版 1262 的藍色 Btn_004、橘色 Btn_014、灰色 Btn_016 及原版圓形圖示，沿用水平切片與滑入／按下效果；不改變 16:9 與既有功能。Android 是原生觸控全螢幕頁面，不套用 Windows 視窗規則。

## 官方資源強制安裝與診斷（P1）

一般啟動必須使用 `run_lala.bat`：版本／完整 Manifest 索引 → 全量 Bundle 計畫與安全配額 → 已快取檔案驗證／增量下載 → 最終版本與 Bundle 複查 → 原子安裝收據 → 主程式。**任一步驟失敗就不能進入 LaLa。**

驗收與診斷指令：

    run_lala.bat --diagnose
    .venv\Scripts\python.exe -m lala_core.resource_bootstrap --online --install --json

`--diagnose` 只檢查官方索引格式，不下載全部 Bundle；後者會執行實際安裝。CI 的 `--check` 只檢查 Python／Pillow，不會對官方主機聯網。

- 官方版號與兩份 Manifest 依各自完整修訂號確認，不能固定使用 1275。
- HTTPS 下載禁止任意主機、轉址與不安全路徑；Bundle 下載需要 Manifest 列出的檔名與大小、MD5、CRC32LE。
- 安裝收據僅表示兩包所有 Manifest 列出的 Bundle 已複查，不宣稱已解包 Unity 資產或證實遊戲資料格式。登入仍維持停用。
- 相關程式：`lala_core/resource_bootstrap.py`、`bundle_install.py`、`yooasset_index.py`，詳見 `docs/官方資源唯讀檢查.md`。

## 正式遊戲分流的單次 TCP 連線實驗（P1）

已依舊版 `WLRe_lala/wlre/resources/server_list.json` 的**分流快照**加入連線檢測。這份快照不保證仍為官方最新位址，連線成功也不能證明遊戲協定相容或已登入。

Windows 使用者可在「官方資源」功能視窗按「測試遊戲伺服器 TCP」，預設只測試舊版「地球召引 1 線」 `34.81.10.22:16988` **一次**；也可在解壓縮的專案資料夾執行：

    run_lala.bat --probe-server

這個模式會顯示測試結果並保留視窗，**不打開 GUI，不執行登入，不傳送任何遊戲封包**。一般雙擊 BAT 不會自動對遊戲分流建立 TCP 連線，避免每次啟動都多次打擾正式伺服器。

也可使用：

    .venv\Scripts\python.exe -m lala_core.server_probe --online --line 101 --json

回傳 `tcp_connected` 只代表 TCP socket 成功建立；`connection_refused` 或 `timeout` 不能直接證明官方關服，亦可能是路由、防火牆、舊位址或來源網路策略。真正帳號登入仍需新版經驗證的協定實作，**不應在 GitHub PR／聊天傳送遊戲密碼或 Token**。

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
