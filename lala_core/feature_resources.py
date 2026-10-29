"""LaLa 功能對應經舊版查核的精確官方 AssetPath，不下載整套遊戲。

以下四個 DataPackage 來源於舊版 1275 Manifest 已核對路徑；
新版使用時仍必須在當次最新官方 Manifest 找到完全一致的 AssetPath。
不代表遊戲資料 Schema 或現行通訊協定相容。
"""
from dataclasses import dataclass
import hashlib
import json

from .features import BY_KEY


POLICY_VERSION = 1
_DATA = "Assets/ResourcesBuild/Data/"
FEATURE_ASSETS = {
    "world": (("DataPackage", _DATA + "ScenesData_C.bytes"),
              ("DataPackage", _DATA + "Eve.bytes")),
    "portals": (("DataPackage", _DATA + "ScenesData_C.bytes"),
                ("DataPackage", _DATA + "Eve.bytes")),
    "npcs": (("DataPackage", _DATA + "Eve.bytes"),),
    "npc_shop": (("DataPackage", _DATA + "Eve.bytes"),
                 ("DataPackage", _DATA + "ItemData_C.bytes")),
    "inventory": (("DataPackage", _DATA + "ItemData_C.bytes"),),
    "crafting": (("DataPackage", _DATA + "SmithData_C.bytes"),
                 ("DataPackage", _DATA + "ItemData_C.bytes")),
}
# 其他導覽頁或本機規劃工具沒有經審核的 Bundle 需求，故不得推測下載。
LAUNCH_FEATURES = tuple(FEATURE_ASSETS)


@dataclass(frozen=True, slots=True)
class FeatureAssetSelection:
    feature_keys: tuple[str, ...]
    assets: tuple[tuple[str, str], ...]
    policy_key: str


def select_feature_assets(*, features=LAUNCH_FEATURES) -> FeatureAssetSelection:
    if not isinstance(features, (tuple, list)) or not features:
        raise ValueError("未指定需準備官方資源的 LaLa 功能")
    keys = tuple(features)
    if (any(type(key) is not str or key not in BY_KEY or key not in FEATURE_ASSETS
            for key in keys) or len(keys) != len(set(keys))):
        raise ValueError("功能清單含未核對的資源需求或重複功能")
    keys = tuple(sorted(keys))
    assets = tuple(sorted({binding for key in keys for binding in FEATURE_ASSETS[key]}))
    if not assets:
        raise ValueError("指定功能沒有任何可驗證的官方資源對應")
    payload = json.dumps({"schema": POLICY_VERSION, "features": keys, "assets": assets},
                         separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return FeatureAssetSelection(keys, assets, hashlib.sha256(payload).hexdigest())


DEFAULT_SELECTION = select_feature_assets()
