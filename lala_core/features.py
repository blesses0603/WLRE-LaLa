"""舊版功能需求的初步模組清單；此清單不表示已實作。"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Feature:
    key: str
    title: str
    group: str
    description: str
    legacy_area: str


FEATURES: tuple[Feature, ...] = (
    Feature('dashboard', '主控台', '總覽', '帳號狀態、操作入口及安全提醒', 'wlre/ui、wlre/core'),
    Feature('accounts', '帳號與登入', '帳號', '多帳號、伺服器／分流、登入與斷線狀態', 'wlre/network、wlre/storage'),
    Feature('characters', '角色資訊', '帳號', '角色選擇、基本屬性、能力配點', 'wlre/core、wlre/services/battle'),
    Feature('battle', '戰鬥控制', '戰鬥', '手動戰鬥操作、戰場狀態與回合', 'wlre/services/battle'),
    Feature('battle_ai', '戰鬥 AI', '戰鬥', '自動戰鬥規則、技能與回復設定', 'wlre/services/battle'),
    Feature('party', '隊伍管理', '戰鬥', '隊伍、陣形及組隊狀態', 'wlre/services/battle'),
    Feature('world', '地圖與移動', '探索', '小地圖、座標、路線與移動', 'wlre/features/minimap、wlre/services/world'),
    Feature('portals', '場景與傳點', '探索', '場景切換、傳點清單及核對', 'wlre/features/portals、wlre/services/world'),
    Feature('npcs', 'NPC 互動', '探索', 'NPC 定位、對話與選項', 'wlre/features/npc'),
    Feature('npc_shop', 'NPC 商店', '探索', '商品預覽與交易狀態確認', 'wlre/features/npc、wlre/services/items'),
    Feature('inventory', '背包與物品', '物品', '背包格位、物品資訊與使用', 'wlre/services/items'),
    Feature('storage', '超空間袋', '物品', '倉儲同步及物品狀態', 'wlre/services/items'),
    Feature('supplies', '補給與維護', '物品', 'HP／SP 補給、修理與物品整理', 'wlre/services/items'),
    Feature('crafting', '製作排程', '物品', '配方、材料檢查與製作佇列', 'wlre/services/items'),
    Feature('alchemy', '煉金系統', '物品', '煉金條件、材料與結果追蹤', 'wlre/services/items'),
    Feature('skills', '技能管理', '物品', '角色與夥伴技能資料', 'wlre/services/battle'),
    Feature('companions', '夥伴管理', '活動', '夥伴狀態、出戰與休息', 'wlre/services/battle'),
    Feature('expeditions', '遠征派遣', '活動', '任務、隊伍與領獎狀態', 'wlre/services/expedition'),
    Feature('dungeons', '一般副本', '活動', '副本資料、房間操作及獎勵', 'wlre/features/dungeon、wlre/services/instances.py'),
    Feature('coop', '協力挑戰', '活動', '協力房間、配對、準備與領獎', 'wlre/features/cooperative'),
    Feature('chat', '聊天社交', '社交', '聊天、好友與社交活動', 'wlre/services/social'),
    Feature('guild', '組織／公會', '社交', '組織狀態、成員與聊天', 'wlre/services/social'),
    Feature('tent', '帳篷與家具', '社交', '帳篷展開、進入與家具狀態', 'wlre/services/items、wlre/services/world'),
    Feature('efficiency', '經驗與統計', '系統', '經驗效率、升級預估與事件統計', 'wlre/core/efficiency.py'),
    Feature('resources', '官方資源管理', '系統', '版本、Manifest、Bundle 校驗及相容性', 'wlre/services/official_*'),
    Feature('logs', '事件與診斷', '系統', '安全日誌、例外與連線健康', 'wlre/core/diagnostics.py'),
    Feature('settings', '系統設定', '系統', '介面偏好、帳號設定與模組開關', 'wlre/storage、wlre/ui'),
)

BY_KEY = {item.key: item for item in FEATURES}
if len(BY_KEY) != len(FEATURES):
    raise ValueError('功能識別碼重複')
