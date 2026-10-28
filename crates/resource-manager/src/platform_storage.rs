//! 平台應用傳入自己的私有資料目錄，核心建立不含遊戲素材的快取子目錄。
//! Windows 由 Tauri 應用提供 AppData；macOS 提供 Application Support；
//! Android 由 Context.getFilesDir() 提供。此模組不推測平台私有路徑。
use std::{
    fs, io,
    path::{Path, PathBuf},
};
pub use wlre_core_observability::ErrorCode as StorageError;

const SUBDIR: &str = "wlre-resource-cache";

/// 快取空間只由目前應用程式寫入；不提供跨程序鎖定或權限提升。
#[derive(Debug, Clone)]
pub struct CacheLocation {
    root: PathBuf,
}

impl CacheLocation {
    /// 父目錄須為應用私有資料夾且事先存在，拒絕父目錄及子目錄符號連結。
    /// 在 Unix 系統建立時設為 0700；Windows ACL 需由平台應用建立私有父目錄。
    pub fn prepare(private_app_data: &Path) -> Result<Self, StorageError> {
        ensure_directory(private_app_data)?;
        let root = private_app_data.join(SUBDIR);
        match fs::create_dir(&root) {
            Ok(()) => {
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(&root, fs::Permissions::from_mode(0o700))
                        .map_err(|_| StorageError::StorageFailure)?;
                }
            }
            Err(err) if err.kind() == io::ErrorKind::AlreadyExists => {}
            Err(_) => return Err(StorageError::StorageFailure),
        }
        ensure_directory(&root)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if fs::symlink_metadata(&root)
                .map_err(|_| StorageError::StorageFailure)?
                .permissions()
                .mode()
                & 0o077
                != 0
            {
                return Err(StorageError::CacheInvalidInput);
            }
        }
        Ok(Self { root })
    }

    /// 只能用於目前程序的下載、快取及已確認索引；禁止把此路徑提交版本庫。
    pub fn root(&self) -> &Path {
        &self.root
    }
}

fn ensure_directory(path: &Path) -> Result<(), StorageError> {
    if !fs::symlink_metadata(path)
        .map_err(|_| StorageError::StorageFailure)?
        .file_type()
        .is_dir()
    {
        return Err(StorageError::CacheInvalidInput);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn creates_and_reuses_a_private_cache_directory() {
        let base = tempfile::tempdir().unwrap();
        let first = CacheLocation::prepare(base.path()).unwrap();
        assert!(first.root().is_dir());
        assert!(first.root().ends_with(SUBDIR));
        let second = CacheLocation::prepare(base.path()).unwrap();
        assert_eq!(first.root(), second.root());
    }

    #[test]
    fn does_not_create_missing_parent() {
        let base = tempfile::tempdir().unwrap();
        let missing = base.path().join("missing");
        assert!(CacheLocation::prepare(&missing).is_err());
        assert!(!missing.exists());
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symlinked_cache_and_nonprivate_existing_cache() {
        use std::os::unix::fs::{symlink, PermissionsExt};
        let base = tempfile::tempdir().unwrap();
        let external = tempfile::tempdir().unwrap();
        let link = base.path().join(SUBDIR);
        symlink(external.path(), &link).unwrap();
        assert!(CacheLocation::prepare(base.path()).is_err());
        fs::remove_file(&link).unwrap();
        fs::create_dir(&link).unwrap();
        fs::set_permissions(&link, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(CacheLocation::prepare(base.path()).is_err());
    }
}
