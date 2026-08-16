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
#include "../src/scm_effects.hpp"
#include "../src/scm_minimap.hpp"
#include "../src/scm_packages.hpp"
#include "../src/scm_pickup_layout.hpp"
#include "../src/scm_radio.hpp"

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

  // Rampage icon planning: while the weapon equip is locked a weapon
  // rampage's icon sinks and stays sunk, the two run-them-down icons never
  // move, and the unlock raises a sunk icon, a save made while sunk
  // included (the band makes the state self-describing).
  {
    Expect(IsVehicleRampagePickup(-679.66f, -419.712f) &&
               IsVehicleRampagePickup(468.656f, -1608.79f),
           "both run-them-down rampage icons are recognized");
    Expect(!IsVehicleRampagePickup(218.22f, -1613.76f),
           "a weapon rampage icon is not");
    Expect(PlanRampageIcon(true, false, 11.0f) == RampageIconAction::kLower,
           "the weapon lock sinks a weapon rampage icon");
    Expect(PlanRampageIcon(true, false, 11.0f - kRampageLowerOffset) ==
               RampageIconAction::kLeaveAlone,
           "a sunk icon stays where it is while locked");
    Expect(PlanRampageIcon(false, false, 11.0f - kRampageLowerOffset) ==
               RampageIconAction::kRaise,
           "the unlock raises a sunk icon, a loaded save included");
    Expect(PlanRampageIcon(false, false, 11.0f) == RampageIconAction::kLeaveAlone,
           "an unlocked icon in place never moves");
    Expect(PlanRampageIcon(true, true, 11.0f) == RampageIconAction::kLeaveAlone,
           "a run-them-down icon stays collectible under the weapon lock");
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

  if (failures == 0) {
    std::cout << "OK: protocol self-test passed\n";
    return 0;
  }
  return 1;
}
