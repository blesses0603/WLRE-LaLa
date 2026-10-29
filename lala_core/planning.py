"""不送出遊戲指令的離線規劃工具：物品、製作、遠征與路線。

輸入由使用者或將來已驗證的服務提供；此模組不推定是正式服狀態。
"""
from dataclasses import dataclass
from heapq import heappush, heappop
from collections.abc import Mapping, Iterable
from math import isfinite


@dataclass(frozen=True, slots=True)
class MaterialRequirement:
    item_id: int
    quantity: int


@dataclass(frozen=True, slots=True)
class CraftPlan:
    recipe_id: int
    quantity: int
    required: tuple[MaterialRequirement, ...]
    missing: tuple[MaterialRequirement, ...]
    can_start: bool


def _positive(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} 須為正整數")


def plan_crafting(recipe_id: int, quantity: int, recipe: Iterable[MaterialRequirement],
                  owned: Mapping[int, int],
                  reserved: Mapping[int, int] | None = None) -> CraftPlan:
    """只比較可信輸入的材料與既有預約，絕不自行啟動製作。"""
    _positive(recipe_id, "配方 ID")
    _positive(quantity, "製作數量")
    reserved = reserved if reserved is not None else {}
    requirements: dict[int, int] = {}
    for item in recipe:
        _positive(item.item_id, "物品 ID")
        _positive(item.quantity, "配方材料數量")
        requirements[item.item_id] = requirements.get(item.item_id, 0) + item.quantity * quantity
    for source in (owned, reserved):
        for item_id, count in source.items():
            _positive(item_id, "物品 ID")
            if type(count) is not int or count < 0:
                raise ValueError("物品數量不可為負或非整數")
    required = tuple(MaterialRequirement(k, v) for k, v in sorted(requirements.items()))
    missing = []
    for item in required:
        available = max(0, owned.get(item.item_id, 0) - reserved.get(item.item_id, 0))
        if available < item.quantity:
            missing.append(MaterialRequirement(item.item_id, item.quantity - available))
    return CraftPlan(recipe_id, quantity, required, tuple(missing), not missing)


@dataclass(frozen=True, slots=True)
class ExpeditionMember:
    member_id: int
    stamina: int
    available: bool


@dataclass(frozen=True, slots=True)
class ExpeditionPlan:
    member_ids: tuple[int, ...]
    accepted: bool
    reason: str


def plan_expedition(members: Iterable[ExpeditionMember],
                    selected_ids: Iterable[int],
                    *, minimum_stamina: int, party_size: int) -> ExpeditionPlan:
    """本機檢查隊伍條件；成功僅代表條件通過，非派遣或領獎成功。"""
    if type(minimum_stamina) is not int or minimum_stamina < 0:
        raise ValueError("體力門檻不可為負")
    _positive(party_size, "隊伍人數")
    by_id: dict[int, ExpeditionMember] = {}
    for member in members:
        _positive(member.member_id, "夥伴 ID")
        if member.member_id in by_id:
            raise ValueError("夥伴 ID 重複")
        if type(member.stamina) is not int or member.stamina < 0:
            raise ValueError("體力數值無效")
        by_id[member.member_id] = member
    selected = tuple(selected_ids)
    if len(selected) != len(set(selected)):
        return ExpeditionPlan(selected, False, "同一夥伴不可重複派遣")
    if len(selected) != party_size:
        return ExpeditionPlan(selected, False, "隊伍人數不符")
    if any(key not in by_id for key in selected):
        return ExpeditionPlan(selected, False, "指定夥伴資料不存在")
    if any(not by_id[key].available for key in selected):
        return ExpeditionPlan(selected, False, "有夥伴目前不可派遣")
    if any(by_id[key].stamina < minimum_stamina for key in selected):
        return ExpeditionPlan(selected, False, "有夥伴體力不足")
    return ExpeditionPlan(selected, True, "僅完成本機條件檢查，未派遣")


@dataclass(frozen=True, slots=True)
class Route:
    nodes: tuple[int, ...]
    cost: float


def shortest_route(graph: Mapping[int, Iterable[tuple[int, float]]],
                   start: int, goal: int, *, resource_verified: bool) -> Route | None:
    """經權威地圖索引驗證後才可規劃路線；不執行移動。

    圖形的來源身分驗證由呼叫端完成，缺少資料時拒絕產生路線。
    """
    if not resource_verified:
        raise ValueError("地圖資源尚未驗證")
    if start not in graph or goal not in graph:
        return None
    neighbors = {}
    for node, edges in graph.items():
        if type(node) is not int:
            raise ValueError("地圖節點 ID 無效")
        pairs = []
        for dest, cost in edges:
            if type(dest) is not int or dest not in graph:
                raise ValueError("地圖連線指向未知節點")
            if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not isfinite(cost) or cost < 0:
                raise ValueError("地圖連線距離無效")
            pairs.append((dest, cost))
        neighbors[node] = tuple(pairs)
    frontier = [(0.0, start)]
    distance = {start: 0.0}
    previous = {}
    while frontier:
        cost, node = heappop(frontier)
        if cost > distance[node]:
            continue
        if node == goal:
            path = [goal]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return Route(tuple(reversed(path)), cost)
        for next_node, length in neighbors[node]:
            new_cost = cost + length
            if new_cost < distance.get(next_node, float("inf")):
                distance[next_node] = new_cost
                previous[next_node] = node
                heappush(frontier, (new_cost, next_node))
    return None
