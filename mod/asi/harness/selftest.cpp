// Standalone protocol self-test: round-trips framing (small and chunked) and
// checks the guards, with no socket and no game. Proves the C++ protocol layer
// compiles and behaves in the 32-bit MSVC toolchain.
#include <algorithm>
#include <array>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "../src/protocol.hpp"
#include "../src/scm_ability_locks.hpp"
#include "../src/scm_applied_reports.hpp"
#include "../src/scm_completion.hpp"
#include "../src/scm_content_locks.hpp"
#include "../src/scm_crossings.hpp"
#include "../src/scm_death_link.hpp"
#include "../src/scm_effects.hpp"
#include "../src/scm_finale_warp.hpp"
#include "../src/scm_grant_pacing.hpp"
#include "../src/scm_minimap.hpp"
#include "../src/scm_packages.hpp"
#include "../src/scm_pickup_layout.hpp"
#include "../src/scm_progress.hpp"
#include "../src/scm_radio.hpp"
#include "../src/scm_seed_stamp.hpp"
#include "../src/scm_status_panel.hpp"
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

// The panel's own geometry, for the fitting tests: a column of the frontend's own
// units, the gap between a label and the value sharing its row, the two bands the
// cover can leave the rows, and a stand-in for the font's measure.
//
// These are COPIES. The drawing's own constants sit in an anonymous namespace in
// status_page.cpp, beside the code that stretches them, and nothing here can reach
// them; status_page.cpp asserts the relations that must hold between them on its
// own side, but no assertion ties these numbers to those, so a change there has to
// be made here too. What the copies buy is the fitting being exercised at the width
// and in the band the game actually uses.
//
// The real page measures with CFont, which no console build has. A character
// averages 5.4 units on the drawn page, spaces included, so the numbers here are
// the ones the game works in.
constexpr float kColumnUnits = 146.0f;
constexpr float kLabelGapUnits = 5.0f;
constexpr float kBandUnits = 337.0f;
// The band the panel keeps where the borrowed page's back entry cannot be moved,
// which is the one every seed gets if another mod owns that entry.
constexpr float kFallbackBandUnits = 251.0f;
constexpr float kDesignRowUnits = 13.0f;
constexpr float kUnitsPerCharacter = 5.4f;

float MeasureUnits(const std::string& text) {
  return kUnitsPerCharacter * static_cast<float>(text.size());
}

// The heading face draws wider than the body face at the same scale, which is why
// the fitting measures headings separately. A fifth again is enough for the tests
// to tell the two apart.
float MeasureHeadingUnits(const std::string& text) {
  return 1.2f * MeasureUnits(text);
}

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

    // Draining: held between games, and holding must cost a delay and never a
    // check. The queue survives being held, survives a game boundary, and
    // leaves in the order it was found. Control is deliberately NOT the hold
    // condition: a check leaving touches no game state, and the on-foot shops
    // freeze the player from the door to the exit, so waiting for control would
    // strand every purchase made inside one.
    std::vector<std::int64_t> queued = {542000001, 542000002};
    Expect(DrainChecks(queued, true).empty(),
           "nothing leaves while the queue is held");
    Expect(queued.size() == 2,
           "and what was found stays queued rather than being dropped");

    // Found while held, then the hold lifts: everything leaves, once, in
    // order. This is the whole contract, since a check dropped here can never
    // be found again.
    queued.push_back(542000003);
    const std::vector<std::int64_t> released = DrainChecks(queued, false);
    Expect(released.size() == 3 && released[0] == 542000001 &&
               released[1] == 542000002 && released[2] == 542000003,
           "held then released sends every check, in the order found");
    Expect(queued.empty(), "and the queue is empty behind them");
    Expect(DrainChecks(queued, false).empty(),
           "a second drain sends nothing, so no check is sent twice");

    // A check found in a game the player abandons survives the boundary. This
    // is the rule that already shipped broken once, so it is pinned against
    // the function the boundary actually calls rather than against a drain.
    std::vector<std::int64_t> across = {542000004, 542000005};
    GameScopedGrants grants;
    grants.cursor = UnlockCursor{7, 9042};
    TakeGrantSlot(grants.pacer, 1000, 250, 5000, 8);
    ResetGrantsForNewGame(grants, across);
    Expect(across.size() == 2 && across[0] == 542000004 && across[1] == 542000005,
           "a game boundary leaves every queued check where it is");
    Expect(grants.cursor.arrival_index == -1 && grants.cursor.global_index == -1 &&
               !grants.pacer.started,
           "and takes the pacer and the rotation cursor with it");
    Expect(DrainChecks(across, false).size() == 2,
           "so both reach the server in the game after");
  }

  // A send that fails hands its locations back, because draining is the only
  // thing that can lose one: detection never finds a location twice, and a save
  // folds its completion global into the next baseline.
  {
    std::vector<std::int64_t> queued;
    RequeueChecks(queued, {542000010, 542000011});
    Expect(queued.size() == 2 && queued[0] == 542000010 && queued[1] == 542000011,
           "an undelivered batch goes back on an empty queue, in the order found");

    std::vector<std::int64_t> found_since = {542000020};
    RequeueChecks(found_since, {542000010, 542000011});
    Expect(found_since.size() == 3 && found_since[0] == 542000010 &&
               found_since[1] == 542000011 && found_since[2] == 542000020,
           "and in front of whatever the game found while the send was failing");

    std::vector<std::int64_t> already = {542000010, 542000030};
    RequeueChecks(already, {542000010, 542000011});
    Expect(already.size() == 3 && already[0] == 542000010 &&
               already[1] == 542000011 && already[2] == 542000030,
           "a location the queue already holds is not queued twice");

    std::vector<std::int64_t> repeated;
    RequeueChecks(repeated, {542000010, 542000010});
    Expect(repeated.size() == 1,
           "nor is one the failed batch itself repeated");

    std::vector<std::int64_t> untouched = {542000040};
    RequeueChecks(untouched, {});
    Expect(untouched.size() == 1 && untouched[0] == 542000040,
           "and a send that failed with nothing left to deliver changes nothing");

    // The round trip: drain, fail, hand back, drain again.
    std::vector<std::int64_t> round = {542000050, 542000051};
    const std::vector<std::int64_t> drained = DrainChecks(round, false);
    Expect(round.empty() && drained.size() == 2, "draining empties the queue");
    RequeueChecks(round, drained);
    Expect(DrainChecks(round, false).size() == 2,
           "so a failed drain loses nothing once it hands the batch back");
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

  // The hunt goal's ending: the flag rises only while the client asks AND the
  // player is controllable, the same deferral point every item application
  // waits on. An ask that outran control would raise it inside the intro or a
  // cutscene, where the script's own launch conditions cannot hold anyway.
  {
    Expect(ShouldRaiseFinaleWarp(true, true), "the ending is asked for and free to play");
    Expect(!ShouldRaiseFinaleWarp(true, false),
           "the ending waits while the player is not controllable");
    Expect(!ShouldRaiseFinaleWarp(false, true), "no ask, no ending");
    Expect(!ShouldRaiseFinaleWarp(false, false), "no ask and no control, no ending");
  }

  // DeathLink, outbound: the wasted state reports once on its edge, an arrest is
  // not a death (it never reaches the predicate as wasted), the echo of a kill
  // this mod made is kept out of the multiworld, and a death with no client is
  // dropped rather than queued.
  {
    Expect(ShouldReportDeath(true, false, false, true), "a fresh death reports");
    Expect(!ShouldReportDeath(true, true, false, true),
           "the frames after the death report nothing more");
    Expect(!ShouldReportDeath(false, true, false, true),
           "coming back from the dead is not a death");
    Expect(!ShouldReportDeath(true, false, true, true),
           "the echo of a linked death is not reported back");
    Expect(!ShouldReportDeath(true, false, false, false),
           "a death with no client connected is dropped rather than queued");
  }

  // The echo window, which is the whole guard against a death bouncing between
  // two linked slots forever: a kill arms it, the wasted state it was armed for
  // ends it, and its deadline ends it for a kill that never killed. Sequenced
  // rather than asserted one call at a time, since the ordering is what makes it
  // correct.
  {
    const unsigned int armed_at = 1000;
    const unsigned int window = 5000;
    const DeathLinkEcho armed = ArmDeathLinkEcho(armed_at, window);
    Expect(DeathLinkEchoSuppressing(armed, armed_at),
           "the frame that armed the window is inside it");
    Expect(DeathLinkEchoSuppressing(armed, armed_at + window - 1),
           "the window holds up to its deadline");
    Expect(!DeathLinkEchoSuppressing(armed, armed_at + window),
           "the window is over on its deadline");
    Expect(!DeathLinkEchoSuppressing(DeathLinkEcho{}, armed_at),
           "an unarmed window suppresses nothing");

    // The frames between the kill and the wasted state it caused: no edge yet, so
    // the window is still holding and the death it is waiting for is the one it
    // will swallow.
    const DeathLinkEcho waiting =
        AdvanceDeathLinkEcho(armed, armed_at + 16, false, false);
    Expect(DeathLinkEchoSuppressing(waiting, armed_at + 16),
           "the window waits for the wasted state its kill caused");
    Expect(!ShouldReportDeath(true, false, DeathLinkEchoSuppressing(waiting, armed_at + 32),
                              true),
           "and that wasted state is not reported");

    // The wasted edge ends it, so a second death moments later is a real one.
    const DeathLinkEcho spent =
        AdvanceDeathLinkEcho(waiting, armed_at + 32, true, false);
    Expect(!DeathLinkEchoSuppressing(spent, armed_at + 32),
           "the wasted edge it was armed for ends the window");
    Expect(ShouldReportDeath(true, false, DeathLinkEchoSuppressing(spent, armed_at + 48),
                             true),
           "a death right after the echo is reported");

    // A kill that never killed: the deadline ends the window instead, and the
    // next real death reports rather than being taken for the echo.
    const DeathLinkEcho expired =
        AdvanceDeathLinkEcho(armed, armed_at + window, false, false);
    Expect(!DeathLinkEchoSuppressing(expired, armed_at + window),
           "a kill that never killed stops being waited for");
    Expect(ShouldReportDeath(true, false, DeathLinkEchoSuppressing(expired, armed_at + window),
                             true),
           "and the next real death is reported");

    // The clock wrapping: a window armed just before the wrap still holds after
    // it, since the difference is taken signed.
    const unsigned int before_wrap = 0xFFFFF000u;
    const DeathLinkEcho across = ArmDeathLinkEcho(before_wrap, window);
    Expect(DeathLinkEchoSuppressing(across, before_wrap + 1),
           "a window armed before the clock wraps still holds after it");
    Expect(!DeathLinkEchoSuppressing(across, before_wrap + window),
           "and still ends on its deadline");
  }

  // DeathLink, inbound: the kill waits for control, is dropped when Tommy is
  // already dying or arrested, and needs a player to kill. The already-dying
  // test outranks the control test, since the wasted fade holds control too and
  // a held death would land on the frame Tommy leaves the hospital.
  {
    Expect(PlanDeathLink(true, true, true, true) == DeathLinkAction::kKill,
           "a linked death kills a controllable player");
    Expect(PlanDeathLink(false, true, true, true) == DeathLinkAction::kHold,
           "no death pending, nothing happens");
    Expect(PlanDeathLink(true, true, false, true) == DeathLinkAction::kHold,
           "a linked death waits while the player is not controllable");
    Expect(PlanDeathLink(true, false, true, true) == DeathLinkAction::kHold,
           "a linked death waits for a player to kill");
    Expect(PlanDeathLink(true, true, false, false) == DeathLinkAction::kDrop,
           "a death arriving mid-death is dropped, not held for the respawn");
    Expect(PlanDeathLink(true, true, true, false) == DeathLinkAction::kDrop,
           "a death arriving during an arrest is dropped, not saved for the door");
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

    auto blocked = PlanEffects(items, effects, 0, false, kEffectsPerFrame);
    Expect(blocked.to_apply.empty(),
           "nothing applies while the player is not controllable");
    Expect(blocked.new_applied_index == 0,
           "the index holds while the player is not controllable");

    auto freed = PlanEffects(items, effects, 0, true, 4);
    Expect(freed.to_apply.size() == 4 && freed.to_apply[0].type == "cash" &&
               freed.to_apply[1].type == "trap_weather" &&
               freed.to_apply[2].type == "trap_wanted" &&
               freed.to_apply[3].type == "trap_speed_up",
           "every pending effect applies in received order once controllable");
    Expect(freed.new_applied_index == 4, "the index reaches the last effect item");

    auto resumed = PlanEffects(items, effects, 2, true, 4);
    Expect(resumed.to_apply.size() == 2 &&
               resumed.to_apply[0].type == "trap_wanted" &&
               resumed.to_apply[1].type == "trap_speed_up",
           "a saved index resumes past the already-applied effects");

    auto done = PlanEffects(items, effects, 4, true, 4);
    Expect(done.to_apply.empty() && done.new_applied_index == 4,
           "a fully applied list repeats nothing");

    // The per-frame cap: a backlog arrives at the cap's rate, in received
    // order, and the index moves only as far as the frame actually applied, so
    // the next frame resumes exactly where this one stopped.
    auto capped = PlanEffects(items, effects, 0, true, 1);
    Expect(capped.to_apply.size() == 1 && capped.to_apply[0].type == "cash",
           "the cap holds a frame to its share of a backlog");
    Expect(capped.new_applied_index == 1,
           "the index counts what the frame applied, not what was pending");

    auto next_frame = PlanEffects(items, effects, capped.new_applied_index, true, 1);
    Expect(next_frame.to_apply.size() == 1 &&
               next_frame.to_apply[0].type == "trap_weather",
           "the frame after resumes at the next effect in received order");

    // Draining the whole list one frame at a time reaches every effect exactly
    // once, in received order, however many frames that takes.
    int index = 0;
    std::vector<std::string> drained;
    for (int frame = 0; frame < 10; ++frame) {
      const EffectPlan step = PlanEffects(items, effects, index, true, 1);
      if (step.to_apply.empty()) break;
      for (const ItemEffect& effect : step.to_apply) drained.push_back(effect.type);
      index = step.new_applied_index;
    }
    const std::vector<std::string> expected = {"cash", "trap_weather",
                                               "trap_wanted", "trap_speed_up"};
    Expect(drained == expected && index == 4,
           "a capped drain applies every effect once, in order");

    // A cap of nothing applies nothing and holds the index, the same contract
    // the toast planner keeps for a zero cap.
    auto none = PlanEffects(items, effects, 0, true, 0);
    Expect(none.to_apply.empty() && none.new_applied_index == 0,
           "a zero cap applies nothing and holds the index");
  }

  // Grant pacing: a grant leaves at the interval, eight to a window, and a
  // burst that empties the window waits for the next one. The unlock steps
  // pick the next global to raise and every global to lower.
  {
    GrantPacer pacer;
    // The first ask is always allowed and starts both the interval and the
    // window at that moment.
    Expect(TakeGrantSlot(pacer, 1000, 250, 5000, 8), "the first grant goes now");
    Expect(!TakeGrantSlot(pacer, 1100, 250, 5000, 8),
           "a second grant inside the interval waits");
    Expect(TakeGrantSlot(pacer, 1250, 250, 5000, 8),
           "a grant one interval later goes");

    // Eight to a window: asking every interval for one whole window grants
    // eight and then refuses, and the window rolling opens it again.
    GrantPacer window;
    unsigned int now = 0;
    int granted = 0;
    for (int step = 0; step * 250 < 5000; ++step) {
      if (TakeGrantSlot(window, now, 250, 5000, 8)) ++granted;
      now += 250;
    }
    Expect(granted == 8, "a window holds a burst to eight grants");
    Expect(!TakeGrantSlot(window, 4999, 250, 5000, 8),
           "the ninth grant waits for the window to roll");
    Expect(TakeGrantSlot(window, 5000, 250, 5000, 8),
           "the window rolling opens the next burst");

    // A pacer of nothing never grants, the same shape the effect cap keeps.
    GrantPacer refused;
    Expect(!TakeGrantSlot(refused, 1000, 250, 5000, 0),
           "a window of nothing never grants");

    // One global at a time: a target above what the game holds is a grant, a
    // target below it comes back at once, and a target it already holds does
    // nothing. Reading the game rather than a memory is what carries a load,
    // where the save brings its own values, and what heals a global a script
    // cleared behind the mod's back.
    Expect(PlanUnlock(5, 3, false) == UnlockAction::kRaiseAsGrant,
           "a global short of its target is handed over as a grant");
    Expect(PlanUnlock(3, 3, false) == UnlockAction::kNone,
           "a global already holding its target is left alone");
    Expect(PlanUnlock(2, 4, false) == UnlockAction::kLowerNow,
           "a global above its target comes back at once, unpaced");
    Expect(PlanUnlock(0, 3, false) == UnlockAction::kLowerNow,
           "what a stale save restored is taken back at once");
    Expect(PlanUnlock(3, 0, false) == UnlockAction::kRaiseAsGrant,
           "a global a script cleared is handed over again");

    // A global the config flags stamp every frame is theirs: lowering one would
    // fight the stamp for as long as the game runs, so it is left alone. Raising
    // one is still a grant, since the stamp never sits below an item target.
    Expect(PlanUnlock(0, 1, true) == UnlockAction::kNone,
           "a stamped global above its target is left to the stamp");
    Expect(PlanUnlock(2, 1, true) == UnlockAction::kNone,
           "a stamped global below its target is left alone too, since the "
           "stamp would take the raise straight back");

    // The rotation. Three pending globals, one of them stuck: something else
    // in the game rewrites 9010 every frame, so it never reaches its target.
    // Always taking the lowest pending index would spend every slot on it and
    // no other unlock would ever arrive.
    // Indices are deliberately not consecutive, so "the next above the cursor"
    // cannot pass by behaving as "the cursor plus one" or "the next position".
    const std::vector<UnlockObservation> pending = {
        {9010, 3, 0, false}, {9017, 5, 1, false}, {9026, 2, 0, false}};
    const UnlockPlan from_start = PlanUnlocks(pending, UnlockCursor{});
    Expect(from_start.has_raise && from_start.raise_index == 9010 &&
               from_start.raise_value == 3,
           "the first raise of a pass is the lowest pending global");
    Expect(PlanUnlocks(pending, UnlockCursor{0, 9010}).raise_index == 9017 &&
               PlanUnlocks(pending, UnlockCursor{0, 9010}).raise_value == 5,
           "the next starts past the one just handed over");
    Expect(PlanUnlocks(pending, UnlockCursor{0, 9017}).raise_index == 9026 &&
               PlanUnlocks(pending, UnlockCursor{0, 9017}).raise_value == 2,
           "and the next past that, so a stuck global costs one slot a pass");
    // The wrap carries the TARGET, not what the global already holds: a wrap
    // that wrote the current value would spin forever on the same global and
    // its item would never apply.
    Expect(PlanUnlocks(pending, UnlockCursor{0, 9026}).raise_index == 9010 &&
               PlanUnlocks(pending, UnlockCursor{0, 9026}).raise_value == 3,
           "a pass that runs out wraps to the lowest pending global again");
    Expect(PlanUnlocks(pending, UnlockCursor{0, 9999}).raise_index == 9010 &&
               PlanUnlocks(pending, UnlockCursor{0, 9999}).raise_value == 3,
           "a cursor above every pending global wraps rather than stalling");

    // One pending global that keeps needing the same raise is served every
    // pass rather than skipped for being the one just handed over.
    const std::vector<UnlockObservation> alone = {{9010, 4, 1, false}};
    Expect(PlanUnlocks(alone, UnlockCursor{0, 9010}).has_raise &&
               PlanUnlocks(alone, UnlockCursor{0, 9010}).raise_index == 9010 &&
               PlanUnlocks(alone, UnlockCursor{0, 9010}).raise_value == 4,
           "a single pending global is retried, at its target, not starved");

    // Lowering is not paced and not rationed: every global above its target
    // comes back in one plan, alongside whichever single raise was chosen.
    const std::vector<UnlockObservation> mixed = {
        {9010, 0, 3, false}, {9011, 2, 0, false}, {9012, 1, 4, false},
        {9013, 0, 2, true}};
    const UnlockPlan both = PlanUnlocks(mixed, UnlockCursor{});
    Expect(both.to_lower.size() == 2 && both.to_lower[0].first == 9010 &&
               both.to_lower[0].second == 0 && both.to_lower[1].first == 9012 &&
               both.to_lower[1].second == 1,
           "every global above its target is lowered in one plan");
    Expect(both.has_raise && both.raise_index == 9011 && both.raise_value == 2,
           "and exactly one raise is chosen alongside them");
    Expect(!PlanUnlocks({{9013, 0, 2, true}}, UnlockCursor{}).has_raise &&
               PlanUnlocks({{9013, 0, 2, true}}, UnlockCursor{}).to_lower.empty(),
           "a stamped global is neither raised nor lowered");

    Expect(!PlanUnlocks({}, UnlockCursor{}).has_raise,
           "nothing pending is nothing planned");

    // THE SWEEP IS IN ARRIVAL ORDER, and every case above carries arrival 0 so
    // the key falls back to global index and they mean what they always meant.
    // Here the two orders DISAGREE, which is the ordinary case: global numbering
    // has nothing to do with when an item arrived.
    //
    // What this defends is measured, not argued. Sweeping by global index while
    // reporting in received order showed the player nothing for eleven seconds on
    // a twenty-item release and then all twenty in one frame, because the item
    // that arrived first sat on the highest global and so was granted last.
    const std::vector<UnlockObservation> reversed = {
        {9010, 1, 0, false, 2}, {9017, 1, 0, false, 1}, {9026, 1, 0, false, 0}};
    const UnlockPlan first_arrival = PlanUnlocks(reversed, UnlockCursor{});
    Expect(first_arrival.has_raise && first_arrival.raise_index == 9026,
           "the first raise serves the item that arrived first, not the lowest "
           "global");
    Expect(PlanUnlocks(reversed, UnlockCursor{0, 9026}).raise_index == 9017,
           "and the next serves the item that arrived after it");
    Expect(PlanUnlocks(reversed, UnlockCursor{1, 9017}).raise_index == 9010,
           "and so on down the arrival order");
    Expect(PlanUnlocks(reversed, UnlockCursor{2, 9010}).raise_index == 9026,
           "a pass that runs out wraps to the earliest arrival again");

    // Ties break on global index, so the district globals one content item
    // releases are consecutive in the sweep. Served one per pass instead, that
    // item would need eleven passes to land and would hold every later report
    // for all of them.
    const std::vector<UnlockObservation> one_item_many_globals = {
        {9101, 1, 0, false, 4}, {9102, 1, 0, false, 4}, {9103, 1, 0, false, 4},
        {9200, 1, 0, false, 5}};
    Expect(PlanUnlocks(one_item_many_globals, UnlockCursor{}).raise_index == 9101,
           "a tied arrival starts at the lowest global");
    Expect(PlanUnlocks(one_item_many_globals, UnlockCursor{4, 9101}).raise_index == 9102,
           "and the next tied global follows it rather than the next arrival");
    Expect(PlanUnlocks(one_item_many_globals, UnlockCursor{4, 9103}).raise_index == 9200,
           "and the next arrival only comes once the tie is exhausted");

    // The rotation still bounds a global that cannot hold its target, on the
    // arrival key rather than the global index.
    const std::vector<UnlockObservation> stuck_early = {
        {9010, 1, 0, false, 0}, {9017, 1, 0, false, 1}};
    Expect(PlanUnlocks(stuck_early, UnlockCursor{0, 9010}).raise_index == 9017,
           "an early global that cannot hold costs one slot a pass, not every "
           "slot");

    // The plan carries the key it chose, so the caller sets its cursor from the
    // selection rather than searching the observations for it again. A cursor
    // pinned by a search that missed would reinstate the starvation the rotation
    // exists to prevent.
    Expect(first_arrival.raise_arrival_index == 0,
           "the plan reports the arrival key of the raise it chose");
    Expect(PlanUnlocks(reversed, UnlockCursor{2, 9010}).raise_arrival_index == 0,
           "and reports it on the wrap too, not only inside a pass");

    // ONE-SHOT EFFECTS ARE ORDERED AGAINST THE RAISES, since both draw on the
    // same grant budget. Without a key of their own the unlock path took every
    // slot while any global was below its target, so an effect early in the list
    // waited out the whole unlock backlog and held every landing report behind it.
    const std::map<std::int64_t, ItemEffect> paced_effects = {
        {6001, ItemEffect{"cash", 500, true}}, {6002, ItemEffect{"armor", 0, false}}};
    const std::vector<std::pair<std::int64_t, std::int64_t>> effects_and_unlocks = {
        {0, 5001}, {1, 6001}, {2, 5002}, {3, 6002}};
    const NextEffect first_effect =
        NextPendingEffect(effects_and_unlocks, paced_effects, 0);
    Expect(first_effect.pending && first_effect.received_index == 1,
           "the next pending effect is named by its RECEIVED index, not its "
           "position among the effects");
    const NextEffect second_effect =
        NextPendingEffect(effects_and_unlocks, paced_effects, 1);
    Expect(second_effect.pending && second_effect.received_index == 3,
           "and the index moving on names the one after it");
    Expect(!NextPendingEffect(effects_and_unlocks, paced_effects, 2).pending,
           "an index past every effect leaves none pending");
    Expect(!NextPendingEffect(effects_and_unlocks, {}, 0).pending,
           "a seed whose items carry no effects has none pending");
    Expect(!NextPendingEffect({}, paced_effects, 0).pending,
           "and neither does an empty item list");

    // THE YIELD RULE, which decides which of the two kinds spends this frame's
    // slot. Held here rather than inline in OnGameFrame because the harness cannot
    // compile that file, which is the one reason the 2026-08-21 note gives for how
    // both of its shipped defects got past every gate in the repo.
    Expect(RaiseYieldsToEffect(true, 9, true, 4, true),
           "a raise gives up its slot to an effect that arrived before it");
    Expect(!RaiseYieldsToEffect(true, 4, true, 9, true),
           "and keeps it against an effect that arrived after it");
    Expect(!RaiseYieldsToEffect(true, 9, true, 9, true),
           "an equal key is not earlier, so the raise keeps its slot");
    Expect(!RaiseYieldsToEffect(true, 9, false, 0, true),
           "nothing to yield to is not a yield");
    // Yielding to an effect that cannot run would spend the frame on neither: the
    // effect path needs a player ped to write into.
    Expect(!RaiseYieldsToEffect(true, 9, true, 4, false),
           "and neither is yielding to an effect with no player to apply it to");
    Expect(!RaiseYieldsToEffect(false, 0, true, 4, true),
           "no raise is not a yield either, since the effect takes the slot on "
           "its own");

    // WHETHER THE WORLD IS PLAYABLE AT ALL, which is what a grant and a landing
    // report wait for. Every field is a separate reason, so a state that reads
    // playable has to clear all of them.
    PlayableState live;
    live.controllable = true;
    live.player_playing = true;
    Expect(WorldIsPlayable(live), "a live world hands things over");

    PlayableState in_cutscene = live;
    in_cutscene.controllable = false;
    Expect(!WorldIsPlayable(in_cutscene),
           "a cutscene holds, which is the one condition that always held");

    PlayableState user_paused = live;
    user_paused.paused = true;
    Expect(!WorldIsPlayable(user_paused), "the game's own pause holds");

    PlayableState menu = live;
    menu.menu_open = true;
    Expect(!WorldIsPlayable(menu),
           "and so does the frontend menu, which the pause flags do not always "
           "answer for");

    PlayableState wasted = live;
    wasted.player_playing = false;
    Expect(!WorldIsPlayable(wasted),
           "a wasted or arrested Tommy holds, since he is not playing");

    // The shop stand needs BOTH halves. An interior alone would hold every indoor
    // mission for as long as it lasted, and the help box alone is the channel
    // every tutorial hint in the game uses.
    PlayableState at_a_stand = live;
    at_a_stand.in_interior = true;
    at_a_stand.help_message_up = true;
    Expect(!WorldIsPlayable(at_a_stand), "a shop stand's help box indoors holds");

    PlayableState indoors_only = live;
    indoors_only.in_interior = true;
    Expect(WorldIsPlayable(indoors_only),
           "being indoors on its own does not, so an indoor mission keeps "
           "flowing");

    PlayableState hint_outdoors = live;
    hint_outdoors.help_message_up = true;
    Expect(WorldIsPlayable(hint_outdoors),
           "and neither does a help box outdoors, which is every tutorial hint");

    // A clock that restarts is caught by the pacer itself, on the only
    // evidence there is: a `now` earlier than one it was already handed. The
    // game restart that does this happens where no caller has a frame to
    // watch, so a pacer holding pre-restart timestamps would otherwise refuse
    // every grant until real time passed them.
    GrantPacer restarted;
    Expect(TakeGrantSlot(restarted, 3'000'000, 250, 5000, 8),
           "a grant goes on a long-running clock");
    Expect(!TakeGrantSlot(restarted, 3'000'100, 250, 5000, 8),
           "and the interval still holds on that clock");
    Expect(TakeGrantSlot(restarted, 1, 250, 5000, 8),
           "a clock that restarted grants at once rather than stalling");
    Expect(!TakeGrantSlot(restarted, 100, 250, 5000, 8),
           "and the interval applies again from the new clock");

    // The restart the guard CANNOT see, and why it costs nothing. A game that
    // handed its backlog over early leaves the window start low, so a restart
    // hours later can land above it: the difference is positive and the pacer
    // carries the old counters. It can only under-grant, and the stale window
    // rolls within one window plus one interval of that start, so the whole
    // cost is a few seconds of extra wait.
    GrantPacer carried;
    unsigned int early = 1000;
    for (int grant = 0; grant < 8; ++grant) {
      TakeGrantSlot(carried, early, 250, 5000, 8);
      early += 250;
    }
    // Probed at the interval rather than inside it, so what refuses is the
    // full window and not the spacing: at 3000 the interval is satisfied
    // exactly and the window has not rolled, so only the count of eight can
    // say no. That also asserts the loop above really did fill the window.
    Expect(!TakeGrantSlot(carried, 3000, 250, 5000, 8),
           "a window handed over early refuses on its count, not its spacing");
    Expect(!TakeGrantSlot(carried, 1200, 250, 5000, 8),
           "a restart landing above the last window start goes unseen");
    Expect(TakeGrantSlot(carried, 6000, 250, 5000, 8),
           "and costs only the roll of the stale window, not a stall");

    // The worst case of that bound is one window AND one interval, which the
    // fixture above cannot reach: handing eight over early leaves the next
    // allowed time behind the roll, so the interval never binds. Spending the
    // eighth grant late, just inside the window, is what puts the two terms
    // in the other order and pins the sum.
    GrantPacer late;
    unsigned int spent = 1000;
    for (int grant = 0; grant < 7; ++grant) {
      TakeGrantSlot(late, spent, 250, 5000, 8);
      spent += 250;
    }
    Expect(TakeGrantSlot(late, 5999, 250, 5000, 8),
           "the eighth grant of a window can land at the end of it");
    // Asserted rather than assumed: without this the loop above could spend no
    // grants at all and every line below would still pass, pinning the interval
    // and nothing about the window.
    Expect(late.held == 8,
           "and it really is the eighth, so the window is what fills");
    Expect(!TakeGrantSlot(late, 6248, 250, 5000, 8),
           "after which the interval still binds past the window roll");
    Expect(TakeGrantSlot(late, 6249, 250, 5000, 8),
           "so the wait is one window and one interval, never more");

    // The window SLIDES, which is the whole point of remembering a time per
    // grant. An anchored window cleared whole refills at its boundary, so eight
    // at the end of one and eight at the start of the next put fifteen inside a
    // single span. Here each time ages out on its own, so the ninth grant waits
    // for the first to be a full window old however the boundary falls.
    GrantPacer sliding;
    unsigned int at = 1000;
    for (int grant = 0; grant < 8; ++grant) {
      Expect(TakeGrantSlot(sliding, at, 250, 5000, 8),
             "eight grants fill the window");
      at += 250;
    }
    Expect(!TakeGrantSlot(sliding, 5999, 250, 5000, 8),
           "and a ninth is refused while the first is under a window old");
    Expect(TakeGrantSlot(sliding, 6000, 250, 5000, 8),
           "arriving only once that first grant has aged out of it");

    // The guarantee itself, swept rather than reasoned about: no five second span
    // may hold more than eight grants.
    //
    // The sweep asks with a QUIET GAP in the middle, which is what discriminates
    // and what the game actually does: nothing to deliver for a while, then a
    // backlog. Asked continuously, the anchored window this replaced also holds
    // eight, so a continuous sweep would pass either way and pin nothing. With
    // the gap, the anchored window let ELEVEN through, because its quota refilled
    // on a boundary the gap had moved.
    {
      GrantPacer swept;
      std::vector<unsigned int> granted;
      for (unsigned int clock = 1000; clock <= 30000; clock += 50) {
        if (clock > 2000 && clock < 5200) continue;  // nothing waiting to go
        if (TakeGrantSlot(swept, clock, 250, 5000, 8)) granted.push_back(clock);
      }
      std::size_t worst = 0;
      for (std::size_t first = 0; first < granted.size(); ++first) {
        std::size_t inside = 0;
        for (std::size_t next = first; next < granted.size(); ++next) {
          if (granted[next] - granted[first] < 5000) ++inside;
        }
        if (inside > worst) worst = inside;
      }
      Expect(granted.size() > 20 && worst <= 8,
             "no five second span holds more than eight grants, however the "
             "window boundaries fall");
    }

    // THE SHIPPED NUMBERS, as a tripwire and not as coverage. The repo
    // deliberately does not pin the derived figures, but the window cap is the
    // number the 2026-08-21 note names as the one to lower if a streaming crash
    // comes back, so it should not be possible to move it without saying so.
    //
    // The literal is the point. Comparing the measured drain against
    // kGrantsPerWindow instead passes at every value, which is the same shape as
    // pinning a chosen index rather than a chosen value.
    Expect(kGrantsPerWindow == 16,
           "the shipped window cap is sixteen grants");
    Expect(kGrantIntervalMs == 250 && kGrantWindowMs == 5000,
           "at one grant every 250 ms over a five second window");
    // What that combination MEANS, which is the part worth a test rather than a
    // constant: a whole window's worth of grants fits inside one window, so the
    // interval is what paces a backlog and the cap only ever trims the tail.
    // A cap of twenty makes the two exactly equal and the assertion below fails,
    // so twenty is already too many rather than the last one that fits.
    Expect(static_cast<unsigned int>(kGrantsPerWindow) * kGrantIntervalMs <
               kGrantWindowMs,
           "so a full window of grants fits inside one window and the interval "
           "is the binding constraint");
    {
      GrantPacer shipped;
      int granted = 0;
      for (unsigned int now = 0; now < 4000; now += 10) {
        if (TakeGrantSlot(shipped, now, kGrantIntervalMs, kGrantWindowMs,
                          kGrantsPerWindow)) {
          ++granted;
        }
      }
      Expect(granted == 16,
             "and a backlog really does drain sixteen inside four seconds");
      Expect(!TakeGrantSlot(shipped, 4990, kGrantIntervalMs, kGrantWindowMs,
                            kGrantsPerWindow),
             "the seventeenth waits for the oldest to age out");
      Expect(TakeGrantSlot(shipped, 5000, kGrantIntervalMs, kGrantWindowMs,
                           kGrantsPerWindow),
             "and goes as soon as it has");
    }
  }

  // Landing reports: which received items the game has acted on, in received
  // order, so a toast names a grant that has happened rather than a packet that
  // has arrived. The order is Archipelago's and not the grants', so a pending
  // item holds the ones behind it, and the one global no grant can ever raise is
  // read as landed so that hold cannot become permanent.
  {
    // Three items on three globals, ascending as PlanUnlocks requires. Unequal
    // gaps, so "the next global up" cannot be told from "the index plus one".
    const std::map<std::int64_t, int> item_globals = {
        {5001, 9010}, {5002, 9017}, {5003, 9026}};
    const std::map<std::int64_t, std::vector<int>> no_districts;
    const std::map<std::int64_t, ItemEffect> no_effects;
    const std::vector<std::pair<std::int64_t, std::int64_t>> three = {
        {0, 5001}, {1, 5002}, {2, 5003}};

    // Every global holding its target: the whole list reports, in received order.
    const std::vector<UnlockObservation> all_held = {
        {9010, 1, 1, false}, {9017, 1, 1, false}, {9026, 1, 1, false}};
    const AppliedReportPlan every = PlanAppliedReports(
        three, item_globals, no_districts, no_effects, all_held, 0, {},
        AppliedReportOrder::kHoldForArrival);
    Expect(every.to_report.size() == 3 && every.to_report[0] == 0 &&
               every.to_report[1] == 1 && every.to_report[2] == 2,
           "every landed item reports, in received order");

    // The middle one still pending: the first reports and the LAST WAITS, even
    // though its own global is held. Received order is the whole point, so a
    // later landing never overtakes an earlier one.
    const std::vector<UnlockObservation> middle_pending = {
        {9010, 1, 1, false}, {9017, 1, 0, false}, {9026, 1, 1, false}};
    const AppliedReportPlan held_back = PlanAppliedReports(
        three, item_globals, no_districts, no_effects, middle_pending, 0, {},
        AppliedReportOrder::kHoldForArrival);
    Expect(held_back.to_report.size() == 1 && held_back.to_report[0] == 0,
           "a pending item holds every item behind it, whatever their globals "
           "hold");

    // Nothing reports twice, and an item marked already told does not block the
    // ones behind it: the baseline marks whatever a save held wherever it sits.
    const AppliedReportPlan past_told = PlanAppliedReports(
        three, item_globals, no_districts, no_effects, all_held, 0, {0, 1},
        AppliedReportOrder::kHoldForArrival);
    Expect(past_told.to_report.size() == 1 && past_told.to_report[0] == 2,
           "an index already reported is walked past and never repeated");

    // A global the config stamp owns is read as landed. PlanUnlock refuses to
    // raise one, so an item waiting for that raise would hold every later report
    // for the rest of the seed. Mutating `true` to `false` here turns this red.
    const std::vector<UnlockObservation> stamped_short = {
        {9010, 2, 0, true}, {9017, 1, 1, false}, {9026, 1, 1, false}};
    const AppliedReportPlan stamped = PlanAppliedReports(
        three, item_globals, no_districts, no_effects, stamped_short, 0, {},
        AppliedReportOrder::kHoldForArrival);
    Expect(stamped.to_report.size() == 3,
           "an item on a stamped global lands rather than holding the queue");

    // Two copies of one item raise one global straight to two, so both land in
    // the same frame and both get a row: the player received two things.
    const std::vector<std::pair<std::int64_t, std::int64_t>> two_copies = {
        {0, 5001}, {1, 5001}};
    const std::vector<UnlockObservation> counted_two = {{9010, 2, 2, false}};
    const AppliedReportPlan copies = PlanAppliedReports(
        two_copies, item_globals, no_districts, no_effects, counted_two, 0, {},
        AppliedReportOrder::kHoldForArrival);
    Expect(copies.to_report.size() == 2,
           "both copies behind one raise report, one row per item received");
    const std::vector<UnlockObservation> counted_one = {{9010, 2, 1, false}};
    Expect(PlanAppliedReports(two_copies, item_globals, no_districts, no_effects,
                              counted_one, 0, {},
                              AppliedReportOrder::kHoldForArrival).to_report.empty(),
           "a global short of its count has landed for neither copy");

    // A content item releases many district globals and has landed only when
    // every one of them holds. Its own class global counts too, so both maps are
    // asked and the answers are ANDed.
    const std::map<std::int64_t, std::vector<int>> districts = {
        {5001, {9101, 9102, 9103}}};
    const std::vector<std::pair<std::int64_t, std::int64_t>> one_content = {{0, 5001}};
    const std::vector<UnlockObservation> two_of_three = {
        {9010, 1, 1, false}, {9101, 1, 1, false}, {9102, 1, 1, false},
        {9103, 1, 0, false}};
    Expect(PlanAppliedReports(one_content, item_globals, districts, no_effects,
                              two_of_three, 0, {},
                              AppliedReportOrder::kHoldForArrival).to_report.empty(),
           "a content item with one district still pending has not landed");
    const std::vector<UnlockObservation> all_three = {
        {9010, 1, 1, false}, {9101, 1, 1, false}, {9102, 1, 1, false},
        {9103, 1, 1, false}};
    Expect(PlanAppliedReports(one_content, item_globals, districts, no_effects,
                              all_three, 0, {},
                              AppliedReportOrder::kHoldForArrival).to_report.size() == 1,
           "a content item reports once every district it releases holds");

    // One-shot effects land as the saved applied-index passes their position
    // among the effect items, which is the same count PlanEffects keeps.
    const std::map<std::int64_t, ItemEffect> effects = {
        {6001, ItemEffect{"cash", 500, true}}, {6002, ItemEffect{"armor", 0, false}}};
    const std::vector<std::pair<std::int64_t, std::int64_t>> mixed = {
        {0, 6001}, {1, 5001}, {2, 6002}};
    const std::vector<UnlockObservation> unlock_held = {{9010, 1, 1, false}};
    const AppliedReportPlan none_applied = PlanAppliedReports(
        mixed, item_globals, no_districts, effects, unlock_held, 0, {},
        AppliedReportOrder::kHoldForArrival);
    Expect(none_applied.to_report.empty(),
           "an effect the applied-index has not reached holds the list");
    const AppliedReportPlan first_applied = PlanAppliedReports(
        mixed, item_globals, no_districts, effects, unlock_held, 1, {},
        AppliedReportOrder::kHoldForArrival);
    Expect(first_applied.to_report.size() == 2 &&
               first_applied.to_report[0] == 0 && first_applied.to_report[1] == 1,
           "an applied-index of one lands the first effect and the unlock past it");
    Expect(PlanAppliedReports(mixed, item_globals, no_districts, effects,
                              unlock_held, 2, {},
                              AppliedReportOrder::kHoldForArrival).to_report.size() == 3,
           "the second effect lands as the index reaches it");

    // An item in none of the three maps does nothing in game, so there is
    // nothing for it to wait on. The hunt goal's package fragment is the one
    // such item: the client counts it and the game never sees it.
    const std::vector<std::pair<std::int64_t, std::int64_t>> unmapped = {{0, 7777}};
    Expect(PlanAppliedReports(unmapped, item_globals, no_districts, no_effects,
                              {}, 0, {},
                              AppliedReportOrder::kHoldForArrival).to_report.size() == 1,
           "an item that maps to nothing lands the moment it arrives");

    // An empty item list reports nothing.
    Expect(PlanAppliedReports({}, item_globals, no_districts, no_effects,
                              all_held, 0, {},
                              AppliedReportOrder::kHoldForArrival).to_report.empty(),
           "an empty item list reports nothing");

    // A BASELINE pass marks every landed item wherever it sits, rather than
    // holding at the first that has not landed. It announces nothing, so order
    // cannot matter to it, and it runs once per boundary: an item it skipped for
    // being out of order would never be marked and would be announced on the next
    // load instead. The mid-delivery state is exactly this shape.
    const AppliedReportPlan baselined = PlanAppliedReports(
        three, item_globals, no_districts, no_effects, middle_pending, 0, {},
        AppliedReportOrder::kEverythingLanded);
    Expect(baselined.to_report.size() == 2 && baselined.to_report[0] == 0 &&
               baselined.to_report[1] == 2,
           "a baseline pass marks the landed items a reporting pass would hold");
    Expect(held_back.to_report.size() == 1,
           "and the reporting pass over the same state still holds at the first "
           "item that has not landed");

    // A BASELINE OVER EFFECTS, which is the case whose absence let a real defect
    // through: every baseline case above passes no effects at all. A baseline
    // marks an effect the index has passed WITHOUT emitting it, so the caller must
    // answer from an index taken before the frame's own effect application. Read
    // afterwards, an effect applied on the baselining frame is marked as already
    // told and loses its row for good, since only a game boundary clears that
    // record and the next boundary baselines it again.
    const std::vector<std::pair<std::int64_t, std::int64_t>> effect_first = {
        {0, 6001}, {1, 5001}};
    const std::map<std::int64_t, ItemEffect> one_effect = {
        {6001, ItemEffect{"cash", 500, true}}};
    const std::vector<UnlockObservation> unlock_at_target = {{9010, 1, 1, false}};
    // The claim is about the EFFECT at index 0 and nothing else. The unlock at
    // index 1 is at its target either way, so a baseline marks it in both runs;
    // that is correct and is not what this is pinning.
    const AppliedReportPlan before_grants = PlanAppliedReports(
        effect_first, item_globals, no_districts, one_effect, unlock_at_target, 0,
        {}, AppliedReportOrder::kEverythingLanded);
    Expect(std::find(before_grants.to_report.begin(), before_grants.to_report.end(),
                     0) == before_grants.to_report.end(),
           "a baseline answered from the pre-grant index leaves the effect "
           "unmarked, so its row survives");
    // The index AFTER the frame's own application: the effect reads as landed, a
    // baseline marks it told, and nothing ever sends it. Pinned so the caller
    // cannot go back to reading the index late.
    const AppliedReportPlan after_grants = PlanAppliedReports(
        effect_first, item_globals, no_districts, one_effect, unlock_at_target, 1,
        {}, AppliedReportOrder::kEverythingLanded);
    Expect(std::find(after_grants.to_report.begin(), after_grants.to_report.end(),
                     0) != after_grants.to_report.end(),
           "and from the post-grant index it would swallow it, which is why the "
           "caller snapshots the index before either grant path runs");
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

    // With no MP3 folder installed the game skips the MP3 slot for the player:
    // while a retune is pending it steps the press count itself once the
    // pending position lands there. That step is no player press, and
    // discounting it is what keeps the off position, the stop right after the
    // slot on the wheel, reachable from Wave.
    std::array<bool, kRadioStationCount> with_wave{};
    with_wave[2] = true;
    with_wave[8] = true;
    Expect(UserTrackSkippedPresses(8, 0, 2) == 1, "a count stepped past the slot is the game's");
    Expect(UserTrackSkippedPresses(8, 0, 1) == 0, "a count resting on the slot is the player's");
    Expect(UserTrackSkippedPresses(8, 0, 13) == 2, "the slot recurs once per lap of the wheel");
    auto off_from_wave = PlanRetunePresses(2, 0, 0, 8, with_wave);
    Expect(off_from_wave.logical_presses == 1 && off_from_wave.written_presses == 2 &&
               !off_from_wave.write_needed,
           "one press from Wave reaches off once the game's own step is discounted");
    auto off_with_mp3_folder = PlanRetunePresses(1, 0, 0, 8, with_wave);
    Expect(off_with_mp3_folder.logical_presses == 1 &&
               off_with_mp3_folder.written_presses == 2 && off_with_mp3_folder.write_needed,
           "and reaches off in one press when an MP3 folder makes the game step nothing");
    auto off_mid_scroll = PlanRetunePresses(8, 1, 6, 2, with_wave);
    Expect(off_mid_scroll.logical_presses == 2 && off_mid_scroll.written_presses == 8 &&
               !off_mid_scroll.write_needed,
           "a press stepping a pending scroll off Wave reaches off too");
    auto off_after_commit = PlanRetunePresses(2, 1, 6, 8, with_wave);
    Expect(off_after_commit.logical_presses == 1 && off_after_commit.written_presses == 2 &&
               !off_after_commit.write_needed,
           "a commit onto Wave plus a stepped press restarts and still reaches off");
    auto stepped_burst = PlanRetunePresses(8, 0, 0, 2, two);
    Expect(stepped_burst.logical_presses == 7 && stepped_burst.written_presses == 5 &&
               stepped_burst.write_needed,
           "an MP3-key burst lands on the same stop with the game's step discounted");
  }

  // Package cash suppression: the executable pays a hundred per package and a
  // hundred thousand as the count reaches the total, so with the class on both
  // go back in the frame they land. The plan reads only live counters and the
  // count the detection reported, so nothing a save restores can look like a
  // payment.
  {
    Expect(PackageCashClawBack(1, 1, 100, 5000) == kPackageCash,
           "one package pays a hundred, taken straight back");
    Expect(PackageCashClawBack(2, 3, 100, 5000) == 2 * kPackageCash,
           "two reported in one frame take back both hundreds");
    Expect(PackageCashClawBack(0, 100, 100, 500000) == 0,
           "no package reported, nothing paid, nothing taken");
    Expect(PackageCashClawBack(1, 100, 100, 500000) == kPackageCash + kAllPackagesCash,
           "the last package pays the bonus on top of its own hundred");
    Expect(PackageCashClawBack(1, 99, 100, 500000) == kPackageCash,
           "a package short of the total pays no bonus");
    Expect(PackageCashClawBack(2, 100, 100, 500000) == 2 * kPackageCash + kAllPackagesCash,
           "the bonus rides the frame the count reaches the total, however many land");
    Expect(PackageCashClawBack(1, 101, 100, 500000) == kPackageCash,
           "a count already past the total means the bonus was paid before, not now");
    Expect(PackageCashClawBack(1, 1, 0, 5000) == kPackageCash,
           "an unknown total pays no bonus");
    Expect(PackageCashClawBack(1, 100, 100, 40) == 40,
           "the claw-back never takes more money than there is");
    Expect(PackageCashClawBack(1, 5, 100, 0) == 0,
           "a wallet pinned at nothing cannot go negative");
    Expect(PackageCashClawBack(1, 5, 100, -50) == 0,
           "nor can one already below nothing");
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
        {0, 393.9, -60.2, 11.5, 15, 274, 34},
        {0, 30.0, -1330.9, 13.0, 2, 366, 0},
        {0, -900.0, 250.0, 17.0, 15, 375, 0},
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

  // The AP check marker: a slot whose check is still to be taken shows the
  // marker model instead of whatever the layout gives it, and goes back to the
  // layout once the check is taken. The flag is re-derived per frame by the
  // caller, so "taken" is simply the flag going false.
  {
    const std::vector<PickupTarget> targets = {
        // A weapon slot with ammo, so reverting has something to re-stamp.
        {1, 393.9, -60.2, 11.5, 15, 274, 34},
        // A heart, and the layout already matches the pool.
        {2, 30.0, -1330.9, 13.0, 2, 366, 0},
    };
    const std::vector<PickupPoolEntry> pool = {
        {393.9f, -60.2f, 11.5f, 15, 274, 40},
        {30.0f, -1330.9f, 13.0f, 2, 366, 41},
    };

    const auto pending = PlanPickupLayout(targets, pool, {true, true});
    Expect(pending.rewrites.size() == 2, "both pending slots take the marker");
    Expect(pending.unmatched_targets == 0,
           "a matched pending slot is not counted unmatched");
    // Unmatched counting is the one thing converting the range-for to an index
    // loop could have broken, so a pending target the pool never offers is
    // pinned too: it counts once and rewrites nothing.
    const auto orphan = PlanPickupLayout(targets, {}, {true, true});
    Expect(orphan.rewrites.empty() && orphan.unmatched_targets == 2,
           "a pending slot the pool never offers counts unmatched, rewrites nothing");
    for (const PickupRewrite& rewrite : pending.rewrites) {
      Expect(rewrite.model == kPickupCheckMarkerModel,
             "a pending check shows the marker model");
      Expect(rewrite.quantity == 0,
             "the marker carries no ammo, since it is not a weapon");
    }

    // Taken: the flags go false and the slot returns to the layout. The weapon
    // gets its ammo back because the rewrite fires on the model differing, and
    // the marker is what it differs from.
    const std::vector<PickupPoolEntry> marked = {
        {393.9f, -60.2f, 11.5f, 15, kPickupCheckMarkerModel, 40},
        {30.0f, -1330.9f, 13.0f, 2, kPickupCheckMarkerModel, 41},
    };
    const auto taken = PlanPickupLayout(targets, marked, {false, false});
    Expect(taken.rewrites.size() == 2, "both taken slots revert");
    Expect(taken.rewrites[0].model == 274 && taken.rewrites[0].quantity == 34,
           "reverting a weapon slot re-stamps its ammo");
    Expect(taken.rewrites[1].model == 366,
           "reverting a heart slot restores the heart");

    // Already showing the marker and still pending: nothing to do, which is
    // what keeps this off the rewrite path every frame for 110 slots.
    const auto steady = PlanPickupLayout(targets, marked, {true, true});
    Expect(steady.rewrites.empty(),
           "a slot already showing the marker is not rewritten again");

    // A short flag list leaves the rest not pending rather than reading past it.
    const auto partial = PlanPickupLayout(targets, pool, {true});
    Expect(partial.rewrites.size() == 1 &&
               partial.rewrites[0].pool_index == 40,
           "only the flagged slot takes the marker when the list is short");

    // And with no flags at all the planner is exactly the shuffle it was.
    const auto none = PlanPickupLayout(targets, pool);
    Expect(none.rewrites.empty(),
           "with no checks pending the layout already matches the pool");
  }

  // How far the matcher looks, which is the one number a foreign pickup can
  // reach a slot through. dump_pickups.py measures the closest same-type pickup
  // no table of ours owns and the world refuses a tolerance that reaches it; the
  // pair that made it tight is the body armour Rub Out leaves in the estate
  // courtyard and the Tec-9 the finale places 0.94 units from it, both street
  // type. These stand in for that pair at the same distance.
  {
    const std::vector<PickupTarget> targets = {
        {0, -336.0, -573.7, 11.6, 2, 368, 0},
    };
    // Only the foreign pickup, at the distance the decompile measures. It must
    // not be taken for the slot.
    const std::vector<PickupPoolEntry> foreign = {
        {-336.6208f, -572.994f, 11.6022f, 2, 281, 70},
    };
    const auto missed = PlanPickupLayout(targets, foreign, {true});
    Expect(missed.rewrites.empty() && missed.unmatched_targets == 1,
           "a same-type pickup 0.94 units away is not the slot");
    // The slot's own entry, off by the last bits of a float rather than by a
    // pickup's width, still matches.
    const std::vector<PickupPoolEntry> own = {
        {-336.0001f, -573.6999f, 11.6001f, 2, 368, 71},
    };
    const auto found = PlanPickupLayout(targets, own, {true});
    Expect(found.rewrites.size() == 1 && found.unmatched_targets == 0 &&
               found.rewrites[0].pool_index == 71,
           "the slot's own entry matches through float round-tripping");
    // Both in the pool at once, foreign entry FIRST, which is what the old
    // first-within-tolerance walk would have taken had the tolerance let it.
    const std::vector<PickupPoolEntry> both = {foreign[0], own[0]};
    const auto nearest = PlanPickupLayout(targets, both, {true});
    Expect(nearest.rewrites.size() == 1 &&
               nearest.rewrites[0].pool_index == 71,
           "the nearest entry wins, whatever order the pool is walked in");
  }

  // Stand pricing. A pending check wears one marker model wherever it is, so the
  // pool slot is the only thing that can tell Phil's stands from the rest, and
  // an override is what the shop class's promise about price rests on.
  {
    std::vector<PickupTarget> targets = {
        // An ambient in-shop stand: a check, and priced like any marker.
        {5, -113.2, -975.7, 10.4, 1, 366, 0},
        // Phil's minigun stand: a check, and priced at what the minigun costs.
        {6, -1105.9, 325.3, 11.1, 1, 290, 0},
    };
    targets[1].price_weapon_type = 33;
    const std::vector<PickupPoolEntry> pool = {
        {-113.2f, -975.7f, 10.4f, 1, 366, 80},
        {-1105.9f, 325.3f, 11.1f, 1, 290, 81},
    };
    const auto pending = PlanPickupLayout(targets, pool, {true, true});
    Expect(pending.price_overrides.size() == 1,
           "only the stand carrying a price type overrides its price");
    Expect(!pending.price_overrides.empty() &&
               pending.price_overrides[0].pool_index == 81 &&
               pending.price_overrides[0].weapon_type == 33,
           "the override names the matched pool slot and the stand's own type");
    // Taken, so the real model is back on the stand and the game's own price for
    // that model is the stand's price again.
    const auto taken = PlanPickupLayout(targets, pool, {false, false});
    Expect(taken.price_overrides.empty(),
           "a stand whose check is taken prices from its own model again");
    // A stand the pool never offered has no slot to name, so it overrides
    // nothing rather than naming a slot it did not match.
    const auto orphan = PlanPickupLayout(targets, {}, {true, true});
    Expect(orphan.price_overrides.empty(),
           "an unmatched stand overrides no pool slot");
  }

  // A tripwire, not a derivation: what makes 12 right is that CostOfWeapon
  // holds a thousand there, which only the game's own table can say. The ASI
  // reads it at load and logs a mismatch; this refuses a silent edit to either
  // half of the pair.
  Expect(kPickupCheckMarkerWeaponType == 12 &&
             kPickupCheckMarkerPriceInDollars == 1000,
         "the marker's price index and its documented price still agree; "
         "re-read CostOfWeapon before changing either");

  {
    // Taking a check from a vehicle. The gate compares the police bribe model
    // against the pickup's own, so the answer here IS the patch: give it the
    // pickup's model and the game's own comparison agrees.
    constexpr int kBribe = 375;
    constexpr int kSomethingElse = 274;
    Expect(VehicleCollectComparisonModel(kPickupCheckMarkerModel, kBribe, true)
               == kPickupCheckMarkerModel,
           "a marker in a vehicle answers with its own model, so the compare "
           "agrees and the vehicle branch is taken");
    // The half that keeps on-foot collection provably vanilla. Both paths run
    // the same on-foot test, so answering unconditionally would behave the same;
    // the point of the gate is that out of a car the answer is the game's own,
    // which is what makes the patch additive rather than merely equivalent.
    Expect(VehicleCollectComparisonModel(kPickupCheckMarkerModel, kBribe, false)
               == kBribe,
           "a marker on foot answers with the bribe model, so the compare fails "
           "and the ordinary on-foot path is kept");
    Expect(VehicleCollectComparisonModel(kSomethingElse, kBribe, true) == kBribe,
           "any other model answers with the bribe model in a vehicle too");
    Expect(VehicleCollectComparisonModel(kSomethingElse, kBribe, false) == kBribe,
           "and on foot");
    // A real bribe is what the gate was built for and must be untouched, in a
    // vehicle and out of one.
    Expect(VehicleCollectComparisonModel(kBribe, kBribe, true) == kBribe &&
               VehicleCollectComparisonModel(kBribe, kBribe, false) == kBribe,
           "a police bribe still answers with the bribe model either way");
  }

  // An in-shop slot wears the marker like any other. What makes that safe is
  // outside this header: the ASI prices the marker itself on the purchase path,
  // so the model no longer decides what the stand charges.
  {
    const std::vector<PickupTarget> targets = {
        // A health stand, in-shop, so it charges.
        {1, 100.0, 200.0, 10.0, kPickupTypeInShop, 366, 0},
        // An ordinary heart beside it.
        {2, 300.0, 400.0, 10.0, 2, 366, 0},
    };
    const std::vector<PickupPoolEntry> pool = {
        {100.0f, 200.0f, 10.0f, kPickupTypeInShop, 366, 60},
        {300.0f, 400.0f, 10.0f, 2, 366, 61},
    };
    const auto plan = PlanPickupLayout(targets, pool, {true, true});
    Expect(plan.rewrites.size() == 2, "both pending slots take the marker");
    bool shop_marked = false;
    for (const PickupRewrite& rewrite : plan.rewrites) {
      Expect(rewrite.model == kPickupCheckMarkerModel,
             "each pending slot shows the marker whatever its type");
      Expect(rewrite.quantity == 0, "and carries no ammo with it");
      if (rewrite.pool_index == 60) shop_marked = true;
    }
    Expect(shop_marked, "the shop stand is one of them");

    // A slot the caller does not flag keeps its own model, whatever its type.
    const auto one_only = PlanPickupLayout(targets, pool, {false, true});
    Expect(one_only.rewrites.size() == 1,
           "an unflagged slot stays on its own model");
    Expect(!one_only.rewrites.empty() && one_only.rewrites[0].pool_index == 61 &&
               one_only.rewrites[0].model == kPickupCheckMarkerModel,
           "and the flagged slot beside it takes the marker");

    // Taken, and the stand goes back to selling what the layout gives it.
    const std::vector<PickupPoolEntry> marked = {
        {100.0f, 200.0f, 10.0f, kPickupTypeInShop, kPickupCheckMarkerModel, 60},
        {300.0f, 400.0f, 10.0f, 2, kPickupCheckMarkerModel, 61},
    };
    const auto taken = PlanPickupLayout(targets, marked, {false, false});
    Expect(taken.rewrites.size() == 2, "both revert once their checks are taken");
    for (const PickupRewrite& rewrite : taken.rewrites) {
      Expect(rewrite.model == 366, "back to the model the layout gives it");
    }
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

  // Stamping the seed into a game: every game that comes up without a hash gets
  // one, which is what a new game started from the pause menu depends on, since
  // the bridge session it was welcomed in never handshakes again.
  {
    Expect(ShouldStampSeedHash(true, true, true),
           "a game whose script space holds no hash is stamped");
    Expect(!ShouldStampSeedHash(false, true, true),
           "a game already carrying a hash is never stamped over");
    Expect(!ShouldStampSeedHash(true, false, true),
           "with no welcome there is no seed to stamp, and the game stays "
           "unstamped rather than being claimed by nothing");
    Expect(!ShouldStampSeedHash(true, true, false),
           "the seed a client that has gone away named cannot claim the next "
           "game, which the client after it would refuse for good");
  }

  // Taking the completion baseline: not before a config has named the globals it
  // is a baseline of, since an empty one is permanent and the welcome that stamps
  // a game can land a frame ahead of the config that describes it.
  {
    Expect(ShouldCaptureBaseline(false, false),
           "a game with globals to watch takes its baseline");
    Expect(!ShouldCaptureBaseline(true, false),
           "a baseline is taken once per game");
    Expect(!ShouldCaptureBaseline(false, true),
           "an empty watch list is no baseline: taking one would skip every "
           "global the config has yet to name for the life of the game");
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
  // The two lock families union on a rampage icon: either alone holds it, and
  // the two run-them-down icons answer only to the rampages content key, since
  // they hand no weapon.
  {
    AbilityLocks no_ability{};
    ContentLocks no_content{};
    AbilityLocks weapon_locked{};
    weapon_locked[kAbilityWeaponEquip] = true;
    ContentLocks rampages_held{};
    rampages_held[ContentDistrictSlot(kContentRampages, 0)] = true;
    const int ocean = 0;

    Expect(IsVehicleRampagePickup(-679.66f, -419.712f) &&
               IsVehicleRampagePickup(468.656f, -1608.79f),
           "both run-them-down rampage icons are recognized");
    Expect(!IsVehicleRampagePickup(218.22f, -1613.76f),
           "a weapon rampage icon is not");
    Expect(ShouldHoldPickup(HeldPickupClass::kRampage, ocean, false, weapon_locked,
                            no_content),
           "the weapon lock alone holds a weapon rampage icon");
    Expect(ShouldHoldPickup(HeldPickupClass::kRampage, ocean, false, no_ability,
                            rampages_held),
           "the rampages key alone holds it too");
    Expect(!ShouldHoldPickup(HeldPickupClass::kRampage, ocean, true, weapon_locked,
                             no_content),
           "a run-them-down icon stays collectible under the weapon lock");
    Expect(ShouldHoldPickup(HeldPickupClass::kRampage, ocean, true, no_ability,
                            rampages_held),
           "but the rampages key holds it");
    Expect(!ShouldHoldPickup(HeldPickupClass::kRampage, ocean, false, no_ability,
                             no_content),
           "neither lock leaves every icon alone");
    // The weapon lock is not per district: it holds a weapon rampage icon
    // wherever it stands, so a district the rampages key released still answers
    // to it.
    Expect(ShouldHoldPickup(HeldPickupClass::kRampage, 5, false, weapon_locked,
                            no_content),
           "the weapon lock reaches every district");
  }

  // Each content key holds its own class and nothing else, and a class is held
  // only while its flag is set and its unlock is still zero.
  {
    ContentLocks packages_held{};
    packages_held[ContentDistrictSlot(kContentHiddenPackages, 0)] = true;
    AbilityLocks no_ability{};
    Expect(ShouldHoldPickup(HeldPickupClass::kPackage, 0, false, no_ability,
                            packages_held),
           "the packages key holds a package in the district it holds");
    Expect(!ShouldHoldPickup(HeldPickupClass::kPackage, 1, false, no_ability,
                            packages_held),
           "and not one in a district it has released, the whole point of the split");
    Expect(!ShouldHoldPickup(HeldPickupClass::kProperty, 0, false, no_ability,
                             packages_held),
           "and leaves the property icons alone");

    // A pickup the seed never described has no district. It is held while any
    // district of its class is, so a table missing an entry hides that pickup
    // rather than handing out a check no item has released.
    Expect(ShouldHoldPickup(HeldPickupClass::kPackage, kDistrictUnknown, false,
                            no_ability, packages_held),
           "an unplaced pickup is held while any district of its class is");

    // The block itself: released is what the globals say, and a class the seed
    // does not lock arrives with every district already stamped released, which
    // is what makes a single condition enough in the script.
    std::array<int, kContentCount * kDistrictCount> unlocks{};
    const std::size_t property_ocean =
        ContentDistrictSlot(kContentPropertyPurchases, 0);
    Expect(PlanContentLocks(unlocks)[property_ocean],
           "a district with no item is held");
    unlocks[property_ocean] = 1;
    Expect(!PlanContentLocks(unlocks)[property_ocean], "the item releases it");
    Expect(ContentHeldAnywhere(PlanContentLocks(unlocks), kContentPropertyPurchases),
           "the class is still held elsewhere");
    Expect(ContentDistrictsHeld(PlanContentLocks(unlocks), kContentPropertyPurchases)
               == kDistrictCount - 1,
           "and the count says how much of it is left");
    std::array<int, kContentCount * kDistrictCount> all_released{};
    all_released.fill(1);
    Expect(!AnyContentHeld(PlanContentLocks(all_released)),
           "an unlocked seed never holds, the toggle invariant");

    // Absent reads from the same block as released, and both let content
    // through. What they must not share is the page: a district with none of a
    // class is not a place the class became available.
    std::array<int, kContentCount * kDistrictCount> mixed{};
    const std::size_t store_ocean = ContentDistrictSlot(kContentRobbableStores, 0);
    mixed[store_ocean] = kDistrictAbsent;
    Expect(!PlanContentLocks(mixed)[store_ocean],
           "an absent pair is not held, so no gate ever waits on it");
    Expect(PlanContentAbsence(mixed)[store_ocean],
           "and it reads as absent, so the page leaves it out");
    Expect(!PlanContentAbsence(mixed)[ContentDistrictSlot(kContentRobbableStores, 1)],
           "a held district is not absent, which is why it is worth naming");
    Expect(!PlanContentAbsence(all_released)[store_ocean],
           "released is not absent: an older seed stamped both alike, and reading "
           "that as absent would hide districts that do hold content");
    Expect(ContentDistrictsPresent(PlanContentAbsence(mixed),
                                   kContentRobbableStores) == kDistrictCount - 1,
           "and the denominator counts what exists rather than all eleven");

    // Placing a pool entry: the position finds it, and the class has to agree,
    // since a property icon and a package can stand close together.
    const std::vector<PickupDistrict> table = {
        {100.0f, 200.0f, kContentHiddenPackages, 3},
        {100.5f, 200.0f, kContentPropertyPurchases, 7},
    };
    Expect(DistrictForPickup(table, HeldPickupClass::kPackage, 100.0f, 200.0f) == 3,
           "a package finds its own district");
    Expect(DistrictForPickup(table, HeldPickupClass::kProperty, 100.5f, 200.0f) == 7,
           "and a property icon beside it finds its own");
    Expect(DistrictForPickup(table, HeldPickupClass::kRampage, 100.0f, 200.0f)
               == kDistrictUnknown,
           "a class with no entry there is unplaced rather than mismatched");
    Expect(DistrictForPickup(table, HeldPickupClass::kPackage, 900.0f, 900.0f)
               == kDistrictUnknown,
           "and so is a position the table does not carry");
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


  // The toast stack. Nothing may be dropped and nothing may overflow the band,
  // and what makes both true at once is that a row's clock starts when it becomes
  // VISIBLE rather than when it arrived: the band stays full, every row gets its
  // whole lifetime, and the queue drains at the band's own rate.
  {
    const auto row = [](std::size_t lines) {
      ToastRow built;
      for (std::size_t line = 0; line < lines; ++line) {
        built.lines.push_back({{"text", ToastRole::kConnective}});
      }
      return built;
    };

    // The band's capacity comes out of the geometry, so the measured default is
    // what the drain rate is reasoned about. The anchor sits near the top of an
    // empty corner and the floor, plus a line's own advance, clears the radar.
    ToastGeometry geometry;
    Expect(ToastLineCapacity(geometry) == 18,
           "the measured band holds eighteen lines, and a message is one line, so "
           "eighteen of them");
    // The band must never be the thing that paces the drip. One row per grant is
    // the whole design, so the band has to turn over at least as fast as grants
    // arrive. As a product rather than a quotient: exact, and with no divide by a
    // capacity that other cases here deliberately drive to zero.
    // A geometry change that cut the capacity far enough would put the block back
    // into a burst that fills the band and then stalls for the rest of a lifetime,
    // which is the bug this whole channel was rewritten to remove.
    Expect(ToastLineCapacity(geometry) * kGrantIntervalMs > geometry.lifetime_ms,
           "and turns over faster than grants arrive, so the band never paces the "
           "rows instead of the pacer");
    // THE FOOT OF A FULL STACK CLEARS THE RADAR, which was a comment and nothing
    // more until shrinking the font broke it: smaller text fits more lines, so the
    // foot moves DOWN as the font goes down.
    //
    // Asserted on the FLOOR and not on where the last line happens to start, so it
    // holds for every top rather than for the anchor alone. The drawing clips on
    // `y > floor_y`, so a line may start exactly at the floor, and a tutorial box
    // pushes the top to an arbitrary real number, so some box height lands the band
    // exactly there. A version of this pinned the anchor case only, which is the
    // same one-point guarantee the whole change was made to replace.
    Expect(geometry.floor_y + ToastLineAdvance(geometry) <= kRadarTopY,
           "and no line it admits can reach the radar, from any top");
    // A hand-edited file may tune the leading but not make the rows overlap.
    const ToastGeometry crushed = ParseToastGeometry(
        {"[toasts]", "line_height = 6", "scale_y = 1.0"});
    Expect(crushed.line_height >= ToastLineAdvance(crushed),
           "and a file asking for less leading than the glyphs need is floored at "
           "them");
    // The leading clears the font's own advance, which the scale does NOT carry
    // with it: 16 * scale_y + 2, where the 2 is constant, so a proportional step
    // down overlaps the rows.
    Expect(geometry.line_height > 16.0f * geometry.scale_y + 2.0f,
           "and a line is taller than the glyphs it holds");
    ToastGeometry narrow;
    narrow.floor_y = narrow.anchor_y;
    Expect(ToastLineCapacity(narrow) == 1,
           "a band with no height still holds one line, so a notice is never lost");
    // Not reachable through the file, which orders the two, but a hand-built one
    // must still answer a count rather than a negative or an enormous cast.
    ToastGeometry inverted;
    inverted.floor_y = inverted.anchor_y - 100.0f;
    Expect(ToastLineCapacity(inverted) == 0,
           "an inverted band holds nothing, which is what it can draw");
    // The band's top MOVES: a tutorial box owns the corner while it is up, and the
    // stack drops below it for as long as that lasts, so the capacity has to be
    // asked about the top it is really drawing from.
    Expect(ToastLineCapacityFrom(geometry, geometry.anchor_y + 100.0f) <
               ToastLineCapacity(geometry),
           "a top pushed down leaves a shorter band");
    // NOTHING, not one line: the drawing's own clip refuses the first line in that
    // state, and a capacity of one would have the advance start a row's lifetime on
    // a line that is never drawn.
    Expect(ToastLineCapacityFrom(geometry, geometry.floor_y + 50.0f) == 0,
           "a top pushed past the floor holds nothing at all");
    // And where the box ends higher than the stack would have started, nothing
    // moves.
    Expect(ToastTopBelowBox(geometry, geometry.anchor_y - 20.0f, 6.0f) ==
               geometry.anchor_y,
           "a box ending above the anchor does not lift the stack");
    Expect(ToastTopBelowBox(geometry, geometry.anchor_y + 40.0f, 6.0f) ==
               geometry.anchor_y + 46.0f,
           "and one ending below it pushes the stack under it, plus the gap");

    // A row's lifetime runs from the frame it was admitted on, not from the frame
    // it arrived on. This is the whole mechanism, so it is asserted directly: a row
    // that waited a full lifetime in the queue still gets its own on screen.
    {
      ToastStackState state;
      state.waiting.push_back(QueuedToast(row(1)));
      state.waiting.push_back(QueuedToast(row(1)));
      AdvanceToastStack(state, 1000, 1, kToastLifetimeMs);
      Expect(state.visible.size() == 1 && state.waiting.size() == 1,
             "a one-line band shows one row and holds the rest");
      Expect(state.visible[0].shown_at_ms == 1000,
             "an admitted row's clock starts when it is admitted");
      // One millisecond short of the lifetime: still on screen, and the row behind
      // it still waiting.
      AdvanceToastStack(state, 1000 + kToastLifetimeMs - 1, 1, kToastLifetimeMs);
      Expect(state.visible.size() == 1 && state.waiting.size() == 1,
             "a row holds its slot for its whole lifetime");
      AdvanceToastStack(state, 1000 + kToastLifetimeMs, 1, kToastLifetimeMs);
      Expect(state.visible.size() == 1 && state.waiting.empty(),
             "the slot frees and the next row takes it in the same frame");
      Expect(state.visible[0].shown_at_ms == 1000 + kToastLifetimeMs,
             "the row that waited gets its own full lifetime, not what is left");
    }

    // Nothing is dropped, however big the burst. Two hundred rows through a
    // nine-line band is the release case, and the count out must equal the count in.
    {
      ToastStackState state;
      for (int index = 0; index < 200; ++index) state.waiting.push_back(QueuedToast(row(2)));
      std::size_t shown = 0;
      unsigned int now = 0;
      for (int frame = 0; frame < 500; ++frame) {
        // Counted off the QUEUE rather than off the visible list: a frame expires
        // and admits at once, so the visible count can be unchanged across a frame
        // that showed four new rows.
        const std::size_t waiting_before = state.waiting.size();
        AdvanceToastStack(state, now, 9, kToastLifetimeMs);
        shown += waiting_before - state.waiting.size();
        now += kToastLifetimeMs;
      }
      Expect(state.waiting.empty(), "a two hundred row release drains completely");
      Expect(shown == 200, "every row of the release was shown, none dropped");
    }

    // A row is admitted whole. A two-line row waits for two free lines rather than
    // showing its sentence without its location, and admission stops at the first
    // row that does not fit rather than reaching past it for a shorter one, since
    // arrival order is the only order these rows have.
    {
      ToastStackState state;
      state.waiting.push_back(QueuedToast(row(1)));
      state.waiting.push_back(QueuedToast(row(2)));
      state.waiting.push_back(QueuedToast(row(1)));
      AdvanceToastStack(state, 0, 2, kToastLifetimeMs);
      Expect(state.visible.size() == 1 && state.waiting.size() == 2,
             "a two-line row waits for two free lines rather than showing half "
             "of itself behind a row already up");
      AdvanceToastStack(state, 0, 4, kToastLifetimeMs);
      Expect(state.visible.size() == 3, "a band of four fits all three rows");
    }

    // The band is never overflowed. Whatever arrives, the lines on screen stay
    // inside the capacity, because a row over the screen is worse than a row late.
    {
      ToastStackState state;
      for (int index = 0; index < 50; ++index) state.waiting.push_back(QueuedToast(row(2)));
      for (int frame = 0; frame < 20; ++frame) {
        AdvanceToastStack(state, static_cast<unsigned int>(frame) * 100, 9,
                          kToastLifetimeMs);
        std::size_t lines = 0;
        for (const LiveToast& live : state.visible) lines += live.row.line_count();
        Expect(lines <= 9, "the band never holds more lines than it has");
      }
    }

    // A notice arriving under rows already up takes its lines off the band whether
    // they were free or not. The OLDEST rows go, from the front, because they are
    // the ones that have been read: a row that has held the screen is not lost the
    // way an unshown one is, and leaving them would push the top of the stack past
    // the floor where the drawing clips it away unseen for the rest of its life.
    {
      ToastStackState state;
      for (int index = 0; index < 3; ++index) {
        state.waiting.push_back(
            QueuedToast(PlainToastRow(std::to_string(index), ToastRole::kConnective)));
      }
      AdvanceToastStack(state, 0, 3, kToastLifetimeMs);
      Expect(state.visible.size() == 3, "three one-line rows fill a band of three");
      state.notices[ToastNoticeSlot(ToastNotice::kBridgeDown)] =
          PlainToastRow("disconnected", ToastRole::kTrap);
      AdvanceToastStack(state, 1, 3, kToastLifetimeMs);
      Expect(state.visible.size() == 2,
             "a notice arriving takes its line from the rows already up");
      Expect(ToastLineText(state.visible[0].row.lines[0]) == "1",
             "and it takes the oldest, which is the one that has been read");
    }

    // A notice holds its place forever, and takes its lines off the band. Where the
    // band is large enough the rest still rotates; where it is not, the notices own
    // it, because a row admitted onto a band with no room for it would start its
    // lifetime and be clipped away unseen.
    {
      ToastStackState state;
      state.notices[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)] =
          PlainToastRow("refused", ToastRole::kTrap);
      Expect(ToastNoticeLines(state) == 1, "an active notice holds one line");
      state.waiting.push_back(QueuedToast(row(1)));
      AdvanceToastStack(state, 0, 2, kToastLifetimeMs);
      Expect(state.visible.size() == 1,
             "a notice leaves the rest of the band to the rotating rows");
      AdvanceToastStack(state, kToastLifetimeMs * 10, 2, kToastLifetimeMs);
      Expect(!state.notices[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)].empty(),
             "a notice never expires, however long it has been up");

      ToastStackState crowded;
      crowded.notices[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)] =
          PlainToastRow("refused", ToastRole::kTrap);
      crowded.notices[ToastNoticeSlot(ToastNotice::kBridgeDown)] =
          PlainToastRow("disconnected", ToastRole::kTrap);
      crowded.waiting.push_back(QueuedToast(row(1)));
      AdvanceToastStack(crowded, 0, 3, kToastLifetimeMs);
      Expect(crowded.visible.size() == 1,
             "two notices leave the rest of a band that has a rest");
      // And a band with no rest gives the notices everything, evicting the row
      // rather than leaving it where the drawing would clip it away unseen.
      AdvanceToastStack(crowded, 0, 2, kToastLifetimeMs);
      Expect(crowded.visible.empty(),
             "a band the notices fill takes back the line a row was holding");
    }

    // The draw order: the notices first, at the anchor, then the rotating rows
    // newest first running downward. So the newest row is always in the same place,
    // the older ones move down under it, and the notices never move at all.
    {
      ToastStackState state;
      state.notices[ToastNoticeSlot(ToastNotice::kBridgeDown)] =
          PlainToastRow("notice", ToastRole::kTrap);
      state.waiting.push_back(QueuedToast(PlainToastRow("older", ToastRole::kConnective)));
      state.waiting.push_back(QueuedToast(PlainToastRow("newer", ToastRole::kConnective)));
      AdvanceToastStack(state, 0, 9, kToastLifetimeMs);
      const std::vector<const ToastRow*> order = ToastDrawOrder(state);
      Expect(order.size() == 3, "every live row is drawn");
      Expect(order[0]->lines[0][0].text == "notice",
             "the notice draws at the anchor, the top of the stack");
      Expect(order[1]->lines[0][0].text == "newer",
             "the newest rotating row draws under it");
      Expect(order[2]->lines[0][0].text == "older",
             "and the older row under that, so the stack runs down into the past");
    }

    // Building a row from the wire. The newline marker is a layout break and not a
    // segment, empty lines are never spent on nothing, and both bounds hold, so a
    // malformed frame costs a truncated row rather than the band.
    {
      const ToastRow built = BuildToastRow({
          {"You", "own_slot"},
          {" sent ", "connective"},
          {"Minigun", "progression"},
          {"", "newline"},
          {"(", "connective"},
          {"Hidden Package 42", "location"},
          {")", "connective"},
      });
      Expect(built.lines.size() == 2, "the newline marker breaks the row in two");
      Expect(built.lines[0].size() == 3 && built.lines[1].size() == 3,
             "the segments land on the right side of the break");
      Expect(built.lines[0][0].role == ToastRole::kOwnSlot,
             "our own slot keeps the magenta role behind the word You");
      Expect(built.lines[1][1].role == ToastRole::kLocation,
             "the location keeps its own role");

      Expect(BuildToastRow({{"", "newline"}, {"", "newline"}}).empty(),
             "a row of nothing but breaks is not a row");
      Expect(BuildToastRow({{"text", "connective"}, {"", "newline"}}).lines.size() == 1,
             "a trailing break does not spend a line on nothing");
      Expect(ToastRoleFromName("nonsense") == ToastRole::kConnective,
             "an unknown colour name draws readably rather than not at all");

      std::vector<std::pair<std::string, std::string>> many;
      for (std::size_t index = 0; index < kToastMaxSegments + 10; ++index) {
        many.push_back({"x", "connective"});
      }
      const ToastRow bounded = BuildToastRow(many);
      Expect(bounded.lines.size() == 1 &&
                 bounded.lines[0].size() == kToastMaxSegments,
             "a row past the segment bound is truncated, not unbounded");

      std::vector<std::pair<std::string, std::string>> deep;
      for (std::size_t index = 0; index < kToastMaxLines + 5; ++index) {
        deep.push_back({"x", "connective"});
        deep.push_back({"", "newline"});
      }
      Expect(BuildToastRow(deep).lines.size() <= kToastMaxLines,
             "a row past the line bound cannot take the whole band");
    }

    // A line's text is the concatenation the width is measured from, which is what
    // keeps the layout off a per-segment sum.
    {
      const std::vector<ToastSegment> line = {
          {"You", ToastRole::kOwnSlot},
          {" found your ", ToastRole::kConnective},
          {"Body Armour", ToastRole::kProgression},
      };
      Expect(ToastLineText(line) == "You found your Body Armour",
             "a line measures as the string it draws");
    }
  }

  // Cutting a line to the band. This is what stops CFont folding an over-wide
  // line at its wrap edge and landing the tail glyph-on-glyph over the row below,
  // so every case that decides whether a line fits is asserted here.
  {
    // A character is one unit wide, which makes a width a character count and the
    // assertions readable.
    const auto measure = +[](const std::string& text) {
      return static_cast<float>(text.size());
    };
    const auto text_of = [](const std::vector<ToastSegment>& line) {
      return ToastLineText(line);
    };

    const std::vector<ToastSegment> line = {
        {"You", ToastRole::kOwnSlot},
        {" found your ", ToastRole::kConnective},
        {"Body Armour", ToastRole::kProgression},
    };
    Expect(text_of(FitSegmentLine(line, 100.0f, measure)) ==
               "You found your Body Armour",
           "a line inside the band is left alone");

    // Cut, never folded, and the cut is marked. 20 units of a 26 character line.
    const std::vector<ToastSegment> cut = FitSegmentLine(line, 20.0f, measure);
    Expect(text_of(cut).size() <= 20,
           "a cut line fits the band it was cut to");
    Expect(text_of(cut).rfind(kToastEllipsis) ==
               text_of(cut).size() - std::string(kToastEllipsis).size(),
           "a cut line says it was cut");
    Expect(text_of(cut).compare(0, 3, "You") == 0,
           "the cut takes the tail, so the front of the line still reads");

    // The ellipsis lands in whatever segment survives, so it draws in that
    // segment's own colour rather than an invented one. At this width the cut
    // lands inside the item name, so that is the colour it must take.
    Expect(cut.back().role == ToastRole::kProgression,
           "the ellipsis keeps the colour of the segment it lands in");

    // A band narrower than the ellipsis itself still terminates, and gives back
    // something rather than looping.
    const std::vector<ToastSegment> crushed = FitSegmentLine(line, 1.0f, measure);
    Expect(crushed.empty() || text_of(crushed).size() <= 4,
           "a band narrower than the ellipsis still terminates");

    // Whole rows, and only once. The flag is what keeps the in-game stack off a
    // per-character walk on every frame a long row is up.
    {
      ToastStackState state;
      ToastRow row;
      row.lines.push_back(line);
      row.lines.push_back({{"(", ToastRole::kConnective},
                           {"A Very Long Location Name Indeed", ToastRole::kLocation},
                           {")", ToastRole::kConnective}});
      state.visible.push_back({row, 0});
      state.notices[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)] =
          PlainToastRow("Archipelago refused this game: the save belongs to "
                        "another multiworld",
                        ToastRole::kTrap);
      FitToastStack(state, 20.0f, 20.0f, 9, measure);
      Expect(state.visible[0].fitted, "a fitted row records that it was fitted");
      Expect(state.notices_fitted[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)],
             "so does a fitted notice");
      for (const std::vector<ToastSegment>& fitted : state.visible[0].row.lines) {
        Expect(ToastLineText(fitted).size() <= 20,
               "every line of a row is cut, not just the first");
      }
      const ToastRow& refusal =
          state.notices[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)];
      for (const std::vector<ToastSegment>& fitted : refusal.lines) {
        Expect(ToastLineText(fitted).size() <= 20,
               "the handshake refusal is brought inside the band like anything "
               "else, since it never expires and would otherwise fold over the "
               "radar for the session");
      }
      // BROKEN, not cut. A refusal names the reason nothing in the seed will work,
      // and "Archipelago refused this game: " alone is most of a line, so cutting
      // it would leave the one row that must be readable saying nothing.
      Expect(refusal.lines.size() > 1,
             "a notice is broken across lines rather than cut to its first");
      Expect(refusal.lines.size() <= kToastMaxLines,
             "and still cannot take the whole band, however long its text");
      Expect(refusal.lines[0][0].role == ToastRole::kTrap,
             "every line of a broken notice keeps the notice's own colour");

      // Fitting again changes nothing, which is what makes it safe to call every
      // frame.
      const std::string once = ToastLineText(state.visible[0].row.lines[0]);
      FitToastStack(state, 20.0f, 20.0f, 9, measure);
      Expect(ToastLineText(state.visible[0].row.lines[0]) == once,
             "a row already fitted is not cut a second time");
    }
  }

  // Breaking a notice has to use BOTH widths too. Breaking the whole text against
  // the first line's width fills every piece to it, and the pieces bound for the
  // indented lines then have to be cut back, which puts an ellipsis in the middle
  // of the one row that must be readable. Driven with the widths UNEQUAL, since
  // equal widths are the one setting where that cannot show.
  {
    const auto measure = +[](const std::string& text) {
      return static_cast<float>(text.size());
    };
    ToastStackState state;
    state.notices[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)] = PlainToastRow(
        "Archipelago refused this game: this save belongs to a different "
        "multiworld, so start a new game for this seed",
        ToastRole::kTrap);
    FitToastStack(state, 40.0f, 30.0f, 9, measure);
    const ToastRow& refusal =
        state.notices[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)];
    Expect(refusal.lines.size() > 1, "a long notice is broken across lines");
    for (std::size_t index = 0; index < refusal.lines.size(); ++index) {
      const std::string text = ToastLineText(refusal.lines[index]);
      Expect(text.size() <= (index == 0 ? 40u : 30u),
             "every broken line fits the width it draws in");
      Expect(text.find(kToastEllipsis) == std::string::npos,
             "and none of them is cut, which is the whole point of breaking a "
             "notice rather than cutting it");
    }
    // The words survive in order. What is drawn, joined back up, is what was set.
    std::string rejoined;
    for (const std::vector<ToastSegment>& line : refusal.lines) {
      if (!rejoined.empty()) rejoined += " ";
      rejoined += ToastLineText(line);
    }
    Expect(rejoined.find("start a new game for this seed") != std::string::npos,
           "the reason survives to the end of the notice");
  }

  // A row's first line starts at the anchor and every line after it is set in, so
  // they do NOT have the same width. Cutting a continuation line to the first
  // line's width lands it a whole indent past the wrap edge, where CFont folds it
  // onto the row below, which is the one thing this whole cut exists to stop.
  {
    const auto measure = +[](const std::string& text) {
      return static_cast<float>(text.size());
    };
    ToastStackState state;
    ToastRow row;
    row.lines.push_back({{"0123456789012345678901234567890123456789",
                          ToastRole::kConnective}});
    row.lines.push_back({{"0123456789012345678901234567890123456789",
                          ToastRole::kLocation}});
    state.visible.push_back({row, 0});
    FitToastStack(state, 30.0f, 20.0f, 9, measure);
    const ToastRow& fitted = state.visible[0].row;
    Expect(ToastLineText(fitted.lines[0]).size() <= 30,
           "the first line is cut to the width it draws in");
    Expect(ToastLineText(fitted.lines[1]).size() <= 20,
           "and a continuation line to its own narrower width, not the first's");
  }

  // The settings file a module reads is derived from its own name, so the two
  // cannot drift if the build renames its output.
  {
    Expect(SettingsPathForModule("C:\\Games\\GtaVcAp.VC.asi") ==
               "C:\\Games\\GtaVcAp.VC.ini",
           "the module's extension is replaced, not its dotted name");
    Expect(SettingsPathForModule("C:\\Games\\plugin") ==
               "C:\\Games\\plugin.ini",
           "a module with no extension gets one rather than nothing");
    Expect(SettingsPathForModule("C:\\Games.v2\\plugin") ==
               "C:\\Games.v2\\plugin.ini",
           "a dot in a directory name is not the module's extension");
    Expect(SettingsPathForModule("").empty(),
           "an unnamed module reads no file at all");
  }

  // The optional file that tunes the stack. Absent is the normal case, so every
  // way a hand edit can go wrong has to leave a geometry that still draws.
  {
    const ToastGeometry defaults;
    Expect(ParseToastGeometry({}).anchor_y == defaults.anchor_y,
           "an empty file is the compiled-in defaults");
    Expect(ParseToastGeometry({"anchor_y = 200"}).anchor_y == defaults.anchor_y,
           "a setting outside the section is ignored");

    ToastGeometry read = ParseToastGeometry({
        "; a comment",
        "[other]",
        "anchor_y = 999",
        "[toasts]",
        "  anchor_y  =  200  ",
        "width = 300 # trailing comment",
        "line_height = 20",
        "lifetime_ms = 6000",
        "nonsense = 4",
        "scale_x = not a number",
    });
    Expect(read.anchor_y == 200.0f, "whitespace either side of a value is dropped");
    Expect(read.width == 300.0f, "a trailing comment is not part of the value");
    Expect(read.line_height == 20.0f && read.lifetime_ms == 6000,
           "every key the file names is applied");
    Expect(read.scale_x == defaults.scale_x,
           "a value that is not a whole number leaves its setting alone");

    Expect(ParseToastGeometry({"[toasts]", "width = 3 4"}).width == defaults.width,
           "a value with a trailing token is not taken as its prefix");
    Expect(ParseToastGeometry({"[toasts]", "lifetime_ms = -5"}).lifetime_ms ==
               defaults.lifetime_ms,
           "a negative duration leaves its setting alone rather than wrapping");

    // NaN is the one value every bound below would pass unchanged, because every
    // comparison against it is false. A NaN band then makes the line count a cast
    // from a NaN, which admits the whole queue onto a stack whose floor test can
    // never be true.
    for (const char* spelling : {"nan", "-nan", "NAN", "inf", "-inf"}) {
      const ToastGeometry hostile =
          ParseToastGeometry({"[toasts]", std::string("anchor_y = ") + spelling});
      Expect(hostile.anchor_y == defaults.anchor_y,
             "a value that is not a finite number leaves its setting alone");
      Expect(ToastLineCapacity(hostile) >= 1 &&
                 ToastLineCapacity(hostile) <= 128,
             "the band a hostile file produces is still a band");
    }

    // The bounds. A file may move the stack but never lose it off the screen.
    const ToastGeometry far_out = ParseToastGeometry({
        "[toasts]", "anchor_x = 5000", "anchor_y = 5000", "width = 5000",
        "scale_x = 50", "scale_y = 0", "line_height = 0",
        "lifetime_ms = 100000000",
    });
    Expect(far_out.anchor_x >= 0.0f && far_out.anchor_x < kVirtualScreenWidth,
           "the anchor stays on the screen");
    Expect(far_out.anchor_x + far_out.width <= kVirtualScreenWidth,
           "and the stack ends on the screen");
    Expect(far_out.anchor_y < kVirtualScreenHeight, "so does the anchor's row");
    Expect(far_out.scale_x <= kToastMaxScale && far_out.scale_y >= kToastMinScale,
           "the text stays a size that can be read");
    Expect(far_out.line_height >= kToastMinLineHeight,
           "a line keeps a height, so the band is a count and not a division by "
           "nothing");
    Expect(far_out.lifetime_ms <= kToastMaxLifetimeMs,
           "a row cannot be made to hold the screen forever");

    // An inverted band is ordered rather than left negative, so the floor is never
    // above the anchor.
    const ToastGeometry swapped =
        ParseToastGeometry({"[toasts]", "anchor_y = 400", "floor_y = 100"});
    Expect(swapped.floor_y >= swapped.anchor_y,
           "the floor is never above the top it is measured from");
    Expect(ToastLineCapacity(swapped) >= 1, "and the band still holds a line");
  }

  // A band too small for what is in it. Neither of these is reachable with the
  // measured geometry, and both are reachable through the file, so both are the
  // model's problem rather than the bounds'.
  {
    const auto row = [](std::size_t lines) {
      ToastRow built;
      for (std::size_t line = 0; line < lines; ++line) {
        built.lines.push_back({{"text", ToastRole::kConnective}});
      }
      return built;
    };

    // Two notices in a one-line band: the notices own it, and nothing rotating is
    // admitted, because a row admitted here would start its lifetime and then be
    // clipped at the floor without ever being drawn.
    ToastStackState crowded;
    crowded.notices[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)] =
        PlainToastRow("refused", ToastRole::kTrap);
    crowded.notices[ToastNoticeSlot(ToastNotice::kBridgeDown)] =
        PlainToastRow("disconnected", ToastRole::kTrap);
    crowded.waiting.push_back(QueuedToast(row(1)));
    AdvanceToastStack(crowded, 0, 1, kToastLifetimeMs);
    Expect(crowded.visible.empty(),
           "a band the notices fill admits nothing, rather than admitting a row "
           "the drawing would clip away unseen");
    Expect(crowded.waiting.size() == 1, "and the row it did not admit is kept");

    // A row taller than the whole rotating band. It shows anyway when nothing else
    // is up, because a queue that never drains says nothing at all, and it shows
    // its LEADING lines, which are the ones the downward drawing would have kept
    // anyway.
    ToastStackState stalled;
    ToastRow tall;
    tall.lines.push_back({{"sentence", ToastRole::kConnective}});
    tall.lines.push_back({{"(location)", ToastRole::kLocation}});
    stalled.waiting.push_back(QueuedToast(tall));
    stalled.waiting.push_back(QueuedToast(row(1)));
    AdvanceToastStack(stalled, 0, 1, kToastLifetimeMs);
    Expect(stalled.visible.size() == 1,
           "a row too tall for the band is still shown when nothing else is up");
    Expect(stalled.visible[0].row.lines.size() == 1 &&
               ToastLineText(stalled.visible[0].row.lines[0]) == "sentence",
           "and it is the sentence that survives, never an orphan location");
    AdvanceToastStack(stalled, kToastLifetimeMs, 1, kToastLifetimeMs);
    Expect(stalled.waiting.empty(),
           "so the queue behind it drains instead of stalling forever");
  }

  // The pause menu's status page. Sections are found by heading rather than by
  // index, so adding a block never silently moves what an assertion is aiming at.
  {
    // Every heading these two helpers are asked for, and every heading the pages
    // they are handed carry. A heading in the first set and not the second is one
    // no page here ever shows, which is a typo in the test or an assertion aimed
    // at a state this block never builds; either way it tests nothing. The two
    // sets are compared once at the end of the block, and that is what covers
    // HasSection, whose absence assertions read the same whether the heading is
    // spelled right or not.
    std::set<std::string> asked_headings;
    std::set<std::string> page_headings;
    auto Note = [&asked_headings, &page_headings](
        const std::vector<StatusSection>& sections, const std::string& heading) {
      asked_headings.insert(heading);
      for (const StatusSection& section : sections) {
        if (!section.heading.empty()) page_headings.insert(section.heading);
      }
    };

    // Whether the page carries a block at all. ComposeStatusPanel drops a
    // section with no rows, so a block with nothing to say is absent from the
    // page and absence is a real thing to assert.
    auto HasSection = [&Note](const std::vector<StatusSection>& sections,
                              const std::string& heading) {
      Note(sections, heading);
      for (const StatusSection& section : sections) {
        if (section.heading == heading) return true;
      }
      return false;
    };

    // A heading that matches nothing is a named failure rather than an empty
    // section, because an assertion reading an empty section passes on any
    // rows.empty() or size test it makes.
    auto Section = [&Note](const std::vector<StatusSection>& sections,
                           const std::string& heading) {
      Note(sections, heading);
      for (const StatusSection& section : sections) {
        if (section.heading == heading) return section;
      }
      const std::string missing = "the page has a section headed " + heading;
      Expect(false, missing.c_str());
      // Three rows, one deeper than the deepest a caller indexes. Three callers
      // read rows[1] or rows[2] in an Expect of their own, separate from the
      // size guard beside it, so a shorter section is read out of range before
      // the failure count is printed. Three is not a count any assertion asks
      // for by equality either, and every inequality it does satisfy is ANDed
      // with a value clause the filler fails.
      StatusSection absent;
      absent.heading = heading;
      for (int filler = 0; filler < 3; ++filler) {
        absent.rows.push_back({"", "no such section", StatusTone::kPlain});
      }
      return absent;
    };

    StatusPanelState state;
    std::vector<StatusSection> sections = ComposeStatusPanel(state);
    Expect(!sections.empty() && sections[0].heading.empty() &&
               sections[0].rows.size() == 2 &&
               sections[0].rows[0].value == "not connected" &&
               sections[0].rows[1].value == "no game started",
           "with no client and no game the summary says exactly that");
    // The lock blocks are there for every seed, so a missing block never has to
    // be told apart from a vanilla seed. Before a stamped game they say they do
    // not know, because the globals they would read mean nothing yet.
    Expect(Section(sections, "ABILITIES").rows.size() == 1 &&
               Section(sections, "ABILITIES").rows[0].value == "No game started." &&
               Section(sections, "CONTENT").rows[0].value == "No game started.",
           "without a stamped game the lock blocks claim nothing about the seed");
    StatusPanelState read_state;
    read_state.locks_known = true;
    Expect(Section(ComposeStatusPanel(read_state), "ABILITIES").rows[0].value ==
               "This seed locks no ability." &&
           Section(ComposeStatusPanel(read_state), "CONTENT").rows[0].value ==
               "This seed holds no content.",
           "and once the globals are read they say the seed locks nothing");
    // The client's own blocks stay out until a client has said something, which
    // means off the page rather than on it and empty.
    Expect(!HasSection(sections, "GOAL") &&
               !HasSection(sections, "MISSION STRANDS"),
           "the goal and strand blocks wait for the client");

    state.client_connected = true;
    state.seed_hash = "8F3C1A2B";
    state.counts_known = true;
    state.checks_done = 61;
    state.checks_total = 214;
    state.items_received = 43;
    state.percentage = 34;
    sections = ComposeStatusPanel(state);
    Expect(sections[0].rows.size() == 5 &&
               sections[0].rows[2].value == "61/214" &&
               sections[0].rows[3].value == "43" &&
               sections[0].rows[4].value == "34%",
           "a connected client's counts and the game's own percentage read out");

    // What the client composes, rendered as its own blocks in reading order.
    state.locks_known = true;
    state.goal_rows = {{"Goal", "Package Fragments", StatusTone::kPlain},
                       {"Fragments", "7 of 20", StatusTone::kPlain}};
    state.strand_rows = {{"Cortez", "3 of 5", StatusTone::kPlain},
                         {"Diaz", "6 of 6", StatusTone::kOpen}};
    sections = ComposeStatusPanel(state);
    Expect(Section(sections, "GOAL").rows.size() == 2 &&
               Section(sections, "GOAL").rows[1].value == "7 of 20",
           "the goal block is the client's rows verbatim");
    // A row per strand, with the count made terse: a name and a count is what a
    // row is for, and a name like Vercetti Protection fills a wrapped line on its
    // own, so wrapping them would cost as many lines as rows.
    const StatusSection strands = Section(sections, "MISSION STRANDS");
    Expect(strands.rows.size() == 2 && strands.rows[0].label == "Cortez" &&
               strands.rows[0].value == "3/5",
           "each strand is a row of its name and its count");
    Expect(strands.rows[1].value == "6/6" &&
               strands.rows[1].tone == StatusTone::kOpen,
           "and a finished strand carries the tone the client gave it");

    // The game's own counts, which no client can answer: the package tally and
    // the level each emergency activity has reached.
    state.packages_collected = 37;
    state.packages_total = 100;
    state.paramedic_level = 7;
    sections = ComposeStatusPanel(state);
    const StatusSection own = Section(sections, "THE GAME COUNTS");
    Expect(own.rows.size() == 6 && own.rows[0].label == "Hidden Packages" &&
               own.rows[0].value == "37/100",
           "the package tally is the game's own count of them");
    Expect(own.rows[1].value == "7/12" && own.rows[2].value == "none",
           "and an emergency activity reads its level or says it has none");
    // The taxi and the pizza boy keep no level in the game's stats, and they do
    // not count alike: the taxi divides its career fares, while the pizza boy is
    // read from the level its mission is working on, because that mission hands
    // out one pizza per level number and a delivery total divides into nothing.
    StatusPanelState jobs = state;
    jobs.taxi_fares = 37;
    jobs.pizza_level_in_progress = 4;
    const StatusSection counted = ComposeRewardSection(jobs);
    Expect(counted.rows[4].label == "Taxi" && counted.rows[4].value == "3/10",
           "every tenth career fare is a taxi level");
    Expect(counted.rows[5].label == "Pizza" && counted.rows[5].value == "3/10",
           "and the pizza level in progress is not one the player has finished");

    jobs.pizza_level_in_progress = 1;
    Expect(ComposeRewardSection(jobs).rows[5].value == "none",
           "the first level being unfinished reads as none rather than as zero");

    // Level ten stays replayable, so the mission steps its level back to nine
    // and the win flag is the only thing that says the tenth is done.
    jobs.pizza_level_in_progress = 9;
    jobs.pizza_finished = true;
    const StatusSection won = ComposeRewardSection(jobs);
    Expect(won.rows[5].value == "10/10" && won.rows[5].tone == StatusTone::kOpen,
           "the win flag reads as all ten done however far the level has stepped back");

    jobs.taxi_fares = 999;
    jobs.pizza_finished = false;
    jobs.pizza_level_in_progress = 10;
    const StatusSection capped = ComposeRewardSection(jobs);
    Expect(capped.rows[4].value == "10/10" && capped.rows[5].value == "9/10",
           "fares past the last level do not read as an eleventh, and nor does "
           "standing on the tenth without having finished it");

    // One selected ability key and one unselected: only the selected one is
    // listed, since an unselected key is fully vanilla.
    state.ability_flags[kAbilitySprint] = 1;
    state.ability_flags[kAbilityWallet] = 1;
    state.ability_locked[kAbilityWallet] = true;
    sections = ComposeStatusPanel(state);
    const StatusSection abilities = Section(sections, "ABILITIES");
    Expect(abilities.rows.size() == 2 &&
               abilities.rows[0].value == "Locked: Wallet" &&
               abilities.rows[0].tone == StatusTone::kHeld &&
               abilities.rows[1].value == "Yours: Sprint" &&
               abilities.rows[1].tone == StatusTone::kOpen,
           "the abilities read as a locked list and a list you have");

    // A content class held in some districts reports the count; one held
    // everywhere does not, since eleven of eleven is what held already means.
    state.content_flags[kContentRampages] = 1;
    state.content_flags[kContentRobbableStores] = 1;
    state.content_districts_held[kContentRampages] = 7;
    state.content_districts_held[kContentRobbableStores] = kDistrictCount;
    sections = ComposeStatusPanel(state);
    // A class held in part of the city names the districts, and it names whichever
    // list is shorter: seven of eleven held reads as the four it is free in.
    for (int district = 0; district < 7; ++district) {
      state.content_held[static_cast<std::size_t>(kContentRampages) * kDistrictCount +
                         district] = true;
    }
    sections = ComposeStatusPanel(state);
    const StatusSection content = Section(sections, "CONTENT");
    Expect(content.rows.size() > 2 && content.rows[0].value == "HELD 7/11",
           "a class held in part of the city carries its district count");
    Expect(content.rows[1].label.empty() &&
               content.rows[1].value.rfind("free in:", 0) == 0 &&
               content.rows[1].tone == StatusTone::kOpen,
           "and names the districts it is free in, being the shorter list");
    Expect(content.rows.back().label == "Robbable Stores" &&
               content.rows.back().value == "HELD",
           "a class held everywhere needs no district list at all");
    // Held in three of eleven, and the held list is the shorter one.
    StatusPanelState few = state;
    few.content_districts_held[kContentRampages] = 3;
    few.content_held.fill(false);
    for (int district = 0; district < 3; ++district) {
      few.content_held[static_cast<std::size_t>(kContentRampages) * kDistrictCount +
                       district] = true;
    }
    const StatusSection fewer = ComposeContentSection(few);
    Expect(fewer.rows[1].value.rfind("held in:", 0) == 0 &&
               fewer.rows[1].value.find("Ocean Beach") != std::string::npos,
           "a class held in a few districts names those instead");

    // A class does not stand in all eleven districts. There are robbable stores
    // in five, so the count is read against those five, and the districts with
    // none of the class are named in neither list: telling the player stores are
    // free in Leaf Links sends them somewhere there is nothing to rob.
    StatusPanelState sparse;
    sparse.locks_known = true;
    sparse.content_flags[kContentRobbableStores] = 1;
    // Ocean Beach, Starfish Island, Prawn Island, Leaf Links, Viceport and
    // Escobar International hold no store, leaving five that do.
    for (const int district : {0, 3, 4, 5, 9, 10}) {
      sparse.content_absent[ContentDistrictSlot(kContentRobbableStores, district)] =
          true;
    }
    const int store_districts =
        ContentDistrictsPresent(sparse.content_absent, kContentRobbableStores);
    Expect(store_districts == 5, "five districts hold the robbable stores");

    for (const int district : {1, 2, 6, 7, 8}) {
      sparse.content_held[ContentDistrictSlot(kContentRobbableStores, district)] =
          true;
    }
    sparse.content_districts_held[kContentRobbableStores] = store_districts;
    StatusSection sparse_section = ComposeContentSection(sparse);
    Expect(sparse_section.rows.size() == 1 &&
               sparse_section.rows[0].value == "HELD",
           "a class held in every district that has it is simply held, not five "
           "of eleven");

    // One released of the five, so the free list is the shorter one and is the
    // one place an absent district would show.
    sparse.content_held[ContentDistrictSlot(kContentRobbableStores, 1)] = false;
    sparse.content_districts_held[kContentRobbableStores] = store_districts - 1;
    sparse_section = ComposeContentSection(sparse);
    Expect(sparse_section.rows[0].value == "HELD 4/5",
           "and a part-held class counts against the districts that have it");
    Expect(sparse_section.rows.size() > 1 &&
               sparse_section.rows[1].value.rfind("free in:", 0) == 0,
           "naming the free districts, being the shorter list");
    std::string sparse_free;
    for (std::size_t row = 1; row < sparse_section.rows.size(); ++row) {
      sparse_free += sparse_section.rows[row].value;
    }
    Expect(sparse_free.find("Washington Beach") != std::string::npos,
           "the district that really did open is named");
    for (const char* nowhere : {"Ocean Beach", "Starfish Island", "Prawn Island",
                                "Leaf Links", "Viceport", "Escobar"}) {
      Expect(sparse_free.find(nowhere) == std::string::npos,
             "and a district with no store of its own is not offered as free");
    }

    // Absence is what a default state knows none of, so a page built before the
    // globals were read reports what it always did rather than blanking.
    StatusPanelState unfilled;
    unfilled.locks_known = true;
    unfilled.content_flags[kContentRampages] = 1;
    unfilled.content_districts_held[kContentRampages] = kDistrictCount;
    Expect(ComposeContentSection(unfilled).rows[0].value == "HELD",
           "a state that knows of no absence counts all eleven, the old reading");

    state.content_districts_held[kContentRampages] = 0;
    state.content_held.fill(false);
    sections = ComposeStatusPanel(state);
    Expect(Section(sections, "CONTENT").rows[0].value == "available" &&
               Section(sections, "CONTENT").rows[0].tone == StatusTone::kOpen,
           "and a released class reads as available");

    // A route waiting on its second item is neither open nor plainly shut, and
    // the row is the one place a player can read that.
    state.route_labels = {"Prawn Island Bridge", "Starfish Island Causeway"};
    state.route_states = {RouteState::kOpen, RouteState::kWaiting};
    sections = ComposeStatusPanel(state);
    const StatusSection routes = Section(sections, "CROSSINGS");
    Expect(routes.rows.size() == 2 && routes.rows[0].value == "open" &&
               routes.rows[1].value == "needs its island",
           "each route reads out what it is doing");

    // And it NAMES what it is waiting for where the seed sent a label, which is
    // the only place that is said now that nothing announces a route.
    state.route_needs_labels = {"", "Starfish Island Access"};
    Expect(Section(ComposeStatusPanel(state), "CROSSINGS").rows[1].value ==
               "needs Starfish Island Access",
           "a waiting route names the item it waits for");
    // A client one field older sends no labels at all, and the generic line stands
    // in rather than the row reading as waiting for nothing.
    state.route_needs_labels.clear();
    Expect(Section(ComposeStatusPanel(state), "CROSSINGS").rows[1].value ==
               "needs its island",
           "and falls back where no label was sent");
    state.route_needs_labels = {"", "Starfish Island Access"};

    // A route list out of step with its states is a caller error, not a crash:
    // the rows stop at the shorter of the two.
    state.route_states = {RouteState::kOpen};
    Expect(Section(ComposeStatusPanel(state), "CROSSINGS").rows.size() == 1,
           "a route list out of step with its states stops at the shorter one");
    state.route_states = {RouteState::kOpen, RouteState::kWaiting};

    // The radio and the minimap only have rows while their options are on, and a
    // section with no rows is not on the page at all.
    Expect(!HasSection(ComposeStatusPanel(state), "RADIO") &&
               !HasSection(ComposeStatusPanel(state), "MINIMAP"),
           "the radio and minimap blocks stay away while their options are off");
    state.radio_randomized = true;
    state.radio_unlocked[0] = true;
    state.minimap_shuffled = true;
    sections = ComposeStatusPanel(state);
    const StatusSection radio = Section(sections, "RADIO");
    Expect(radio.rows.size() < static_cast<std::size_t>(kRadioStationCount) &&
               radio.rows[0].value == "Yours: Wildstyle" &&
               radio.rows[0].tone == StatusTone::kOpen,
           "the stations you have read as one wrapped list");
    bool locked_listed = false;
    for (const StatusRow& row : radio.rows) {
      if (row.value.rfind("Locked:", 0) == 0 && row.tone == StatusTone::kHeld) {
        locked_listed = true;
      }
    }
    Expect(locked_listed, "and the locked ones as another");
    Expect(Section(sections, "MINIMAP").rows.size() == 1 &&
               Section(sections, "MINIMAP").rows[0].value == "HIDDEN",
           "and the radar says whether the item has arrived");

    // The pause page's recent messages. Laid out UNDER the columns across the whole
    // page rather than dealt into one of them, so it is composed on its own and is
    // deliberately NOT a section of the page the columns are flowed from.
    {
      const auto movement = [](const std::string& item, const std::string& location) {
        ToastRow row;
        std::vector<ToastSegment> line = {{"You", ToastRole::kOwnSlot},
                                          {" found your ", ToastRole::kConnective},
                                          {item, ToastRole::kProgression}};
        if (!location.empty()) {
          line.push_back({" (", ToastRole::kConnective});
          line.push_back({location, ToastRole::kLocation});
          line.push_back({")", ToastRole::kConnective});
        }
        row.lines.push_back(line);
        return row;
      };

      StatusPanelState state;
      Expect(ComposeRecentSection(state).rows.empty(),
             "a seed that has moved no item has no recent block at all");
      // And it is never dealt into the columns, whatever it holds: a message is a
      // sentence and a location, and in a 146 unit column every one of them was cut.
      state.recent_rows = {movement("Body Armour", "Cherry Popper Fourth Delivery")};
      // Read directly rather than through HasSection, whose own guard requires
      // every heading it is asked for to appear on some page. This one deliberately
      // appears on none: it is drawn under the columns, not dealt into them.
      bool dealt_into_a_column = false;
      for (const StatusSection& section : ComposeStatusPanel(state)) {
        if (section.heading == "RECENT MESSAGES") dealt_into_a_column = true;
      }
      Expect(!dealt_into_a_column, "the recent block is not a column section");

      const StatusSection recent = ComposeRecentSection(state);
      Expect(recent.heading == "RECENT MESSAGES", "and it names itself in full");
      Expect(recent.rows.size() == 1,
             "a movement is ONE row, the sentence and its location together");
      Expect(recent.rows[0].label.empty() && recent.rows[0].value.empty(),
             "a segmented row carries no label and no value, so nothing about the "
             "page's own rows is changed by its presence");
      Expect(recent.rows[0].segments[0].role == ToastRole::kOwnSlot,
             "and it keeps the colours the stack drew it in");
      Expect(ToastLineText(state.recent_rows[0].lines[0]) ==
                 "You found your Body Armour (Cherry Popper Fourth Delivery)",
             "the whole message is one line");

      // Bounded, so a long history cannot run off the band the columns left it.
      state.recent_rows.clear();
      for (int index = 0; index < 40; ++index) {
        state.recent_rows.push_back(movement("Item", "Somewhere"));
      }
      Expect(ComposeRecentSection(state).rows.size() == kRecentMaxLines,
             "one-line rows fill the budget to the line and no further");

      // A two-line row can still reach here, since a notice is broken rather than
      // cut, and it is taken whole or not at all.
      state.recent_rows.clear();
      for (int index = 0; index < 40; ++index) {
        ToastRow two = movement("Item", "");
        two.lines.push_back({{"second", ToastRole::kConnective}});
        state.recent_rows.push_back(two);
      }
      // Where the block lands, and whether it lands at all. This is what keeps it
      // off the columns above it and off the pause page's own back button below.
      {
        constexpr float kTop = 60.0f;
        constexpr float kRow = 13.0f;
        Expect(RecentFooterTop(kTop, kRow, 10) == kTop + kRow * 11.0f,
               "the block starts a blank row under the tallest column");
        Expect(RecentFooterTop(kTop, kRow, 0) == kTop + kRow,
               "and a page with no rows at all still leaves that blank row");
        const float footer_top = RecentFooterTop(kTop, kRow, 10);
        Expect(!RecentFooterFits(footer_top, footer_top + kRow, kRow),
               "a band with room for a heading alone draws no block, since a "
               "heading over nothing says less than nothing");
        Expect(RecentFooterFits(footer_top, footer_top + kRow * 2.0f, kRow),
               "a heading and one message is enough to be worth the band");
        Expect(RecentFooterRows(footer_top, footer_top + kRow * 2.0f, kRow, 9) == 1,
               "and that band holds exactly the one message");
        Expect(RecentFooterRows(footer_top, footer_top + kRow * 5.0f, kRow, 2) == 2,
               "a band with room to spare holds only what there is to show");
        Expect(RecentFooterRows(footer_top, footer_top, kRow, 9) == 0,
               "and a band of nothing holds nothing");
      }

      const StatusSection pairs = ComposeRecentSection(state);
      Expect(pairs.rows.size() % 2 == 0 && pairs.rows.size() <= kRecentMaxLines,
             "a multi-line row is taken whole, never half");
      // Nothing marks them as belonging together, and nothing needs to: the block
      // is drawn as one run under the columns, so its lines are always adjacent.
      // The column dealing, which is what joined_above exists for, never sees them.
    }

    // The comparison the two sets above exist for.
    for (const std::string& heading : asked_headings) {
      if (page_headings.count(heading) != 0) continue;
      const std::string unknown = "no page ever carries a section headed " + heading;
      Expect(false, unknown.c_str());
    }

    // Every wrapped line is drawn from the column's own left edge, so what it has
    // to fit is the whole column; a line carrying a label would start a third of
    // the way in and this bound would not cover it. Checked over every
    // combination of unlocked stations, since which names share a line is what
    // decides the widest one, and over the abilities for the same reason.
    bool every_line_fits = true;
    for (int combination = 0; combination < (1 << kRadioStationCount);
         ++combination) {
      StatusPanelState radio_state = state;
      for (int station = 0; station < kRadioStationCount; ++station) {
        radio_state.radio_unlocked[station] = (combination & (1 << station)) != 0;
      }
      for (const StatusRow& row : ComposeRadioSection(radio_state).rows) {
        if (!row.label.empty() || row.value.size() > kWrappedLineChars) {
          every_line_fits = false;
        }
      }
    }
    for (int combination = 0; combination < (1 << kAbilityCount); ++combination) {
      StatusPanelState ability_state = state;
      for (int index = 0; index < kAbilityCount; ++index) {
        ability_state.ability_flags[index] = 1;
        ability_state.ability_locked[index] = (combination & (1 << index)) != 0;
      }
      for (const StatusRow& row : ComposeAbilitySection(ability_state).rows) {
        if (!row.label.empty() || row.value.size() > kWrappedLineChars) {
          every_line_fits = false;
        }
      }
    }
    Expect(every_line_fits,
           "no wrapped line carries a label or outgrows a column, whichever "
           "stations and abilities the seed handed out");

    // The page is flattened into lines and dealt into columns of even height, so
    // one tall block continues in the next column instead of setting the row
    // height for the whole page.
    const std::vector<PanelLine> lines = FlattenPanel(sections);
    const std::vector<std::vector<PanelLine>> columns = PlanPanelColumns(lines, 4);
    Expect(columns.size() == 4, "the plan has a column for every column asked for");
    std::size_t placed = 0;
    for (const std::vector<PanelLine>& column : columns) placed += column.size();
    Expect(placed <= lines.size(),
           "no line is dealt twice, and a blank at a column head is dropped");
    // Reading order survives the dealing: the labels come out in the order they
    // went in, blanks aside.
    std::vector<std::string> flowed;
    for (const std::vector<PanelLine>& column : columns) {
      for (const PanelLine& line : column) {
        if (!line.blank) flowed.push_back(line.label + "|" + line.value);
      }
    }
    std::vector<std::string> composed;
    for (const PanelLine& line : lines) {
      if (!line.blank) composed.push_back(line.label + "|" + line.value);
    }
    Expect(flowed == composed, "and every line is dealt exactly once, in order");
    // No column opens with a blank line or ends with a heading, so a title always
    // sits above lines of its own.
    bool well_formed = true;
    for (const std::vector<PanelLine>& column : columns) {
      if (column.empty()) continue;
      if (column.front().blank || column.back().heading) well_formed = false;
    }
    Expect(well_formed, "no column opens on a blank line or ends on a heading");
    // Even to within one line, which is what keeps the text at its full size.
    int tallest = TallestColumn(columns);
    int shortest = tallest;
    for (const std::vector<PanelLine>& column : columns) {
      shortest = static_cast<int>(column.size()) < shortest
                     ? static_cast<int>(column.size())
                     : shortest;
    }
    Expect(tallest - shortest <= 3, "the columns come out within a few lines of each other");
    Expect(PlanPanelColumns(lines, 0).empty(), "asking for no columns plans none");
    Expect(PlanPanelColumns({}, 4).size() == 4 && PlanPanelColumns({}, 4)[0].empty(),
           "an empty panel plans empty columns");

    // The busiest page any seed can produce still fits the room the cover leaves:
    // 337 of the frontend's units once the borrowed page's back entry stands at
    // the foot of the screen, and a row is 13 at the design size, so twenty-five
    // lines a column is full size and the busiest seed lands just the other side
    // of that.
    //
    // Six districts held of eleven is what fills the page, not five and not all:
    // a class names whichever side is shorter, so six held names the five it is
    // free in, and those five are the long names.
    StatusPanelState full = state;
    full.locks_known = true;
    for (int index = 0; index < kAbilityCount; ++index) full.ability_flags[index] = 1;
    for (int index = 0; index < kContentCount; ++index) {
      full.content_flags[index] = 1;
      full.content_districts_held[index] = 6;
      for (int district = 0; district < 6; ++district) {
        full.content_held[static_cast<std::size_t>(index) * kDistrictCount +
                          district] = true;
      }
    }
    full.strand_rows.clear();
    for (int index = 0; index < 20; ++index) {
      full.strand_rows.push_back({"Vercetti Protection", "1/6", StatusTone::kPlain});
    }
    full.route_labels = {"Prawn Island Bridge", "Leaf Links Bridge",
                         "Ocean Beach Bridge", "Starfish Island Causeway"};
    full.route_states = {RouteState::kOpen, RouteState::kAbsent,
                         RouteState::kAbsent, RouteState::kWaiting};
    full.packages_total = 100;
    const std::vector<PanelLine> worst = FlattenPanel(ComposeStatusPanel(full));
    Expect(TallestColumn(PlanPanelColumns(worst, 4)) <= 26,
           "the busiest seed stays inside twenty-six lines a column");
    // And once every line is narrowed to its column, which is what the page is
    // really laid out from, it still fits the band at a size worth reading.
    const std::vector<PanelLine> narrowed =
        FitPanelLines(worst, kColumnUnits, kLabelGapUnits, MeasureUnits,
                      MeasureHeadingUnits);
    const int narrowed_tallest = TallestColumn(PlanPanelColumns(narrowed, 4));
    Expect(narrowed_tallest <= 28,
           "and inside twenty-eight once every line is narrowed to its column");
    Expect(FittedRowHeight(narrowed_tallest, kBandUnits, kDesignRowUnits) >
               kDesignRowUnits * 0.9f,
           "so the busiest seed still draws at nearly the design size");
    Expect(FittedRowHeight(narrowed_tallest, kFallbackBandUnits, kDesignRowUnits) >
               kDesignRowUnits * 0.65f,
           "and still reads on the shorter band, which is what it gets where that "
           "entry cannot be moved");

    // Nothing the fitting hands back is wider than its column, one long word
    // aside, which is the property the one-row-per-line drawing rests on. Run over
    // this page rather than a fixture of its own, because this is the one that has
    // the partly held district lists, the strand rows and the goal rows: the lines
    // the fitting exists for. Run again at a narrower column, which is what a font
    // whose characters run wider than the average amounts to, since a flat measure
    // and the composer's own character budget agree by construction and only the
    // narrow pass puts the composed lists through the re-breaking.
    bool every_line_narrow = true;
    for (const float column : {kColumnUnits, kColumnUnits * 0.75f}) {
      const std::vector<PanelLine> narrow = FitPanelLines(
          worst, column, kLabelGapUnits, MeasureUnits, MeasureHeadingUnits);
      for (const PanelLine& line : narrow) {
        if (line.blank) continue;
        const std::string& text = line.label.empty() ? line.value : line.label;
        const bool one_word =
            text.find(' ', text.find_first_not_of(' ')) == std::string::npos;
        float width = 0.0f;
        if (!line.label.empty()) {
          width += line.heading ? MeasureHeadingUnits(line.label)
                                : MeasureUnits(line.label);
        }
        if (!line.value.empty()) width += MeasureUnits(line.value);
        if (!line.label.empty() && !line.value.empty()) width += kLabelGapUnits;
        if (width > column && !one_word) every_line_narrow = false;
      }
    }
    Expect(every_line_narrow,
           "no line the fitting hands back is wider than its column, one long word "
           "aside");

    // A run of lines the fitting broke out of one line stays in one column, so a
    // value it moved off its label's row is never dealt away from that label. The
    // dealing can only break such a run where it is longer than the column itself,
    // and then it leaves a single line behind, so a column opening on a broken-out
    // line means the one before it holds exactly that.
    bool runs_stay_whole = true;
    for (const float column : {kColumnUnits, kColumnUnits * 0.75f}) {
      const std::vector<std::vector<PanelLine>> dealt = PlanPanelColumns(
          FitPanelLines(worst, column, kLabelGapUnits, MeasureUnits,
                        MeasureHeadingUnits),
          4);
      for (std::size_t index = 1; index < dealt.size(); ++index) {
        if (dealt[index].empty() || !dealt[index].front().joined_above) continue;
        if (dealt[index - 1].size() != 1) runs_stay_whole = false;
      }
    }
    Expect(runs_stay_whole,
           "and no column opens on a line broken out of the one before it, short "
           "of a run longer than a column");

    // A list of one needs no wrapping, a list of none produces no line at all,
    // and a name wider than the column still gets drawn rather than truncated.
    Expect(WrapNameList("Locked", {}, StatusTone::kHeld, kWrappedLineChars).empty(),
           "an empty list produces no line");
    const std::vector<StatusRow> one =
        WrapNameList("Yours", {"Wave 103"}, StatusTone::kOpen, kWrappedLineChars);
    Expect(one.size() == 1 && one[0].value == "Yours: Wave 103",
           "a list of one is one line, prefix and all");
    const std::vector<StatusRow> wide =
        WrapNameList("Yours", {"A Station Name Longer Than Any Column"},
                     StatusTone::kOpen, 10);
    Expect(wide.size() == 1 &&
               wide[0].value == "Yours: A Station Name Longer Than Any Column",
           "a name wider than the column is drawn whole rather than cut");
    // Continuations line up under the prefix, so a list reads as one block.
    const std::vector<StatusRow> several =
        WrapNameList("Locked", {"Flash FM", "K-Chat", "Fever 105", "V-Rock", "VCPR"},
                     StatusTone::kHeld, 24);
    Expect(several.size() > 1 && several[0].value == "Locked: Flash FM,",
           "the first line carries the prefix and as much as fits");
    Expect(several[1].value.rfind("        ", 0) == 0,
           "and every line after it is indented under that prefix");
  }

  // Every line is narrowed to its column before the page is laid out, because the
  // drawing gives each one a single row and the font answers a line that reaches
  // the column's edge by folding its tail onto the row below, where it prints over
  // whatever is there.
  {
    // A pair that fits keeps its row, however little room is left over.
    const std::vector<PanelLine> fits =
        FitPanelLines({{"Taxi", "none", StatusTone::kPlain, false, false}},
                      kColumnUnits, kLabelGapUnits, MeasureUnits,
                      MeasureHeadingUnits);
    Expect(fits.size() == 1 && fits[0].label == "Taxi" && fits[0].value == "none" &&
               !fits[0].value_alone,
           "a label and a value that fit a column share their row");

    // One that does not is split, and the value keeps the tone that says what it
    // means. This is the shape the content blocks draw: a class name, then whether
    // it is held and in how many districts.
    const std::vector<PanelLine> split = FitPanelLines(
        {{"Property Purchases", "HELD 10/11", StatusTone::kHeld, false, false}},
        kColumnUnits, kLabelGapUnits, MeasureUnits, MeasureHeadingUnits);
    Expect(split.size() == 2 && split[0].label == "Property Purchases" &&
               split[0].value.empty(),
           "a pair too wide for its column leaves the label a row of its own");
    Expect(split[1].label.empty() && split[1].value == "HELD 10/11" &&
               split[1].value_alone && split[1].joined_above &&
               split[1].tone == StatusTone::kHeld,
           "and hands the value the next row, against the column's right edge");

    // A wrapped line wider than its column is re-broken at its own spaces, and
    // every line it breaks into carries the list's indent so the block still reads
    // as one.
    const std::vector<PanelLine> rebroken = FitPanelLines(
        {{"", "         Escobar International", StatusTone::kOpen, false, false}},
        kColumnUnits, kLabelGapUnits, MeasureUnits, MeasureHeadingUnits);
    Expect(rebroken.size() == 2 && rebroken[0].value == "         Escobar" &&
               rebroken[1].value == "         International" &&
               rebroken[1].joined_above,
           "a wrapped line too wide for its column breaks again under its indent");

    // The line a list's prefix rides on has no indent of its own, so its
    // continuations are set in as far as that prefix runs, which is where the
    // composer's own wrapping puts them.
    const std::vector<PanelLine> prefixed = FitPanelLines(
        {{"", "free in: Escobar International", StatusTone::kOpen, false, false}},
        kColumnUnits, kLabelGapUnits, MeasureUnits, MeasureHeadingUnits);
    Expect(prefixed.size() == 2 && prefixed[0].value == "free in: Escobar" &&
               prefixed[1].value == "         International",
           "and a line carrying the prefix indents under it rather than under "
           "nothing");

    // A word wider than a column is left where it is: it has no space to break at,
    // so the font cannot fold it either, and cutting it would hide what it names.
    const std::vector<PanelLine> unbreakable = FitPanelLines(
        {{"", "AStationNameLongerThanAnyColumn", StatusTone::kOpen, false, false}},
        kColumnUnits, kLabelGapUnits, MeasureUnits, MeasureHeadingUnits);
    Expect(unbreakable.size() == 1 &&
               unbreakable[0].value == "AStationNameLongerThanAnyColumn",
           "a word wider than a column is drawn whole rather than cut");

    // A blank line carries no text, and a heading that fits comes through whole.
    const std::vector<PanelLine> passed =
        FitPanelLines({{"", "", StatusTone::kPlain, false, true},
                       {"MISSION STRANDS", "", StatusTone::kPlain, true, false}},
                      kColumnUnits, kLabelGapUnits, MeasureUnits,
                      MeasureHeadingUnits);
    Expect(passed.size() == 2 && passed[0].blank && passed[1].heading &&
               passed[1].label == "MISSION STRANDS",
           "a blank line and a heading that fits come through the fitting whole");

    // A heading is measured in its OWN face, which draws wider than the body face
    // at the same scale. Measured under the body face this one would fit, and it is
    // the line nothing else would catch: the taller the band, the larger the whole
    // page draws, and a heading that folds costs the row under it.
    const std::vector<PanelLine> heading = FitPanelLines(
        {{"THE GAME COUNTS AND MORE", "", StatusTone::kPlain, true, false}},
        kColumnUnits, kLabelGapUnits, MeasureUnits, MeasureHeadingUnits);
    Expect(MeasureUnits("THE GAME COUNTS AND MORE") <= kColumnUnits &&
               heading.size() > 1 && heading[0].heading && heading[1].heading &&
               heading[1].joined_above,
           "a heading too wide for its column in its own face is broken in it");

    // The row height is the design's own until the rows outgrow the band, and then
    // it is exactly the band's share, so the page fits whole either way.
    Expect(FittedRowHeight(10, kBandUnits, kDesignRowUnits) == kDesignRowUnits,
           "a page that fits the band draws at the design row height");
    Expect(FittedRowHeight(0, kBandUnits, kDesignRowUnits) == kDesignRowUnits,
           "and a page with no rows at all does too");
    const float tight = FittedRowHeight(50, kBandUnits, kDesignRowUnits);
    Expect(tight == kBandUnits / 50.0f,
           "a page that outgrows it takes the band's own share");
    // The text follows the rows, which is what keeps a measured line honest: a
    // line that fits at the design size cannot outgrow its column once the page is
    // drawn smaller than that.
    Expect(FittedTextScale(kDesignRowUnits, kDesignRowUnits) == 1.0f,
           "text at the design row height draws at its design size");
    Expect(FittedTextScale(tight, kDesignRowUnits) < 1.0f &&
               FittedTextScale(tight, kDesignRowUnits) == tight / kDesignRowUnits,
           "and tighter rows scale the text by exactly as much");
  }

  // What the panel does with a menu frame. The borrowed page has no idea which
  // row opened it, since the game resets the highlight when the page changes, so
  // the decision is a latch taken on the pause menu. This is the part that failed
  // in game when the panel had a page of its own.
  {
    PanelMenuState menu;
    menu.owns_entry = true;
    menu.game_loaded = true;
    menu.pause_page = 32;
    menu.host_page = 2;
    menu.panel_entry = 6;

    // Standing on the panel's row arms it, and that row goes into the borrowed
    // page's parent entry so going back lands there.
    menu.page = 32;
    menu.highlighted_entry = 6;
    menu.highlighted_entry_targets_host = true;
    PanelFrame frame = PlanPanelFrame(menu, false);
    Expect(frame.armed && !frame.draw && frame.parent_entry == 6,
           "the panel's own row arms the borrowed page");

    // The page opens with the highlight reset to its first row, and the latch is
    // what carries the answer across.
    menu.page = 2;
    menu.highlighted_entry = 0;
    menu.highlighted_entry_targets_host = false;
    frame = PlanPanelFrame(menu, true);
    Expect(frame.draw && frame.armed && frame.parent_entry < 0,
           "and the panel draws on the borrowed page while it holds");

    // The borrowed page's own row disarms it, so its vanilla content still opens.
    menu.page = 32;
    menu.highlighted_entry = 4;
    menu.highlighted_entry_targets_host = true;
    frame = PlanPanelFrame(menu, true);
    Expect(!frame.armed && frame.parent_entry == 4,
           "the page's own row disarms the panel and takes the parent entry");
    menu.page = 2;
    menu.highlighted_entry = 0;
    menu.highlighted_entry_targets_host = false;
    Expect(!PlanPanelFrame(menu, false).draw,
           "so the borrowed page shows its own content");

    // A row opening some other page never reaches that page's parent entry: the
    // field would name a row that cannot lead there.
    menu.page = 32;
    menu.highlighted_entry = 0;
    menu.highlighted_entry_targets_host = false;
    frame = PlanPanelFrame(menu, true);
    Expect(!frame.armed && frame.parent_entry < 0,
           "another page's row is not written into the borrowed page");

    // A page that is neither the pause menu nor the borrowed one leaves the latch
    // alone: the player is somewhere else in the menu and will come back through
    // the pause page, which is the only place the answer is set.
    menu.page = 27;
    menu.highlighted_entry = 0;
    menu.highlighted_entry_targets_host = false;
    Expect(PlanPanelFrame(menu, true).armed && !PlanPanelFrame(menu, true).draw,
           "another page neither arms nor disarms the panel");
    Expect(!PlanPanelFrame(menu, false).armed,
           "and cannot arm it either");

    // A row outside the pause page's own entries reads as no row at all.
    menu.page = 32;
    menu.highlighted_entry = -1;
    menu.highlighted_entry_targets_host = true;
    PanelFrame stray = PlanPanelFrame(menu, true);
    Expect(!stray.armed && stray.parent_entry < 0,
           "a row the page does not have arms nothing and is never written back");

    // No entry, no panel, whatever the latch says; and no game, no panel either,
    // since the borrowed page is reachable from the frontend's own menu too.
    menu.owns_entry = false;
    menu.page = 2;
    Expect(!PlanPanelFrame(menu, true).armed && !PlanPanelFrame(menu, true).draw,
           "without the entry there is nothing to draw");
    menu.owns_entry = true;
    menu.game_loaded = false;
    Expect(!PlanPanelFrame(menu, true).draw,
           "and the panel stays off the frontend's own menu");
  }

  // The completion percentage as the stats menu prints it. The menu converts
  // with the rounding mode set to round-toward-zero, so a player two thirds of
  // the way into a point reads the point below, and the tracker has to agree
  // with that screen digit for digit.
  Expect(DisplayedPercentage(0.0f) == 0, "no progress reads zero");
  Expect(DisplayedPercentage(93.5f) == 93, "the menu truncates rather than rounds");
  Expect(DisplayedPercentage(99.9f) == 99, "a hair short of the end is not the end");
  Expect(DisplayedPercentage(100.0f) == 100, "a finished game reads a hundred");
  Expect(DisplayedPercentage(-1.0f) == 0, "a negative stat reads zero");
  Expect(DisplayedPercentage(120.0f) == 100, "nothing reads past a hundred");
  Expect(DisplayedPercentage(std::numeric_limits<float>::quiet_NaN()) == 0,
         "a not-a-number stat reads zero");
  Expect(DisplayedPercentage(std::numeric_limits<float>::infinity()) == 100,
         "an infinite stat reads a hundred");
  const json progress = ProgressMessage(93);
  const std::vector<json> progress_result = RoundTrip(progress);
  Expect(progress_result.size() == 1 && progress_result[0] == progress,
         "progress round-trip");

  // The landing report, which the client turns into the row the player reads. Its
  // own frame rather than only the planner behind it, since it is the client's one
  // source of a row for an item arriving and a frame that does not decode leaves
  // the stack silent about everything received.
  const json applied = AppliedMessage(41);
  const std::vector<json> applied_result = RoundTrip(applied);
  Expect(applied_result.size() == 1 && applied_result[0] == applied &&
             applied_result[0]["index"] == 41,
         "applied round-trip, carrying the received index");

  if (failures == 0) {
    std::cout << "OK: protocol self-test passed\n";
    return 0;
  }
  return 1;
}
