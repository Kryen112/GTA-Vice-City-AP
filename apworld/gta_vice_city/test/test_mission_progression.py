"""Assignment-aware slot and business events, using AP reachability sweeps."""

from BaseClasses import CollectionState, Item, ItemClassification, Location, Region
from test.bases import WorldTestBase
from test.general import setup_multiworld

from .. import GTAViceCityWorld, mission_order
from .. import mission_progression as progression
from ..locations import LOCATION_NAME_TO_ID
from ..rules import LocationRequirements, compile_requirements


class TestMissionProgression(WorldTestBase):
    game = "Grand Theft Auto Vice City"
    auto_construct = False

    def graph(self, timing, destination="Rosenberg", purchase_check=True):
        self.multiworld = setup_multiworld(GTAViceCityWorld, steps=())
        self.world = self.multiworld.worlds[1]
        strands = {"Rosenberg": ["An Old Friend", "The Party", "Back Alley Brawl"],
                   "Vercetti Protection": ["Shakedown", "Bar Brawl"],
                   "Malibu Club": ["No Escape?"]}
        assignment = {giver: list(missions) for giver, missions in strands.items()}
        if destination:
            index = 1 if destination == "Rosenberg" else 0
            assignment[destination][index], assignment["Vercetti Protection"][0] = (
                assignment["Vercetti Protection"][0], assignment[destination][index])
        menu = Region("Menu", 1, self.multiworld)
        self.multiworld.regions.append(menu)
        regions = {giver: Region(giver, 1, self.multiworld) for giver in strands}
        for giver, region in regions.items():
            self.multiworld.regions.append(region)
            menu.connect(region, rule=(lambda state: state.has("Starfish Island Access", 1))
                         if giver == "Vercetti Protection" else lambda state: True)
        entry = {}
        for giver, missions in strands.items():
            for ordinal in range(len(missions)):
                count = ordinal if giver == "Rosenberg" else ordinal + 1
                requirements = [(f"Progressive {giver}", count)] if count else []
                if giver == "Malibu Club":
                    requirements += [("Malibu bought", 1), ("Malibu Club Ownership", 1)]
                entry[giver, ordinal] = LocationRequirements(requirements, [])
        gameplay = {mission: LocationRequirements([], []) for missions in strands.values() for mission in missions}
        # The current Shakedown scene adapter stages at the mansion and needs an exit.
        gameplay["Shakedown"] = LocationRequirements([("Starfish Island Access", 1)], [])
        slots = progression.build_slots(strands, assignment, entry, gameplay)
        events = progression.add_slot_locations(strands, assignment, slots, regions, timing)
        purchase = Location(1, "Malibu bought", None, regions["Malibu Club"])
        purchase.access_rule = lambda state: state.has(progression.BUSINESSES_PURCHASABLE, 1)
        purchase.place_locked_item(Item("Malibu bought", ItemClassification.progression, None, 1))
        purchase.parent_region.locations.append(purchase)
        events.append(purchase)
        if purchase_check:
            check = Location(1, "Malibu Club Purchase", LOCATION_NAME_TO_ID["Malibu Club Purchase"],
                             regions["Malibu Club"])
            check.access_rule = purchase.access_rule
            check.parent_region.locations.append(check)
        state = CollectionState(self.multiworld)
        for giver, missions in strands.items():
            for _ in missions:
                state.collect(self.world.create_item(f"Progressive {giver}"), prevent_sweep=True)
        state.collect(self.world.create_item("Malibu Club Ownership"), prevent_sweep=True)
        return state, events, strands, assignment, entry, gameplay

    def test_early_shakedown_check_and_business_event_have_separate_timing(self):
        for timing in ("quest_giver_progress", "mission_completion"):
            with self.subTest(timing=timing):
                state, events, *_ = self.graph(timing)
                state.collect(self.world.create_item("Starfish Island Access"), prevent_sweep=True)
                while state.has("Progressive Vercetti Protection", 1):
                    state.remove(self.world.create_item("Progressive Vercetti Protection"))
                self.assertFalse(state.has(progression.slot_completed("Rosenberg", 1), 1))
                state.sweep_for_advancements(events)
                check = self.multiworld.get_location("Shakedown", 1)
                self.assertEqual(check.address, LOCATION_NAME_TO_ID["Shakedown"])
                self.assertEqual(check.parent_region.name, "Rosenberg")
                self.assertTrue(check.can_reach(state))
                self.assertTrue(state.has(progression.mission_completed("Shakedown"), 1))
                self.assertEqual(state.has(progression.BUSINESSES_PURCHASABLE, 1), timing == "mission_completion")
                self.assertFalse(state.has("Mainland Access", 1))
                state.collect(self.world.create_item("Progressive Vercetti Protection"), prevent_sweep=True)
                state.sweep_for_advancements(events)
                self.assertTrue(state.has(progression.BUSINESSES_PURCHASABLE, 1))

    def test_business_cycle_is_rejected_without_poisoning_input_state(self):
        state, events, *_ = self.graph("mission_completion", "Malibu Club")
        state.collect(self.world.create_item("Starfish Island Access"), prevent_sweep=True)
        with self.assertRaisesRegex(ValueError, "Unreachable mission progression:.*Malibu"):
            progression.validate_slot_reachability(state, events)
        self.assertFalse(state.has(progression.slot_completed("Rosenberg", 0), 1))
        state, events, *_ = self.graph("quest_giver_progress", "Malibu Club")
        state.collect(self.world.create_item("Starfish Island Access"), prevent_sweep=True)
        progression.validate_slot_reachability(state, events)

    def test_purchase_fact_survives_disabled_purchase_checks_and_identity(self):
        for timing in ("quest_giver_progress", "mission_completion"):
            state, events, *_ = self.graph(timing, destination=None, purchase_check=False)
            state.collect(self.world.create_item("Starfish Island Access"), prevent_sweep=True)
            progression.validate_slot_reachability(state, events)
            state.sweep_for_advancements(events)
            self.assertTrue(state.has("Malibu bought", 1))
            self.assertEqual(state.count(progression.BUSINESSES_PURCHASABLE, 1), 1)
            state.sweep_for_advancements(events)
            self.assertEqual(state.count(progression.BUSINESSES_PURCHASABLE, 1), 1)
            with self.assertRaisesRegex(ValueError, "pregranted"):
                progression.validate_slot_reachability(state, events)

    def test_alternative_gameplay_routes_and_required_predecessors(self):
        state, events, strands, assignment, entry, gameplay = self.graph("mission_completion")
        gameplay["Shakedown"] = LocationRequirements(
            [], [([[("Mainland Access", 1)], [("Starfish Island Access", 1)]], 1)])
        slots = progression.build_slots(strands, assignment, entry, gameplay)
        shakedown = next(slot for slot in slots if slot.mission == "Shakedown")
        self.assertIn((progression.slot_completed("Rosenberg", 0), 1), shakedown.requirements.requirements)
        rule = compile_requirements(shakedown.requirements)
        self.assertFalse(rule(state, 1))
        state.sweep_for_advancements(events)
        self.assertFalse(rule(state, 1))
        state.collect(self.world.create_item("Mainland Access"), prevent_sweep=True)
        self.assertTrue(rule(state, 1))

    def test_timing_and_incomplete_requirement_tables_fail_closed(self):
        _, _, strands, assignment, entry, gameplay = self.graph("mission_completion")
        with self.assertRaisesRegex(ValueError, "Unknown world event timing"):
            mission_order.event_trigger_slot(strands, assignment, "Shakedown", "unknown")
        with self.assertRaisesRegex(ValueError, "entry requirements"):
            progression.build_slots(strands, assignment, {}, gameplay)
        with self.assertRaisesRegex(ValueError, "gameplay requirements"):
            progression.build_slots(strands, assignment, entry, {})

    def test_mansion_and_departure_follow_the_selected_identity(self):
        for mission, event in (("Rub Out", progression.MANSION_TAKEN_OVER),
                               ("All Hands On Deck!", progression.CORTEZ_DEPARTED)):
            for timing in ("quest_giver_progress", "mission_completion"):
                with self.subTest(mission=mission, timing=timing):
                    self.multiworld = setup_multiworld(GTAViceCityWorld, steps=())
                    strands = {"Rosenberg": ["The Party"], "Original": [mission]}
                    assignment = {"Rosenberg": [mission], "Original": ["The Party"]}
                    menu = Region("Menu", 1, self.multiworld)
                    regions = {giver: Region(giver, 1, self.multiworld) for giver in strands}
                    self.multiworld.regions.extend([menu, *regions.values()])
                    for region in regions.values():
                        menu.connect(region)
                    entry = {(giver, 0): LocationRequirements(
                        [("Original slot available", 1)] if giver == "Original" else [], []) for giver in strands}
                    gameplay = {name: LocationRequirements([], []) for name in (mission, "The Party")}
                    slots = progression.build_slots(strands, assignment, entry, gameplay)
                    events = progression.add_slot_locations(strands, assignment, slots, regions, timing)
                    state = CollectionState(self.multiworld)
                    state.sweep_for_advancements(events)
                    self.assertTrue(state.has(progression.mission_completed(mission), 1))
                    self.assertEqual(state.has(event, 1), timing == "mission_completion")
                    self.assertEqual(self.multiworld.get_location(mission, 1).address, LOCATION_NAME_TO_ID[mission])
                    state.collect(Item("Original slot available", ItemClassification.progression, None, 1),
                                  prevent_sweep=True)
                    state.sweep_for_advancements(events)
                    self.assertEqual(state.count(event, 1), 1)
