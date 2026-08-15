// Standalone protocol self-test: round-trips framing (small and chunked) and
// checks the guards, with no socket and no game. Proves the C++ protocol layer
// compiles and behaves in the 32-bit MSVC toolchain.
#include <array>
#include <iostream>
#include <map>
#include <set>
#include <vector>

#include "../src/protocol.hpp"
#include "../src/scm_completion.hpp"
#include "../src/scm_effects.hpp"
#include "../src/scm_packages.hpp"
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
  // index; a chaos trap waits until the player is controllable, so the index
  // never skips it; weather and consumables never defer.
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
    Expect(blocked.to_apply.size() == 2 && blocked.to_apply[0].type == "cash" &&
               blocked.to_apply[1].type == "trap_weather",
           "cash and weather apply while not controllable");
    Expect(blocked.new_applied_index == 2,
           "the deferring trap stops the plan and the index does not skip it");

    auto freed = PlanEffects(items, effects, 2, true);
    Expect(freed.to_apply.size() == 2 && freed.to_apply[0].type == "trap_wanted" &&
               freed.to_apply[1].type == "trap_speed_up",
           "deferred traps apply in received order once controllable");
    Expect(freed.new_applied_index == 4, "the index reaches the last effect item");

    auto done = PlanEffects(items, effects, 4, true);
    Expect(done.to_apply.empty() && done.new_applied_index == 4,
           "a fully applied list repeats nothing");

    Expect(EffectDefersUntilControllable("trap_wanted"), "a chaos trap defers");
    Expect(!EffectDefersUntilControllable("trap_weather"), "weather does not defer");
    Expect(!EffectDefersUntilControllable("cash"), "a consumable does not defer");
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

  if (failures == 0) {
    std::cout << "OK: protocol self-test passed\n";
    return 0;
  }
  return 1;
}
