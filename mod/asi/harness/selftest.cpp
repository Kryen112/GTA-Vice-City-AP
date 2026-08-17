// Standalone protocol self-test: round-trips framing (small and chunked) and
// checks the guards, with no socket and no game. Proves the C++ protocol layer
// compiles and behaves in the 32-bit MSVC toolchain.
#include <array>
#include <iostream>
#include <map>
#include <set>
#include <vector>

#include "../src/protocol.hpp"
#include "../src/scm_ability_locks.hpp"
#include "../src/scm_completion.hpp"
#include "../src/scm_content_locks.hpp"
#include "../src/scm_effects.hpp"
#include "../src/scm_minimap.hpp"
#include "../src/scm_packages.hpp"
#include "../src/scm_pickup_layout.hpp"
#include "../src/scm_radio.hpp"
#include "../src/scm_stunt_jumps.hpp"
#include "../src/scm_toasts.hpp"

using namespace gtavc;

namespace {

std::vector<json> RoundTrip(const json& message) {
  MessageWriter writer;
  MessageReader reader;
  std::vector<json> received;
  for (const std::string& frame : writer.Frames(message)) {
    for (json& decoded : reader.Feed(frame.data(), frame.size())) {
      received.push_back(std::move(decoded));
    }
  }
  return received;
}

int failures = 0;

void Expect(bool condition, const char* label) {
  if (!condition) {
    std::cerr << "FAIL: " << label << "\n";
    ++failures;
  }
}

}  // namespace

int main() {
  const json small = CheckMessage(542000000);
  const std::vector<json> small_result = RoundTrip(small);
  Expect(small_result.size() == 1 && small_result[0] == small, "small round-trip");

  json items = json::array();
  for (int index = 0; index < 5000; ++index) {
    items.push_back(json::array({index, index * 7}));
  }
  const json big = json{{"type", msg::kItems}, {"items", items}};
  const std::vector<std::string> frames = MessageWriter().Frames(big);
  Expect(frames.size() > 1, "large message chunks");
  for (const std::string& frame : frames) {
    Expect(frame.size() <= kMaxFrameBytes, "every frame within the size bound");
    Expect(!frame.empty() && frame.back() == '\n', "every frame ends in a newline");
  }
  const std::vector<json> big_result = RoundTrip(big);
  Expect(big_result.size() == 1 && big_result[0] == big, "chunked round-trip");

  bool threw = false;
  try {
    MessageReader reader;
    const std::string bad = "this is not json\n";
    reader.Feed(bad.data(), bad.size());
  } catch (const ProtocolError&) {
    threw = true;
  }
  Expect(threw, "malformed frame raises");

  // Completion detection: only a global that was zero at the baseline and is
  // now nonzero counts as a check. A global nonzero at the baseline (an
  // undeclared global reading leftover bytecode) is never reported, so an
  // incomplete main.scm cannot flood every location.
  {
    const std::map<int, std::int64_t> watch = {
        {9031, 542000000}, {9032, 542000001}, {9033, 542000002}};
    const std::map<int, int> baseline = {{9031, 0}, {9032, 0}, {9033, 12345}};
    std::set<int> reported;

    auto quiet = DetectCompletedLocations(watch, baseline, baseline, reported);
    Expect(quiet.empty(), "no checks when nothing changed from the baseline");

    std::map<int, int> current = {{9031, 1}, {9032, 0}, {9033, 99999}};
    auto first = DetectCompletedLocations(watch, baseline, current, reported);
    Expect(first.size() == 1 && first[0] == 542000000,
           "reports the zero-baseline global that went nonzero, not the garbage one");

    auto repeat = DetectCompletedLocations(watch, baseline, current, reported);
    Expect(repeat.empty(), "does not report a location twice");

    current[9032] = 4;
    auto later = DetectCompletedLocations(watch, baseline, current, reported);
    Expect(later.size() == 1 && later[0] == 542000001, "reports a later completion");
  }

  // Hidden-package detection: a package seen present this game and then gone is
  // collected, matched to the pickup pool by coordinate. Detection is per
  // package (by which coordinate vanished), never by collection order, and a
  // package never seen present or already recorded does not report.
  {
    const std::vector<PackageLocation> packages = {
        {9075, 10.0f, 10.0f, 10.0f},
        {9076, 100.0f, 100.0f, 100.0f},
        {9077, 200.0f, 200.0f, 200.0f}};
    const std::set<int> none;
    std::set<int> seen;

    const std::vector<WorldPoint> all = {
        {10.0f, 10.0f, 10.0f}, {100.0f, 100.0f, 100.0f}, {200.0f, 200.0f, 200.0f}};
    auto present = DetectNewlyCollectedPackages(packages, all, seen, none);
    Expect(present.empty(), "no package collected while all are present");
    Expect(seen.size() == 3, "every present package is marked seen");

    // The middle package vanishes: only its global reports, not the first by
    // placement order.
    const std::vector<WorldPoint> without_middle = {
        {10.0f, 10.0f, 10.0f}, {200.0f, 200.0f, 200.0f}};
    auto collected = DetectNewlyCollectedPackages(packages, without_middle, seen, none);
    Expect(collected.size() == 1 && collected[0] == 9076,
           "the specific vanished package reports, not by collection order");

    // Recorded as collected: it does not report again.
    const std::set<int> recorded = {9076};
    auto repeat = DetectNewlyCollectedPackages(packages, without_middle, seen, recorded);
    Expect(repeat.empty(), "an already-recorded package does not report again");

    // Gone but never seen present (unplaced pool or a save loaded with it
    // already gone) is not treated as collected.
    std::set<int> fresh;
    auto unseen = DetectNewlyCollectedPackages(packages, {}, fresh, none);
    Expect(unseen.empty(), "a package never seen present is not collected");

    // Match tolerance: within two units stays present, beyond counts as gone.
    std::set<int> one_seen = {9075};
    const std::vector<WorldPoint> near = {{11.5f, 10.0f, 10.0f}};
    auto near_result = DetectNewlyCollectedPackages({packages[0]}, near, one_seen, none);
    Expect(near_result.empty(), "a pickup within two units keeps the package present");
    const std::vector<WorldPoint> far = {{13.0f, 10.0f, 10.0f}};
    auto far_result = DetectNewlyCollectedPackages({packages[0]}, far, one_seen, none);
    Expect(far_result.size() == 1 && far_result[0] == 9075,
           "a pickup beyond two units leaves the package collected");
  }

  // One-shot effect planning: effects apply in received order past the applied
  // index; nothing applies while the player is not controllable, and the index
  // holds there so no effect is ever skipped.
  {
    auto make = [](const char* type, int amount, bool has) {
      ItemEffect effect;
      effect.type = type;
      effect.amount = amount;
      effect.has_amount = has;
      return effect;
    };
    const std::map<std::int64_t, ItemEffect> effects = {
        {10, make("cash", 500, true)},
        {11, make("trap_weather", 0, false)},
        {12, make("trap_wanted", 3, true)},
        {13, make("trap_speed_up", 30, true)}};
    // Item 99 carries no effect and is skipped without disturbing the index.
    const std::vector<std::pair<std::int64_t, std::int64_t>> items = {
        {0, 10}, {1, 99}, {2, 11}, {3, 12}, {4, 13}};

    auto blocked = PlanEffects(items, effects, 0, false);
    Expect(blocked.to_apply.empty(),
           "nothing applies while the player is not controllable");
    Expect(blocked.new_applied_index == 0,
           "the index holds while the player is not controllable");

    auto freed = PlanEffects(items, effects, 0, true);
    Expect(freed.to_apply.size() == 4 && freed.to_apply[0].type == "cash" &&
               freed.to_apply[1].type == "trap_weather" &&
               freed.to_apply[2].type == "trap_wanted" &&
               freed.to_apply[3].type == "trap_speed_up",
           "every pending effect applies in received order once controllable");
    Expect(freed.new_applied_index == 4, "the index reaches the last effect item");

    auto resumed = PlanEffects(items, effects, 2, true);
    Expect(resumed.to_apply.size() == 2 &&
               resumed.to_apply[0].type == "trap_wanted" &&
               resumed.to_apply[1].type == "trap_speed_up",
           "a saved index resumes past the already-applied effects");

    auto done = PlanEffects(items, effects, 4, true);
    Expect(done.to_apply.empty() && done.new_applied_index == 4,
           "a fully applied list repeats nothing");
  }

  // Radio planning: the resolve map sends a locked station to the next
  // unlocked one with wraparound; the retune cycle visits unlocked stations
  // and the off position in the vanilla wrap order, skipping the MP3 player,
  // so the radio can always be turned off but never plays a locked station.
  {
    std::array<bool, kRadioStationCount> only_fever{};
    only_fever[3] = true;
    const auto single = ResolveRadioStations(only_fever);
    bool all_fever = true;
    for (int station = 0; station < kRadioStationCount; ++station) {
      all_fever = all_fever && single[station] == 3;
    }
    Expect(all_fever, "everything resolves to the one unlocked station");

    std::array<bool, kRadioStationCount> two{};
    two[2] = true;
    two[7] = true;
    const auto resolve = ResolveRadioStations(two);
    Expect(resolve[2] == 2 && resolve[7] == 7, "an unlocked station resolves to itself");
    Expect(resolve[3] == 7, "a locked station resolves upward to the next unlocked one");
    Expect(resolve[8] == 2, "resolution wraps past Wave back around");

    Expect(CorrectedVehicleStation(9, resolve) == 2, "a rolled MP3 player re-resolves from Wildstyle");
    Expect(CorrectedVehicleStation(5, resolve) == 7, "a spawn remap follows the resolve map");

    Expect(NextAllowedTuning(2, two) == 7, "the cycle steps to the next unlocked station");
    Expect(NextAllowedTuning(7, two) == kRadioOff, "the cycle reaches off after the last station");
    Expect(NextAllowedTuning(kRadioOff, two) == 2, "the cycle wraps from off to the first unlocked");
    Expect(NextAllowedTuning(8, two) == kRadioOff, "the MP3 player is skipped, never landed on");

    std::array<bool, kRadioStationCount> only_wave{};
    only_wave[8] = true;
    Expect(NextAllowedTuning(8, only_wave) == kRadioOff, "a single station cycles to off");
    Expect(NextAllowedTuning(kRadioOff, only_wave) == 8, "and off cycles back to it");

    // Press shaping: presses walk the allowed cycle, and the rewritten raw
    // count makes the vanilla eleven-position commit land on that stop.
    Expect(AdvanceTuning(2, 1, two) == 7, "one press advances one allowed stop");
    Expect(AdvanceTuning(2, 2, two) == kRadioOff, "two presses reach the off position");
    Expect(AdvanceTuning(2, 3, two) == 2, "a full lap of the cycle comes back around");
    Expect(AdvanceTuning(2, 7, two) == 7, "press bursts reduce modulo the cycle length");
    Expect(AdvanceTuning(kRadioOff, 1, two) == 2, "advancing from off reaches the first unlocked");
    Expect(RetunePressesForTarget(2, 7) == 5, "the raw count is the wheel distance to the target");
    Expect(RetunePressesForTarget(7, 2) == 6, "the wheel distance wraps forward past off");
    Expect(RetunePressesForTarget(2, 2) == 11, "a same-station target becomes a full lap");

    // Press-plan bookkeeping across frames: fresh presses fold into the
    // logical total, an unchanged raw count plans no write, a raw count of
    // zero clears the scroll, and a commit plus a fresh press in one frame
    // restarts the count from the new byte.
    auto first = PlanRetunePresses(1, 0, 0, 2, two);
    Expect(first.logical_presses == 1 && first.written_presses == 5 && first.write_needed,
           "one fresh press aims the commit at the next unlocked station");
    auto second = PlanRetunePresses(6, first.logical_presses, first.written_presses, 2, two);
    Expect(second.logical_presses == 2 && second.written_presses == 8 && second.write_needed,
           "a second press advances the plan to the off position");
    auto idle = PlanRetunePresses(8, second.logical_presses, second.written_presses, 2, two);
    Expect(idle.logical_presses == 2 && idle.written_presses == 8 && !idle.write_needed,
           "an unchanged raw count plans no write");
    auto consumed = PlanRetunePresses(0, idle.logical_presses, idle.written_presses, 10, two);
    Expect(consumed.logical_presses == 0 && consumed.written_presses == 0 && !consumed.write_needed,
           "a consumed commit clears the scroll bookkeeping");
    auto restarted = PlanRetunePresses(1, 2, 8, 7, two);
    Expect(restarted.logical_presses == 1 && restarted.written_presses == 3 && restarted.write_needed,
           "a commit plus a fresh press restarts from the new byte");
    auto burst = PlanRetunePresses(7, 0, 0, 2, two);
    Expect(burst.logical_presses == 7 && burst.written_presses == 5 && burst.write_needed,
           "an MP3-key burst reduces modulo the cycle and lands on an unlocked stop");
  }

  // Minimap planning: while shuffled and locked the radar-hide flag is
  // asserted every frame; the unlock releases it exactly once and then leaves
  // it to the game, so a vanilla script hiding the radar is never stomped.
  // With the option off the plan never touches the flag.
  {
    const auto off = PlanMinimapEnforcement(false, false, false);
    Expect(off.action == MinimapAction::kLeaveAlone && !off.forcing,
           "option off leaves the flag alone");
    const auto off_stale = PlanMinimapEnforcement(false, false, true);
    Expect(off_stale.action == MinimapAction::kLeaveAlone && !off_stale.forcing,
           "option off drops stale forcing state");
    const auto locked = PlanMinimapEnforcement(true, false, false);
    Expect(locked.action == MinimapAction::kForceHidden && locked.forcing,
           "shuffled and locked forces the hide");
    const auto held = PlanMinimapEnforcement(true, false, locked.forcing);
    Expect(held.action == MinimapAction::kForceHidden && held.forcing,
           "the hide is re-asserted every frame while locked");
    const auto released = PlanMinimapEnforcement(true, true, held.forcing);
    Expect(released.action == MinimapAction::kReleaseOnce && !released.forcing,
           "the unlock releases the flag once");
    const auto after = PlanMinimapEnforcement(true, true, released.forcing);
    Expect(after.action == MinimapAction::kLeaveAlone && !after.forcing,
           "after the release the flag belongs to the game");
    const auto loaded_unlocked = PlanMinimapEnforcement(true, true, false);
    Expect(loaded_unlocked.action == MinimapAction::kLeaveAlone && !loaded_unlocked.forcing,
           "a save loaded already unlocked never writes the flag");
  }

  // Pickup layout planning: a target matches a pool entry by position and
  // type; only a model difference rewrites, so the game's own quantity
  // bookkeeping (ammo extraction zeroes it in place) is never re-stamped; a
  // dead or script-removed slot (type zero is filtered before planning, a
  // recreated slot arrives with its vanilla type) and a far entry never match.
  {
    const std::vector<PickupTarget> targets = {
        {393.9, -60.2, 11.5, 15, 274, 34},
        {30.0, -1330.9, 13.0, 2, 366, 0},
        {-900.0, 250.0, 17.0, 15, 375, 0},
    };
    const std::vector<PickupPoolEntry> pool = {
        // The first target's slot, still holding its vanilla bribe.
        {393.9f, -60.2f, 11.5f, 15, 375, 40},
        // The second target's slot, already rewritten to the heart.
        {30.0f, -1330.9f, 13.0f, 2, 366, 41},
        // Near the third target but the wrong type: no match.
        {-900.0f, 250.0f, 17.0f, 2, 269, 42},
        // Unrelated pool entry far from every target.
        {0.0f, 0.0f, 0.0f, 15, 366, 43},
    };
    const auto plan = PlanPickupLayout(targets, pool);
    Expect(plan.rewrites.size() == 1, "exactly the model mismatch rewrites");
    Expect(!plan.rewrites.empty() && plan.rewrites[0].pool_index == 40 &&
               plan.rewrites[0].model == 274 && plan.rewrites[0].quantity == 34,
           "the rewrite carries the target model and ammo to the matched slot");
    Expect(plan.unmatched_targets == 1,
           "the type-mismatched slot counts as unmatched, left vanilla");
    const auto vanilla = PlanPickupLayout({}, pool);
    Expect(vanilla.rewrites.empty() && vanilla.unmatched_targets == 0,
           "an empty layout plans nothing");
  }

  // Ability lock planning: a lock is its flag with no unlock; the input plan
  // is state-aware (the pad overloads buttons between foot and vehicle) and
  // constrains only a controllable player, except the wallet pin, which is
  // state and holds through cutscenes.
  {
    std::array<int, kAbilityCount> flags{};
    std::array<int, kAbilityCount> unlocks{};
    Expect(!AnyAbilityLocked(PlanAbilityLocks(flags, unlocks)),
           "no flags means nothing locked");
    flags.fill(1);
    const AbilityLocks all_locked = PlanAbilityLocks(flags, unlocks);
    Expect(AnyAbilityLocked(all_locked), "flags without unlocks lock");
    unlocks[kAbilitySprint] = 1;
    Expect(!PlanAbilityLocks(flags, unlocks)[kAbilitySprint],
           "an unlock releases its own ability");
    Expect(PlanAbilityLocks(flags, unlocks)[kAbilityJump],
           "an unlock releases only its own ability");

    const auto foot = PlanAbilityInputs(all_locked, true, true, false);
    Expect(foot.mask_sprint && foot.mask_jump && foot.mask_crouch &&
               foot.mask_weapon_cycle && foot.force_unarmed,
           "on foot masks the foot buttons and holds the weapon");
    const auto vehicle = PlanAbilityInputs(all_locked, false, true, false);
    Expect(!vehicle.mask_sprint && !vehicle.mask_jump && !vehicle.mask_crouch &&
               !vehicle.mask_weapon_cycle,
           "in a vehicle no button masks: the game reads those fields as "
           "look-behind and horn there");
    Expect(vehicle.force_unarmed,
           "the weapon hold still applies in a vehicle, which is what blocks drive-by");
    const auto cutscene = PlanAbilityInputs(all_locked, true, false, false);
    Expect(!cutscene.mask_sprint && !cutscene.mask_jump && !cutscene.mask_crouch &&
               !cutscene.mask_weapon_cycle && !cutscene.force_unarmed,
           "a script-owned player keeps every input");
    const auto remote = PlanAbilityInputs(all_locked, true, true, true);
    Expect(!remote.mask_sprint && !remote.mask_jump && !remote.mask_crouch &&
               !remote.mask_weapon_cycle && !remote.force_unarmed,
           "remote control stands every lock down: the pad drives the RC vehicle");
  }

  // Re-deriving the unlock globals: only on the edge where a world comes up,
  // and never from an empty item list, which would write every unlock global
  // to zero while the first delivery is still in flight.
  {
    Expect(ShouldReDeriveUnlocks(true, false, true), "a loaded world re-derives");
    Expect(!ShouldReDeriveUnlocks(true, true, true),
           "a world already up does not re-derive every frame");
    Expect(!ShouldReDeriveUnlocks(false, true, true),
           "a world going away does not re-derive");
    Expect(!ShouldReDeriveUnlocks(true, false, false),
           "no items in hand means nothing to re-derive from");
  }

  // Vehicle entry: each lock answers for its own appearance class and leaves
  // the others enterable.
  {
    AbilityLocks land_only{};
    land_only[kAbilityLandVehicles] = true;
    Expect(VehicleEntryLockIndex(land_only, kAppearanceAutomobile) == kAbilityLandVehicles &&
               VehicleEntryLockIndex(land_only, kAppearanceBike) == kAbilityLandVehicles,
           "the land lock blocks cars and bikes");
    Expect(VehicleEntryLockIndex(land_only, kAppearanceBoat) == kAbilityCount &&
               VehicleEntryLockIndex(land_only, kAppearanceHeli) == kAbilityCount,
           "the land lock leaves boats and helicopters enterable");
    AbilityLocks air_only{};
    air_only[kAbilityAirVehicles] = true;
    Expect(VehicleEntryLockIndex(air_only, kAppearanceHeli) == kAbilityAirVehicles &&
               VehicleEntryLockIndex(air_only, kAppearancePlane) == kAbilityAirVehicles,
           "the air lock blocks helicopters and planes");
    AbilityLocks sea_only{};
    sea_only[kAbilitySeaVehicles] = true;
    Expect(VehicleEntryLockIndex(sea_only, kAppearanceBoat) == kAbilitySeaVehicles,
           "the sea lock blocks boats");
  }

  // Held pickup planning: sinking and raising, and the band that makes a save
  // written while sunk heal itself on load.
  {
    Expect(PlanPickupHold(true, 11.0f, false) == PickupHoldAction::kLower,
           "a held pickup sinks");
    Expect(PlanPickupHold(true, 11.0f - kPickupLowerOffset, false) ==
               PickupHoldAction::kLeaveAlone,
           "a sunk pickup stays where it is while held");
    Expect(PlanPickupHold(false, 11.0f - kPickupLowerOffset, false) ==
               PickupHoldAction::kRaise,
           "release raises a sunk pickup, a loaded save included");
    Expect(PlanPickupHold(false, 11.0f, false) == PickupHoldAction::kLeaveAlone,
           "a released pickup in place never moves");
    // A pickup the game has taken away is neither visible nor collectable, so
    // it needs no holding either way.
    Expect(PlanPickupHold(true, 11.0f, true) == PickupHoldAction::kLeaveAlone,
           "a removed pickup is not sunk");
    Expect(PlanPickupHold(false, 11.0f - kPickupLowerOffset, true) ==
               PickupHoldAction::kLeaveAlone,
           "and a removed sunk pickup waits for its respawn");
  }

  // The package detector reads a sunk package back at its own height. Without
  // this every held package would match nothing and any package already seen
  // present would report as collected: a hundred checks at once.
  {
    Expect(UnsunkHeight(11.0f) == 11.0f, "a pickup in place reads its own height");
    Expect(UnsunkHeight(11.0f - kPickupLowerOffset) == 11.0f,
           "a sunk pickup reads the height it was sunk from");
    Expect(!IsPickupSunk(11.0f) && IsPickupSunk(11.0f - kPickupLowerOffset),
           "the band separates placed pickups from sunk ones");
  }

  // The two halves composed the way the frame handler composes them, which is
  // the interaction that matters: a package seen present, then held, must not
  // report as collected. Without the unsink read in the snapshot this is a
  // hundred false checks at once.
  {
    std::vector<PackageLocation> packages = {
        {9076, 479.6f, -1718.5f, 15.6f}, {9077, 708.4f, -498.2f, 12.3f}};
    std::vector<WorldPoint> placed;
    for (const PackageLocation& package : packages) {
      placed.push_back({package.x, package.y, package.z});
    }
    std::set<int> seen;
    std::set<int> collected;
    Expect(DetectNewlyCollectedPackages(packages, placed, seen, collected).empty(),
           "seeing a package present reports nothing");
    Expect(seen.size() == packages.size(), "and remembers both as present");

    // Now the hold sinks them, and the snapshot reads their height back up.
    std::vector<WorldPoint> held_snapshot;
    for (const PackageLocation& package : packages) {
      held_snapshot.push_back(
          {package.x, package.y, UnsunkHeight(package.z - kPickupLowerOffset)});
    }
    Expect(DetectNewlyCollectedPackages(packages, held_snapshot, seen, collected).empty(),
           "a held package still reads as present, so nothing false-reports");

    // A genuinely collected package leaves the pool entirely, at any height.
    std::vector<WorldPoint> one_gone = {held_snapshot[0]};
    const std::vector<int> newly =
        DetectNewlyCollectedPackages(packages, one_gone, seen, collected);
    Expect(newly.size() == 1 && newly[0] == 9077,
           "a package absent from the pool still reports collected");
  }

  // Classifying a pool entry: packages and property icons by pickup type,
  // rampage icons by the kill-frenzy model, everything else left alone. An
  // unresolved model (negative) must not swallow every entry.
  {
    Expect(ClassifyHeldPickup(kPickupTypeCollectable, 42, 7) ==
               HeldPickupClass::kPackage, "a collectable is a package");
    Expect(ClassifyHeldPickup(kPickupTypePropertyForSale, 42, 7) ==
               HeldPickupClass::kProperty, "a for-sale property icon is a property");
    Expect(ClassifyHeldPickup(kPickupTypePropertyLocked, 42, 7) ==
               HeldPickupClass::kProperty, "a locked property icon is too");
    Expect(ClassifyHeldPickup(3, 7, 7) == HeldPickupClass::kRampage,
           "the kill-frenzy model is a rampage icon");
    Expect(ClassifyHeldPickup(2, 42, 7) == HeldPickupClass::kNone,
           "an ambient street pickup is none of them");
    Expect(ClassifyHeldPickup(2, -1, -1) == HeldPickupClass::kNone,
           "an unresolved kill-frenzy model matches nothing");
    // An unresolved model costs only the rampage class: the type-matched
    // classes keep working, and a real rampage entry falls through to none
    // rather than being mistaken for something else.
    Expect(ClassifyHeldPickup(kPickupTypeCollectable, 42, -1) ==
               HeldPickupClass::kPackage,
           "packages still classify while the model is unresolved");
    Expect(ClassifyHeldPickup(kPickupTypePropertyForSale, 42, -1) ==
               HeldPickupClass::kProperty,
           "property icons too");
    Expect(ClassifyHeldPickup(3, 7, -1) == HeldPickupClass::kNone,
           "and a rampage entry is left alone, retried next frame");
  }

  // Release reporting. Two opposite failure modes to avoid: announcing from the
  // first observed frame (every loaded save would re-announce what it already
  // had) and suppressing the first real edge (a hundred packages would reappear
  // unexplained). The first observation is the baseline; every edge after it
  // speaks.
  {
    std::array<int, kContentCount> flags{};
    flags[kContentHiddenPackages] = 1;
    ContentLocks held{};
    held[kContentHiddenPackages] = true;
    ContentLocks none{};

    // First observation on a new game: held, and silent.
    ContentReleasePlan plan = PlanContentReleases(held, flags, none, false);
    Expect(!plan.announce[kContentHiddenPackages],
           "the first observed frame is the baseline, not an announcement");
    Expect(plan.next_was_held[kContentHiddenPackages],
           "and it records the class as held");

    // The item lands: the edge speaks, exactly once. This is the case an
    // earlier guard swallowed when the item was the game's first.
    plan = PlanContentReleases(none, flags, plan.next_was_held, true);
    Expect(plan.announce[kContentHiddenPackages],
           "the release announces on its edge");
    plan = PlanContentReleases(none, flags, plan.next_was_held, true);
    Expect(!plan.announce[kContentHiddenPackages],
           "and never again while it stays released");

    // A save that already holds the item reads released at the first
    // observation, so it stays quiet.
    plan = PlanContentReleases(none, flags, held, false);
    Expect(!plan.announce[kContentHiddenPackages],
           "a save already carrying the item does not re-announce");

    // An unconfigured class never speaks, whatever the state does.
    std::array<int, kContentCount> unselected{};
    plan = PlanContentReleases(none, unselected, held, true);
    Expect(!plan.announce[kContentHiddenPackages],
           "an unselected key never announces, the toggle invariant");
  }

  // The two lock families union on a rampage icon: either alone holds it, and
  // the two run-them-down icons answer only to the rampages content key, since
  // they hand no weapon.
  {
    AbilityLocks no_ability{};
    ContentLocks no_content{};
    AbilityLocks weapon_locked{};
    weapon_locked[kAbilityWeaponEquip] = true;
    ContentLocks rampages_held{};
    rampages_held[kContentRampages] = true;

    Expect(IsVehicleRampagePickup(-679.66f, -419.712f) &&
               IsVehicleRampagePickup(468.656f, -1608.79f),
           "both run-them-down rampage icons are recognized");
    Expect(!IsVehicleRampagePickup(218.22f, -1613.76f),
           "a weapon rampage icon is not");
    Expect(ShouldHoldPickup(HeldPickupClass::kRampage, false, weapon_locked, no_content),
           "the weapon lock alone holds a weapon rampage icon");
    Expect(ShouldHoldPickup(HeldPickupClass::kRampage, false, no_ability, rampages_held),
           "the rampages key alone holds it too");
    Expect(!ShouldHoldPickup(HeldPickupClass::kRampage, true, weapon_locked, no_content),
           "a run-them-down icon stays collectible under the weapon lock");
    Expect(ShouldHoldPickup(HeldPickupClass::kRampage, true, no_ability, rampages_held),
           "but the rampages key holds it");
    Expect(!ShouldHoldPickup(HeldPickupClass::kRampage, false, no_ability, no_content),
           "neither lock leaves every icon alone");
  }

  // Each content key holds its own class and nothing else, and a class is held
  // only while its flag is set and its unlock is still zero.
  {
    ContentLocks packages_held{};
    packages_held[kContentHiddenPackages] = true;
    AbilityLocks no_ability{};
    Expect(ShouldHoldPickup(HeldPickupClass::kPackage, false, no_ability, packages_held),
           "the packages key holds a package");
    Expect(!ShouldHoldPickup(HeldPickupClass::kProperty, false, no_ability, packages_held),
           "and leaves the property icons alone");

    std::array<int, kContentCount> flags{};
    std::array<int, kContentCount> unlocks{};
    flags[kContentPropertyPurchases] = 1;
    Expect(PlanContentLocks(flags, unlocks)[kContentPropertyPurchases],
           "a selected key with no item held");
    unlocks[kContentPropertyPurchases] = 1;
    Expect(!PlanContentLocks(flags, unlocks)[kContentPropertyPurchases],
           "the item releases it");
    std::array<int, kContentCount> unselected{};
    Expect(!AnyContentHeld(PlanContentLocks(unselected, unlocks)),
           "an unselected key never holds, the toggle invariant");
  }

  // Ability toast pacing: the first attempt toasts, the cooldown silences the
  // stream, and the clock wrapping cannot wedge it shut.
  {
    Expect(ShouldShowAbilityToast(500, false, 0), "the first attempt toasts");
    Expect(!ShouldShowAbilityToast(5000, true, 500),
           "inside the cooldown stays quiet");
    Expect(ShouldShowAbilityToast(500 + kAbilityToastCooldownMs, true, 500),
           "past the cooldown toasts again");
    Expect(!ShouldShowAbilityToast(100, true, 0xFFFFFF00u),
           "a wrap inside the cooldown stays quiet");
    Expect(ShouldShowAbilityToast(20000, true, 0xFFFFFF00u),
           "a wrapped clock still toasts once the cooldown elapses");
  }

  // Toast batching. The game keeps a pointer to the text of every message it
  // has queued and plays them in sequence, so lines pending together are joined
  // into one message. Nothing may be dropped: a release line is one-shot.
  {
    // The message cap is a parameter, so the cases below drive it at a value
    // that shows both the cap and the carry; the shipped value has its own case.
    constexpr std::size_t kTestMessagesPerPost = 3;
    const ToastBatch none = PlanToastBatch({}, kToastMaxChars, kTestMessagesPerPost);
    Expect(none.messages.empty() && none.consumed == 0, "nothing pending posts nothing");

    const ToastBatch one = PlanToastBatch({"Rampages are now available."},
                                          kToastMaxChars, kTestMessagesPerPost);
    Expect(one.messages.size() == 1 && one.consumed == 1 &&
               one.messages[0] == "Rampages are now available.",
           "a single line posts as itself");

    const ToastBatch joined = PlanToastBatch({"first", "second"}, kToastMaxChars,
                                             kTestMessagesPerPost);
    Expect(joined.messages.size() == 1 && joined.consumed == 2 &&
               joined.messages[0] ==
                   std::string("first") + std::string(kToastSeparator) + "second",
           "lines pending together join into one message");

    // An empty line would hold a message slot for its whole duration showing
    // nothing, so it is consumed without being posted.
    const ToastBatch empties = PlanToastBatch({"", "text", ""}, kToastMaxChars,
                                              kTestMessagesPerPost);
    Expect(empties.messages.size() == 1 && empties.messages[0] == "text" &&
               empties.consumed == 3,
           "empty lines are consumed and never posted");

    // The boundary: two lines that exactly fill one message stay in one.
    const std::string half(kToastMaxChars / 2 - 2, 'a');
    const ToastBatch exact = PlanToastBatch({half, half}, kToastMaxChars,
                                            kTestMessagesPerPost);
    Expect(exact.messages.size() == 1 && exact.consumed == 2 &&
               exact.messages[0].size() <= kToastMaxChars,
           "a pair that just fits stays one message");

    // One past it spills into the next message rather than truncating.
    const std::string most(kToastMaxChars - 2, 'b');
    const ToastBatch spill = PlanToastBatch({most, most}, kToastMaxChars,
                                            kTestMessagesPerPost);
    Expect(spill.messages.size() == 2 && spill.consumed == 2 &&
               spill.messages[0] == most && spill.messages[1] == most,
           "a line that does not fit starts the next message");

    // A single line longer than a whole message is truncated, never dropped.
    const ToastBatch huge = PlanToastBatch({std::string(kToastMaxChars + 50, 'c')},
                                           kToastMaxChars, kTestMessagesPerPost);
    Expect(huge.messages.size() == 1 && huge.consumed == 1 &&
               huge.messages[0].size() == kToastMaxChars,
           "an over-long line is truncated to one message");

    // Past the per-frame cap the rest stays queued, so the next frame posts it.
    const std::vector<std::string> flood(6, most);
    const ToastBatch capped = PlanToastBatch(flood, kToastMaxChars, kTestMessagesPerPost);
    Expect(capped.messages.size() == kTestMessagesPerPost &&
               capped.consumed == kTestMessagesPerPost,
           "the per-frame cap holds and consumes only what it posted");
    const ToastBatch rest = PlanToastBatch(
        std::vector<std::string>(flood.begin() + capped.consumed, flood.end()),
        kToastMaxChars, kTestMessagesPerPost);
    Expect(rest.messages.size() == 3 && rest.consumed == 3,
           "and the carried remainder posts on the next frame");

    // What ships: one message a post, so the game's own queue never overflows
    // and the rest of the queue waits here instead of being refused there.
    const ToastBatch shipped = PlanToastBatch({"first", most, "third"},
                                              kToastMaxChars,
                                              kToastMessagesPerPost);
    Expect(shipped.messages.size() == 1 && shipped.consumed == 1 &&
               shipped.messages[0] == "first",
           "a post hands the game one message and leaves the rest queued");

    // A zero cap would consume nothing, which stalls the queue rather than
    // losing it.
    const ToastBatch stalled = PlanToastBatch({"first"}, kToastMaxChars, 0);
    Expect(stalled.messages.empty() && stalled.consumed == 0,
           "a zero cap posts nothing and consumes nothing");
  }

  // The status line the status key shows. Only configured keys reach it, so a
  // seed that locks nothing must still say something.
  {
    Expect(ComposeLockStatus("", "", "", "") == "This seed locks nothing.",
           "a seed with no lock configured says so");
    Expect(ComposeLockStatus("Sprint", "", "", "") == "Locked: Sprint",
           "one list carries its own label alone");
    const std::string full =
        ComposeLockStatus("Sprint", "Jump", "Rampages", "Hidden Packages");
    Expect(full == std::string("Locked: Sprint") + std::string(kToastSeparator) +
                       "Unlocked: Jump" + std::string(kToastSeparator) +
                       "Held: Rampages" + std::string(kToastSeparator) +
                       "Available: Hidden Packages",
           "every non-empty list appears once, in order, separated");
  }

  // Recovering the stunt jump table from a block of memory. The game builds it
  // on the heap and writes it nowhere else, so the scan has to pick it out of
  // whatever else happens to be there.
  {
    constexpr std::size_t kStride = 0x44;
    constexpr int kJumps = 36;
    constexpr std::size_t kLead = 0x120;
    std::vector<unsigned char> memory(kLead + kStride * (kJumps + 2), 0);

    const auto write_float = [&memory](std::size_t offset, float value) {
      std::memcpy(memory.data() + offset, &value, sizeof(value));
    };
    const auto write_record = [&](std::size_t offset, float x, float y, int reward) {
      const float floats[kStuntJumpFloats] = {
          x, y, 10.0f, x + 8.0f, y + 8.0f, 16.0f,      // start box
          x + 60.0f, y, 9.0f, x + 90.0f, y + 20.0f, 15.0f,  // landing box
          x + 30.0f, y - 40.0f, 25.0f,                 // camera
      };
      std::memcpy(memory.data() + offset, floats, sizeof(floats));
      std::memcpy(memory.data() + offset + sizeof(floats), &reward, sizeof(reward));
    };
    for (int index = 0; index < kJumps; ++index) {
      write_record(kLead + kStride * index, -900.0f + 40.0f * index,
                   300.0f - 20.0f * index, 500 * (index + 1));
    }
    // A lone lookalike before the array, at no stride with anything: the run
    // search must not take it for a table, and must not let it shorten one.
    write_record(0x40, 120.0f, -400.0f, 1);
    // Junk that is not a box: corners that coincide, so the extent is zero.
    for (std::size_t offset = 0; offset < 0x40; offset += 4) {
      write_float(offset, 1.0f);
    }

    const std::vector<StuntJumpRecord> records =
        FindStuntJumpRecords(memory.data(), memory.size());
    Expect(records.size() >= static_cast<std::size_t>(kJumps),
           "every planted record is recognised by its shape");
    const StuntJumpRun run = BestStuntJumpRun(records, kJumps);
    Expect(run.count == kJumps, "the run is exactly the planted table");
    Expect(run.stride == kStride, "the stride is recovered from the records");
    Expect(run.offset == kLead, "the run starts at the array, not partway in");
    Expect(BestStuntJumpRun(records, 0).count == kJumps,
           "with no count to aim for the longest run stands in");

    // A longer run of the same shape in the same block, which is what an array
    // of collision volumes looks like. The wanted count has to pick the table
    // out from under it; length alone would take the decoy.
    std::vector<unsigned char> crowded = memory;
    constexpr std::size_t kDecoyLead = 0;
    constexpr std::size_t kDecoyStride = 0x50;
    constexpr int kDecoyCount = 60;
    crowded.resize(kLead + kStride * (kJumps + 2) +
                   kDecoyStride * (kDecoyCount + 2), 0);
    const std::size_t decoy_base = kLead + kStride * (kJumps + 2);
    for (int index = 0; index < kDecoyCount; ++index) {
      const std::size_t offset = decoy_base + kDecoyStride * index;
      const float floats[kStuntJumpFloats] = {
          -50.0f, -50.0f, 2.0f, -44.0f, -44.0f, 8.0f,
          -20.0f, -50.0f, 2.0f, -10.0f, -40.0f, 8.0f,
          -35.0f, -70.0f, 20.0f,
      };
      std::memcpy(crowded.data() + offset, floats, sizeof(floats));
    }
    const std::vector<StuntJumpRecord> crowded_records =
        FindStuntJumpRecords(crowded.data(), crowded.size());
    Expect(BestStuntJumpRun(crowded_records, 0).count == kDecoyCount,
           "the longer decoy wins on length alone");
    const StuntJumpRun picked = BestStuntJumpRun(crowded_records, kJumps);
    Expect(picked.count == kJumps && picked.offset == kLead,
           "the wanted count picks the table out of the same block as a decoy");
    Expect(kDecoyLead == 0, "the decoy sits after the table, not before it");

    // The pin takes the middle of the start box, whichever corner came first.
    const std::array<float, 3> centre = StuntJumpBoxCentre(records.front().values.data());
    Expect(centre[0] > 100.0f && centre[0] < 140.0f,
           "the box centre sits between its corners");

    // A buffer of alternating plus and minus one matches the box and camera
    // shape at every offset and runs long enough to read as a table. Its reward
    // field holds a float's bits and its values barely vary, so it is rejected.
    {
      std::vector<unsigned char> unit_vectors(0x20000, 0);
      for (std::size_t offset = 0; offset + 4 <= unit_vectors.size(); offset += 4) {
        const float value = (offset / 4) % 2 == 0 ? 1.0f : -1.0f;
        std::memcpy(unit_vectors.data() + offset, &value, sizeof(value));
      }
      Expect(FindStuntJumpRecords(unit_vectors.data(), unit_vectors.size()).empty(),
             "a buffer of unit vectors is not a stunt jump table");
    }

    // The same repeating shape carrying a plausible reward. Only the
    // distinct-values test separates this from a record.
    {
      const std::size_t span = kStuntJumpFloats * sizeof(float) + sizeof(int);
      std::vector<unsigned char> repeating(span * 8, 0);
      for (std::size_t offset = 0; offset + 4 <= repeating.size(); offset += 4) {
        const float value = (offset / 4) % 2 == 0 ? 40.0f : -40.0f;
        std::memcpy(repeating.data() + offset, &value, sizeof(value));
      }
      const int reward = 500;
      for (std::size_t record = 0; record * span + span <= repeating.size(); ++record) {
        std::memcpy(repeating.data() + record * span + kStuntJumpFloats * sizeof(float),
                    &reward, sizeof(reward));
      }
      Expect(FindStuntJumpRecords(repeating.data(), repeating.size()).empty(),
             "a repeating pattern with a plausible reward is still not a record");
    }

    // A record whose reward is a float's bits is rejected, and accepted again
    // when the caller turns that test off.
    {
      const std::size_t span = kStuntJumpFloats * sizeof(float) + sizeof(int);
      std::vector<unsigned char> one_record(span, 0);
      std::memcpy(one_record.data(), memory.data() + kLead,
                  kStuntJumpFloats * sizeof(float));
      const int float_bits = -1082130432;  // -1.0f
      std::memcpy(one_record.data() + kStuntJumpFloats * sizeof(float), &float_bits,
                  sizeof(float_bits));
      Expect(FindStuntJumpRecords(one_record.data(), one_record.size()).empty(),
             "a reward that is really a float's bits rejects the record");
      Expect(FindStuntJumpRecords(one_record.data(), one_record.size(), false).size() == 1,
             "the same record reads once the reward test is off");

      // The reward bounds themselves: the maximum is a reward, one past is not.
      const int at_limit = static_cast<int>(kStuntJumpMaximumReward);
      std::memcpy(one_record.data() + kStuntJumpFloats * sizeof(float), &at_limit,
                  sizeof(at_limit));
      Expect(FindStuntJumpRecords(one_record.data(), one_record.size()).size() == 1,
             "the largest allowed reward is still a reward");
      const int past_limit = at_limit + 1;
      std::memcpy(one_record.data() + kStuntJumpFloats * sizeof(float), &past_limit,
                  sizeof(past_limit));
      Expect(FindStuntJumpRecords(one_record.data(), one_record.size()).empty(),
             "one past the largest allowed reward is not");
    }

    // Nothing box-shaped at all yields nothing, rather than a short run of noise.
    std::vector<unsigned char> empty(4096, 0);
    Expect(BestStuntJumpRun(FindStuntJumpRecords(empty.data(), empty.size()), kJumps)
               .count == 0,
           "zeroed memory holds no stunt jump table");
  }

  if (failures == 0) {
    std::cout << "OK: protocol self-test passed\n";
    return 0;
  }
  return 1;
}
