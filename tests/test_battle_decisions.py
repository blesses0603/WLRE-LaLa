import unittest
from lala_core.battle import (
    BattleSkill, BattleUnit, BattleView, propose_battle_action
)


class BattleProposalTests(unittest.TestCase):
    def setUp(self):
        self.state = BattleView(15, 1, (BattleUnit(1, 100, 20, True),),
                                (BattleUnit(5, 90, 0, True),
                                 BattleUnit(6, 0, 0, False)),
                                True, True)

    def test_off_by_default_and_no_unknown_state(self):
        spells = (BattleSkill(10, 8, 3),)
        self.assertIsNone(propose_battle_action(self.state, spells))
        self.assertIsNone(propose_battle_action(
            BattleView(15, 1, self.state.allies, self.state.enemies, False, True),
            spells, enabled_by_user=True))

    def test_proposal_is_not_sent(self):
        spells = (BattleSkill(100, 21, 8), BattleSkill(101, 8, 5),
                  BattleSkill(102, 5, 2))
        action = propose_battle_action(self.state, spells, enabled_by_user=True)
        self.assertEqual((action.unit_id, action.target_id, action.skill_id),
                         (1, 5, 101))
        self.assertIn("尚未送出", action.note)

    def test_no_dead_targets_or_insufficient_sp(self):
        self.assertIsNone(propose_battle_action(
            BattleView(15, 1, self.state.allies, (BattleUnit(5, 0, 0, False),),
                       True, True),
            (BattleSkill(1, 1),), enabled_by_user=True))
        self.assertIsNone(propose_battle_action(
            self.state, (BattleSkill(2, 99),), enabled_by_user=True))
