//! 前景啟動自動更新工作；快取資料夾須事先建立並保持私有。
use std::{
    io::{self, Write},
    path::PathBuf,
};
use wlre_resource_manager::{
    auto_update::{AutoUpdater, Config},
    version_map::Platform,
};

fn main() {
    if let Err(error) = run() {
        eprintln!("更新服務無法啟動：{error}");
        std::process::exit(1);
    }
}
fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 4 {
        return Err("使用方式：指定私有快取目錄、windows 或 android、遊戲執行檔版本".into());
    }
    let platform = match args[2].to_str() {
        Some("windows") => Platform::Windows,
        Some("android") => Platform::Android,
        _ => return Err("平台必須是 windows 或 android".into()),
    };
    let executable = args[3].to_str().ok_or("版本格式無效")?.to_owned();
    let config = Config::new(PathBuf::from(&args[1]), platform, executable);
    let (_worker, events) = AutoUpdater::start(config).map_err(|e| format!("{e:?}"))?;
    let stdout = io::stdout();
    let mut output = stdout.lock();
    for event in events {
        serde_json::to_writer(&mut output, &event).map_err(|_| "無法寫入更新事件")?;
        writeln!(&mut output).map_err(|_| "無法寫入更新事件")?;
        output.flush().map_err(|_| "無法寫入更新事件")?;
    }
    Ok(())
}
