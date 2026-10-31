import unittest
from lala_core.planning import (
    MaterialRequirement, plan_crafting, ExpeditionMember,
    plan_expedition, shortest_route,
)


class PlanTests(unittest.TestCase):
    def test_crafting_missing_and_reserved(self):
        m = [MaterialRequirement(12, 2), MaterialRequirement(13, 1),
             MaterialRequirement(12, 1)]
        result = plan_crafting(7, 2, m, {12: 8, 13: 3}, {12: 3})
        self.assertEqual([(p.item_id, p.quantity) for p in result.required],
                         [(12, 6), (13, 2)])
        self.assertEqual([(p.item_id, p.quantity) for p in result.missing], [(12, 1)])
        self.assertFalse(result.can_start)
        yes = plan_crafting(7, 2, m, {12: 8, 13: 3}, {12: 2})
        self.assertTrue(yes.can_start)
        self.assertFalse(yes.missing)

    def test_crafting_invalid_inputs(self):
        with self.assertRaises(ValueError):
            plan_crafting(1, 0, (), {})
        with self.assertRaises(ValueError):
            plan_crafting(1, 1, [MaterialRequirement(3, -1)], {})
        with self.assertRaises(ValueError):
            plan_crafting(1, 1, [MaterialRequirement(3, 1)], {3: -1})

    def test_expedition_party(self):
        members = [ExpeditionMember(1, 70, True),
                   ExpeditionMember(2, 90, True),
                   ExpeditionMember(3, 99, False)]
        self.assertTrue(plan_expedition(members, [1, 2], party_size=2,
                                        minimum_stamina=65).accepted)
        self.assertFalse(plan_expedition(members, [1, 1], party_size=2,
                                         minimum_stamina=60).accepted)
        self.assertFalse(plan_expedition(members, [1, 3], party_size=2,
                                         minimum_stamina=60).accepted)
        self.assertFalse(plan_expedition(members, [1, 2], party_size=2,
                                         minimum_stamina=80).accepted)

    def test_shortest_route(self):
        graph = {1: [(2, 5), (3, 12)], 2: [(3, 1)], 3: []}
        with self.assertRaises(ValueError):
            shortest_route(graph, 1, 3, resource_verified=False)
        route = shortest_route(graph, 1, 3, resource_verified=True)
        self.assertEqual(route.nodes, (1, 2, 3))
        self.assertEqual(route.cost, 6)
        self.assertIsNone(shortest_route(graph, 3, 1, resource_verified=True))
        with self.assertRaises(ValueError):
            shortest_route({1: [(2, -1)], 2: []}, 1, 2, resource_verified=True)
