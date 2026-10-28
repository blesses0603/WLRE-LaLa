//! 以精確封包名稱及依賴產生增量預覽；不直接下載或刪除。
use crate::bundle_index::{Bundle, BundleIndex};
use std::collections::{BTreeMap, BTreeSet};
pub use wlre_core_observability::ErrorCode as PlanError;

#[derive(Debug, Eq, PartialEq)]
pub enum Change {
    FirstObservation,
    Added,
    Changed,
    Unchanged,
}
#[derive(Debug, Eq, PartialEq)]
pub struct PlannedBundle {
    pub name: String,
    pub size: u64,
    pub change: Change,
}

/// 解析精確名稱並按依賴優先順序預覽；首次觀察不宣稱曾完成差異比較。
/// 所有來源須由呼叫端確認；清單驗證碼不等於防竄改保證。
/// 不檢查本機快取、不刪檔、不下載；拒絕加密封包、循環和不存在的參照。
pub fn plan(
    current: &BundleIndex,
    previous: Option<&BundleIndex>,
    requested: &[String],
) -> Result<Vec<PlannedBundle>, PlanError> {
    if requested.is_empty() {
        return Err(PlanError::ResourceNotFound);
    }
    if let Some(old) = previous {
        if old.package_name != current.package_name {
            return Err(PlanError::IndexInvalidEntry);
        }
    }
    let mut lookup = BTreeMap::new();
    for (id, bundle) in current.bundle_list.iter().enumerate() {
        if lookup.insert(bundle.bundle_name.as_str(), id).is_some() {
            return Err(PlanError::IndexDuplicatePath);
        }
    }
    let mut old_lookup = BTreeMap::new();
    if let Some(old) = previous {
        for b in &old.bundle_list {
            if old_lookup.insert(b.bundle_name.as_str(), b).is_some() {
                return Err(PlanError::IndexDuplicatePath);
            }
        }
    }
    let mut state = vec![0u8; current.bundle_list.len()];
    let mut order = Vec::new();
    let mut unique = BTreeSet::new();
    for name in requested {
        if !unique.insert(name) {
            continue;
        }
        let id = *lookup
            .get(name.as_str())
            .ok_or(PlanError::ResourceNotFound)?;
        let mut stack = vec![(id, false)];
        while let Some((node, exit)) = stack.pop() {
            let bundle = current
                .bundle_list
                .get(node)
                .ok_or(PlanError::IndexInvalidEntry)?;
            if exit {
                state[node] = 2;
                order.push(node);
                continue;
            }
            match state[node] {
                1 => return Err(PlanError::DependencyCycle),
                2 => continue,
                _ => {}
            }
            if bundle.encrypted {
                return Err(PlanError::UnsupportedEncryption);
            }
            state[node] = 1;
            stack.push((node, true));
            for &dependency in bundle.depend_ids.iter().rev() {
                if dependency >= state.len() {
                    return Err(PlanError::IndexInvalidEntry);
                }
                if state[dependency] == 1 {
                    return Err(PlanError::DependencyCycle);
                }
                if state[dependency] == 0 {
                    stack.push((dependency, false));
                }
            }
        }
    }
    let compare = |new: &Bundle| match previous {
        None => Change::FirstObservation,
        Some(_) => match old_lookup.get(new.bundle_name.as_str()) {
            None => Change::Added,
            Some(old)
                if old.file_hash.eq_ignore_ascii_case(&new.file_hash)
                    && old.file_crc.eq_ignore_ascii_case(&new.file_crc)
                    && old.file_size == new.file_size =>
            {
                Change::Unchanged
            }
            Some(_) => Change::Changed,
        },
    };
    Ok(order
        .into_iter()
        .map(|id| {
            let b = &current.bundle_list[id];
            PlannedBundle {
                name: b.bundle_name.clone(),
                size: b.file_size,
                change: compare(b),
            }
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn index(bundles: Vec<Bundle>) -> BundleIndex {
        BundleIndex {
            file_version: "2.2.5".into(),
            package_name: "DataPackage".into(),
            package_version: "v".into(),
            asset_list: vec![],
            bundle_list: bundles,
        }
    }
    fn bundle(name: &str, hash: &str, deps: Vec<usize>) -> Bundle {
        Bundle {
            bundle_name: name.into(),
            unity_crc: 0,
            file_hash: hash.into(),
            file_crc: "crc".into(),
            file_size: 10,
            encrypted: false,
            tags: vec![],
            depend_ids: deps,
        }
    }
    #[test]
    fn finds_dependencies_before_requested_and_classifies_first_and_change() {
        let now = index(vec![
            bundle("a", "new", vec![1]),
            bundle("b", "same", vec![]),
        ]);
        let old = index(vec![
            bundle("b", "same", vec![]),
            bundle("a", "old", vec![]),
        ]);
        let result = plan(&now, Some(&old), &["a".into()]).unwrap();
        assert_eq!(
            result.iter().map(|x| x.name.as_str()).collect::<Vec<_>>(),
            vec!["b", "a"]
        );
        assert_eq!(result[0].change, Change::Unchanged);
        assert_eq!(result[1].change, Change::Changed);
        assert_eq!(
            plan(&now, None, &["a".into()]).unwrap()[0].change,
            Change::FirstObservation
        );
    }
    #[test]
    fn rejects_cycles_missing_and_encrypted_dependencies() {
        let cycle = index(vec![bundle("a", "x", vec![1]), bundle("b", "x", vec![0])]);
        assert_eq!(
            plan(&cycle, None, &["a".into()]),
            Err(PlanError::DependencyCycle)
        );
        assert_eq!(
            plan(&cycle, None, &["missing".into()]),
            Err(PlanError::ResourceNotFound)
        );
        let mut b = bundle("a", "x", vec![]);
        b.encrypted = true;
        assert_eq!(
            plan(&index(vec![b]), None, &["a".into()]),
            Err(PlanError::UnsupportedEncryption)
        );
    }
}
