"""Marker gates stay equivalent to the world's location and region rules."""

import random
import unittest

from .. import data, items, locations, rules, scm
from ..check_markers import check_markers, marker_requirements


class TestMarkerRequirements(unittest.TestCase):
    def test_export_matches_rules(self):
        rng = random.Random(123)
        markers = check_markers(dict.fromkeys(locations.CLASS_TOGGLE.values(), True))
        globals_by_id = scm.item_globals()
        item_globals = {name: globals_by_id[item_id]
                        for name, item_id in items.ITEM_NAME_TO_ID.items()
                        if item_id in globals_by_id}
        item_globals.update({data.mission_passed_item_name(m): scm.completion_global(m)
                             for m in data.ROUTE_MISSIONS})
        lock_sets = [frozenset(), frozenset(data.ABILITY_LOCK_ITEMS)]
        lock_sets += [frozenset({key}) for key in data.ABILITY_LOCK_ITEMS]
        for split in (False, True):
            exported = marker_requirements(split)
            for locks in lock_sets:
                active = frozenset(item for key in locks for item in data.ABILITY_LOCK_ITEMS[key])
                expected = rules.build_location_requirements(ability_locks=locks, split_mainland_access=split)
                for _ in range(15):
                    counts = {name: rng.choice([0, 0, 1, 2, 5]) for name in item_globals}
                    memory = {index: counts[name] for name, index in item_globals.items()}
                    memory.update({scm.ability_lock_flag_global(item): int(item in active)
                                   for item in data.ABILITY_ITEMS})
                    for name, region in locations.LOCATION_REGIONS.items():
                        key = str(scm.completion_global(name))
                        if key not in markers:
                            continue
                        entry = expected.get(name, rules.LocationRequirements([], []))
                        def satisfies(terms, counts=counts):
                            return all(counts[item] >= count for item, count in terms)
                        reachable = satisfies(entry.requirements) and all(
                            sum(satisfies(route) for route in routes) >= needed
                            for routes, needed in entry.thresholds)
                        routes = data.active_route_groups(data.region_access_groups(region, split), active)
                        reachable &= not routes or any(all(counts[item] >= 1 for item in route) for route in routes)
                        visible = all(sum(all((flag and memory[flag] == 0) or memory[index] >= minimum
                                              for index, minimum, flag in route) for route in routes) >= needed
                                      for needed, routes in exported.get(key, []))
                        self.assertEqual(visible, reachable, (name, split, locks))
