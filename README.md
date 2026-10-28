# WLRE-LaLa

LaLa 跨平台重新開發專案。**Rust 共用核心**、Windows／macOS 的 **Tauri 共用介面**，以及 Android 的 **Kotlin + Jetpack Compose** 獨立介面。

目前主要工作位於尚未合併的開發 PR；共用核心現階段只包含資源管理的基礎型別與清單比較，**尚未實作官方資源自動更新、完整格式解析、遊戲登入或三平台應用**。

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
