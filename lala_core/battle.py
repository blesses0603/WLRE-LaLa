"""唯讀戰鬥行動候選：絕不發封包、絕不自行啟動自動戰鬥。

真正出招仍需正式伺服器回合狀態、角色狀態與經審核的指令 Adapter。
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BattleSkill:
    skill_id: int
    sp_cost: int
    priority: int = 0


@dataclass(frozen=True, slots=True)
class BattleUnit:
    unit_id: int
    hp: int
    sp: int
    alive: bool


@dataclass(frozen=True, slots=True)
class BattleView:
    turn_revision: int
    active_unit_id: int
    allies: tuple[BattleUnit, ...]
    enemies: tuple[BattleUnit, ...]
    authoritative: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class BattleProposal:
    turn_revision: int
    unit_id: int
    target_id: int
    skill_id: int
    note: str = "離線候選，尚未送出"


def propose_battle_action(state: BattleView, skills: tuple[BattleSkill, ...],
                          *, enabled_by_user: bool = False) -> BattleProposal | None:
    """僅回傳合法候選，沒有任何副作用；未驗證回合一律無候選。"""
    if not (enabled_by_user and state.authoritative and state.is_active):
        return None
    if type(state.turn_revision) is not int or state.turn_revision < 0:
        return None
    seen = set()
    for unit in state.allies + state.enemies:
        if type(unit.unit_id) is not int or unit.unit_id in seen:
            return None
        seen.add(unit.unit_id)
        if type(unit.hp) is not int or type(unit.sp) is not int or unit.hp < 0 or unit.sp < 0:
            return None
    actor = next((a for a in state.allies if a.unit_id == state.active_unit_id), None)
    if actor is None or not actor.alive or actor.hp == 0:
        return None
    valid_targets = [enemy for enemy in state.enemies if enemy.alive and enemy.hp > 0]
    if not valid_targets:
        return None
    valid_skills = [skill for skill in skills
                    if (type(skill.skill_id) is int and skill.skill_id > 0
                        and type(skill.sp_cost) is int and skill.sp_cost >= 0
                        and type(skill.priority) is int
                        and skill.sp_cost <= actor.sp)]
    if not valid_skills:
        return None
    skill = min(valid_skills, key=lambda item: (-item.priority, item.sp_cost, item.skill_id))
    target = min(valid_targets, key=lambda item: item.unit_id)
    return BattleProposal(state.turn_revision, actor.unit_id, target.unit_id, skill.skill_id)
