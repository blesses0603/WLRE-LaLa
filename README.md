# WLRE-LaLa

LaLa 跨平台重新開發專案。**Rust 共用核心**、Windows／macOS 的 **Tauri 共用介面**，以及 Android 的 **Kotlin + Jetpack Compose** 獨立介面。

目前主要工作位於尚未合併的開發 PR；共用核心已有開發中的官方版本查詢與自動下載服務，**尚未完成平台整合、完整格式解析、遊戲登入或三平台應用**。

## 專案文件

- [開發規範與 PR 版本管理](AGENTS.md)
- [架構及版本規劃](docs/架構.md)
- [P0～P6 開發路線圖與驗收門檻](docs/ROADMAP.md)
- [官方資源調查與未確認事項](docs/官方資源調查.md)

遊戲資源唯一指定原始來源：https://wlreftpsrc.chinesegamer.net/WLN/TW/ 。需先確認官方更新與格式資訊，才可實作相對應轉接器；禁止提交官方遊戲素材。

## 核心驗證

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

以上為**預期執行的驗證指令**，不代表任何特定環境已通過。實際執行與 CI 結果請以對應 PR 記錄為準。

## 自動更新服務（開發中）

共用核心提供在程序運行期間自動檢查與下載的服務，可用以下指令啟動前景範例；快取目錄必須先建立，並由使用者確保私有。平台值使用 `windows` 或 `android`，最後一項是遊戲執行檔版本：

```powershell
cargo run -p wlre-resource-manager --example auto_update -- "私人快取目錄" windows 1.3.0
```

啟動後會立即查詢，預設每小時重新檢查，並以 JSON 事件回報版本、進度與錯誤；預設最多 10,000 個檔案及 8 GiB，單檔上限 256 MiB。關閉程序後不會背景執行，桌面及 Android 應用尚未整合此服務。清單大小、MD5 與 CRC32 用於檢查下載損毀，不能保證防止惡意竄改。官方版本或格式不相容時會停止並回報錯誤，不會使用猜測的格式。
