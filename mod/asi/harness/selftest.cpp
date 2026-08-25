// Standalone protocol self-test: round-trips framing (small and chunked) and
// checks the guards, with no socket and no game. Proves the C++ protocol layer
// compiles and behaves in the 32-bit MSVC toolchain.
#include <algorithm>
#include <array>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <vector>

#include "../src/protocol.hpp"
#include "../src/scm_ability_locks.hpp"
#include "../src/scm_completion.hpp"
#include "../src/scm_content_locks.hpp"
#include "../src/scm_crossings.hpp"
#include "../src/scm_effects.hpp"
#include "../src/scm_finale_warp.hpp"
#include "../src/scm_grant_pacing.hpp"
#include "../src/scm_minimap.hpp"
#include "../src/scm_packages.hpp"
#include "../src/scm_pickup_layout.hpp"
#include "../src/scm_progress.hpp"
#include "../src/scm_radio.hpp"
#include "../src/scm_status_panel.hpp"
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
    grants.last_raised_index = 9042;
    TakeGrantSlot(grants.pacer, 1000, 250, 5000, 8);
    ResetGrantsForNewGame(grants, across);
    Expect(across.size() == 2 && across[0] == 542000004 && across[1] == 542000005,
           "a game boundary leaves every queued check where it is");
    Expect(grants.last_raised_index == -1 && !grants.pacer.started,
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
    const UnlockPlan from_start = PlanUnlocks(pending, -1);
    Expect(from_start.has_raise && from_start.raise_index == 9010 &&
               from_start.raise_value == 3,
           "the first raise of a pass is the lowest pending global");
    Expect(PlanUnlocks(pending, 9010).raise_index == 9017 &&
               PlanUnlocks(pending, 9010).raise_value == 5,
           "the next starts past the one just handed over");
    Expect(PlanUnlocks(pending, 9017).raise_index == 9026 &&
               PlanUnlocks(pending, 9017).raise_value == 2,
           "and the next past that, so a stuck global costs one slot a pass");
    // The wrap carries the TARGET, not what the global already holds: a wrap
    // that wrote the current value would spin forever on the same global and
    // its item would never apply.
    Expect(PlanUnlocks(pending, 9026).raise_index == 9010 &&
               PlanUnlocks(pending, 9026).raise_value == 3,
           "a pass that runs out wraps to the lowest pending global again");
    Expect(PlanUnlocks(pending, 9999).raise_index == 9010 &&
               PlanUnlocks(pending, 9999).raise_value == 3,
           "a cursor above every pending global wraps rather than stalling");

    // One pending global that keeps needing the same raise is served every
    // pass rather than skipped for being the one just handed over.
    const std::vector<UnlockObservation> alone = {{9010, 4, 1, false}};
    Expect(PlanUnlocks(alone, 9010).has_raise &&
               PlanUnlocks(alone, 9010).raise_index == 9010 &&
               PlanUnlocks(alone, 9010).raise_value == 4,
           "a single pending global is retried, at its target, not starved");

    // Lowering is not paced and not rationed: every global above its target
    // comes back in one plan, alongside whichever single raise was chosen.
    const std::vector<UnlockObservation> mixed = {
        {9010, 0, 3, false}, {9011, 2, 0, false}, {9012, 1, 4, false},
        {9013, 0, 2, true}};
    const UnlockPlan both = PlanUnlocks(mixed, -1);
    Expect(both.to_lower.size() == 2 && both.to_lower[0].first == 9010 &&
               both.to_lower[0].second == 0 && both.to_lower[1].first == 9012 &&
               both.to_lower[1].second == 1,
           "every global above its target is lowered in one plan");
    Expect(both.has_raise && both.raise_index == 9011 && both.raise_value == 2,
           "and exactly one raise is chosen alongside them");
    Expect(!PlanUnlocks({{9013, 0, 2, true}}, -1).has_raise &&
               PlanUnlocks({{9013, 0, 2, true}}, -1).to_lower.empty(),
           "a stamped global is neither raised nor lowered");

    Expect(!PlanUnlocks({}, -1).has_raise,
           "nothing pending is nothing planned");

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

  // What an in-shop pickup prices from, in the order the purchase path resolves
  // it. The order is the whole of this: the three fixed models are compared
  // before anything reads a model info, so resolving them the other way round
  // prices a stand off a field that means nothing for it.
  {
    PickupFixedPriceModels fixed;
    fixed.body_armour = 368;
    fixed.health = 366;
    fixed.adrenaline = 367;
    // Distinct on purpose. The game gives armour and adrenaline the same type,
    // so using the real pair here would leave the first and third clauses
    // indistinguishable and a swap between them would redden nothing.
    fixed.body_armour_weapon_type = 0x26;
    fixed.health_weapon_type = 0x25;
    fixed.adrenaline_weapon_type = 0x21;
    // A model info value that must never win where a fixed model matches.
    const int ignored = 99;
    Expect(PickupWeaponTypeForPrice(366, fixed, ignored, 1) == 0x25,
           "a health stand prices from its fixed type, not its model info");
    Expect(PickupWeaponTypeForPrice(368, fixed, ignored, 1) == 0x26,
           "and so does body armour");
    Expect(PickupWeaponTypeForPrice(367, fixed, ignored, 1) == 0x21,
           "and adrenaline, by its own clause and not body armour's");
    Expect(PickupWeaponTypeForPrice(-1, fixed, ignored, 1) == 0,
           "a model of minus one prices from nothing, the way the table does");
    Expect(PickupWeaponTypeForPrice(kPickupCheckMarkerModel, fixed, ignored, 1) == 1,
           "the marker prices at what the ASI charges for it");
    Expect(PickupWeaponTypeForPrice(274, fixed, ignored, 1) == ignored,
           "and any other model prices from its model info");
    // The marker's type is the caller's to choose, so a value no other clause
    // returns proves the parameter is what comes back.
    Expect(PickupWeaponTypeForPrice(kPickupCheckMarkerModel, fixed, ignored, 7) == 7,
           "and the marker's price is whatever the caller asks for");
    // The shipped constant through the same clause, which pins that no earlier
    // clause intercepts the marker model, the three fixed ones included. The
    // order among those clauses is pinned by the cases above. It cannot pin the
    // constant's VALUE, being an identity in it; the tripwire below does that.
    Expect(PickupWeaponTypeForPrice(kPickupCheckMarkerModel, fixed, ignored,
                                    kPickupCheckMarkerWeaponType)
               == kPickupCheckMarkerWeaponType,
           "the marker prices from the shipped marker weapon type");
    // A tripwire, not a derivation: what makes 12 right is that CostOfWeapon
    // holds a thousand there, which only the game's own table can say. The ASI
    // reads it at load and logs a mismatch; this refuses a silent edit to either
    // half of the pair.
    Expect(kPickupCheckMarkerWeaponType == 12 &&
               kPickupCheckMarkerPriceInDollars == 1000,
           "the marker's price index and its documented price still agree; "
           "re-read CostOfWeapon before changing either");

    // A name that never resolved leaves 0xFFFF in the game's own slot, which the
    // game reads unsigned, so it can never match a model. Minus one must still
    // reach the minus one clause and not be swallowed by one of the three, so
    // each of them carries a type that would be visible if it were.
    PickupFixedPriceModels unresolved;
    unresolved.body_armour_weapon_type = 0x11;
    unresolved.health_weapon_type = 0x12;
    unresolved.adrenaline_weapon_type = 0x13;
    Expect(unresolved.body_armour == 0xFFFF &&
               unresolved.health == 0xFFFF &&
               unresolved.adrenaline == 0xFFFF,
           "all three fields default to the 0xFFFF the game leaves in an "
           "unresolved slot");
    Expect(PickupWeaponTypeForPrice(-1, unresolved, ignored, 1) == 0,
           "an unresolved fixed model does not swallow the minus one case");

    // Which model infos carry the weapon type at all. Leaving the weapon kind
    // out reads as a working dump whose price column simply says nothing, and
    // the models it drops are the weapons, which is most of what a shop sells.
    // Literals, not the constants, so this pins WHICH kinds are admitted rather
    // than restating the disjunction with its own names.
    Expect(ModelInfoCarriesWeaponType(4),
           "a weapon model info carries the weapon type");
    Expect(ModelInfoCarriesWeaponType(1) && ModelInfoCarriesWeaponType(3),
           "and so do the simple and time kinds it derives from");
    for (const int kind : {0, 2, 5, 6, 7, -1}) {
      Expect(!ModelInfoCarriesWeaponType(kind),
             "and no other kind does, since that offset is something else or "
             "past the object");
    }
  }

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
    // What counts as a shop's stock. Two silent mistakes to refuse: dropping the
    // body armour, which is a simple model sold beside the guns, and catching a
    // pickup's own visible object, which wears a weapon model info too.
    constexpr int kBodyArmour = 368;
    constexpr int kOtherModel = 401;
    Expect(IsShopStockObject(kModelInfoWeapon, 274, kBodyArmour,
                             kObjectTypeMission, false),
           "a gun on a rack is stock");
    Expect(IsShopStockObject(kModelInfoSimple, kBodyArmour, kBodyArmour,
                             kObjectTypeMission, false),
           "and so is the body armour beside it, by model rather than by kind");
    Expect(!IsShopStockObject(kModelInfoWeapon, 274, kBodyArmour,
                              kObjectTypeMission, true),
           "a pickup's own object is never stock, whatever it wears");
    Expect(!IsShopStockObject(kModelInfoSimple, kBodyArmour, kBodyArmour,
                              kObjectTypeMission, true),
           "including the body armour pickup");
    Expect(!IsShopStockObject(kModelInfoWeapon, 274, kBodyArmour, 1, false),
           "and neither is a map object, whatever it wears");
    Expect(!IsShopStockObject(kModelInfoSimple, kOtherModel, kBodyArmour,
                              kObjectTypeMission, false),
           "an ordinary script object is not stock either");

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
    const std::size_t ocean_beach = ContentDistrictSlot(kContentHiddenPackages, 0);
    const std::size_t vice_point = ContentDistrictSlot(kContentHiddenPackages, 2);
    std::array<int, kContentCount> flags{};
    flags[kContentHiddenPackages] = 1;
    ContentLocks held{};
    held[ocean_beach] = true;
    held[vice_point] = true;
    ContentLocks none{};

    // First observation on a new game: held, and silent.
    ContentReleasePlan plan = PlanContentReleases(held, flags, none, false);
    Expect(!plan.announce[ocean_beach],
           "the first observed frame is the baseline, not an announcement");
    Expect(plan.next_was_held[ocean_beach],
           "and it records the district as held");

    // One district's item lands: that district speaks, and the one still held
    // stays quiet. A split seed releases a class a district at a time, so an
    // announcement that spoke for the whole class would be a lie.
    ContentLocks ocean_released = held;
    ocean_released[ocean_beach] = false;
    plan = PlanContentReleases(ocean_released, flags, plan.next_was_held, true);
    Expect(plan.announce[ocean_beach], "the released district announces");
    Expect(!plan.announce[vice_point], "the one still held says nothing");
    plan = PlanContentReleases(ocean_released, flags, plan.next_was_held, true);
    Expect(!plan.announce[ocean_beach],
           "and never again while it stays released");

    // A save that already holds the item reads released at the first
    // observation, so it stays quiet.
    plan = PlanContentReleases(none, flags, held, false);
    Expect(!plan.announce[ocean_beach],
           "a save already carrying the item does not re-announce");

    // An unconfigured class never speaks, whatever the state does.
    std::array<int, kContentCount> unselected{};
    plan = PlanContentReleases(none, unselected, held, true);
    Expect(!plan.announce[ocean_beach],
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

  // The mainland routes. One item opening every crossing and one item per
  // crossing are the same reporting problem, so the world sends whichever it
  // made and this only renders it. A route with a second requirement is the
  // Starfish causeway, whose gate stands on the island: the item alone opens
  // nothing, and saying it did would send the player to a shut gate.
  {
    std::vector<MainlandRoute> routes = {
        MainlandRoute{9032, "Prawn Island Bridge", 0, ""},
        MainlandRoute{9035, "Starfish Island Causeway", 9031,
                      "Starfish Island Access"},
    };
    const std::vector<int> nothing = {0, 0};
    std::vector<RouteState> was;

    // First observation on a new game: silent, and the baseline recorded.
    RouteReportPlan plan =
        PlanRouteReports(routes, nothing, nothing, was, false);
    Expect(plan.announce.empty(),
           "the first observed frame is the baseline, not an announcement");
    Expect(plan.next_was.size() == 2 &&
               plan.next_was[0] == RouteState::kAbsent,
           "and it records both routes as absent");

    // A bridge item lands: its edge speaks once, and only for that bridge.
    plan = PlanRouteReports(routes, {1, 0}, nothing, plan.next_was, true);
    Expect(plan.announce.size() == 1 &&
               plan.announce[0] == "Prawn Island Bridge is open.",
           "an opened bridge announces itself on its edge");
    plan = PlanRouteReports(routes, {1, 0}, nothing, plan.next_was, true);
    Expect(plan.announce.empty(), "and never again while it stays open");

    // The causeway item lands without the island: it is not open, and the
    // announcement says what is still missing rather than claiming a route.
    plan = PlanRouteReports(routes, {1, 1}, {0, 0}, plan.next_was, true);
    Expect(plan.announce.size() == 1 &&
               plan.announce[0] ==
                   "Starfish Island Causeway needs Starfish Island Access.",
           "a route waiting on a second item says so");
    Expect(plan.next_was[1] == RouteState::kWaiting,
           "and records it as waiting, not open");

    // The island arrives: now it really is a route.
    plan = PlanRouteReports(routes, {1, 1}, {0, 1}, plan.next_was, true);
    Expect(plan.announce.size() == 1 &&
               plan.announce[0] == "Starfish Island Causeway is open.",
           "the waiting route opens once its second item lands");

    // A save already holding both reads open at its first observation, so it
    // stays quiet, the same rule the content classes follow.
    plan = PlanRouteReports(routes, {1, 1}, {0, 1}, was, false);
    Expect(plan.announce.empty(),
           "a save already carrying the routes does not re-announce");

    // Mismatched inputs are a caller error, not a crash: nothing is announced
    // and nothing is recorded, so a half-applied config cannot speak.
    plan = PlanRouteReports(routes, {1}, nothing, was, true);
    Expect(plan.announce.empty() && plan.next_was.empty(),
           "a route list out of step with its values reports nothing");
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
    // 226 of the frontend's units, and a row is 13 at the design size, so
    // seventeen lines is full size and anything up to about twenty-six is legible.
    StatusPanelState full = state;
    full.locks_known = true;
    for (int index = 0; index < kAbilityCount; ++index) full.ability_flags[index] = 1;
    for (int index = 0; index < kContentCount; ++index) {
      full.content_flags[index] = 1;
      full.content_districts_held[index] = 5;
      for (int district = 0; district < 5; ++district) {
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

  // Recovering the stunt jump table from a block of memory. The game builds it
  // on the heap and writes it nowhere else, so the search runs on what the table
  // is: world positions at a constant stride, spread across the city.
  {
    constexpr std::size_t kStride = 0x44;
    constexpr int kJumps = 36;
    constexpr std::size_t kLead = 0x120;

    // One record at a place in the city, laid out the way the manager lays it.
    const auto plant = [](std::vector<unsigned char>* into, std::size_t offset,
                          float x, float y, int reward) {
      const float floats[kStuntJumpFloats] = {
          x, y, 10.0f, x + 8.0f, y + 8.0f, 16.0f,
          x + 60.0f, y, 9.0f, x + 90.0f, y + 20.0f, 15.0f,
          x + 30.0f, y - 40.0f, 25.0f,
      };
      std::memcpy(into->data() + offset, floats, sizeof(floats));
      std::memcpy(into->data() + offset + sizeof(floats), &reward, sizeof(reward));
    };
    const auto plant_table = [&](std::vector<unsigned char>* into, std::size_t lead) {
      for (int index = 0; index < kJumps; ++index) {
        plant(into, lead + kStride * index, -900.0f + 40.0f * index,
              300.0f - 20.0f * index, 500 * (index + 1));
      }
    };

    std::vector<unsigned char> memory(kLead + kStride * (kJumps + 2), 0);
    plant_table(&memory, kLead);

    const std::vector<StuntJumpPosition> positions =
        FindStuntJumpPositions(memory.data(), memory.size());
    Expect(positions.size() >= static_cast<std::size_t>(kJumps),
           "every planted position is found");
    const std::vector<StuntJumpRun> runs = FindStuntJumpRuns(positions);
    // Each record holds five positions, so the array yields a run per alignment
    // and a run per straddle. What matters is that the true one is among them,
    // and that ranking picks it: only there do the floats form the manager's
    // own record.
    const StuntJumpRun* table = nullptr;
    for (const StuntJumpRun& run : runs) {
      if (run.offset == kLead && run.stride == kStride && run.count == kJumps) {
        table = &run;
      }
    }
    Expect(table != nullptr, "the planted table is among the qualifying runs");
    if (table != nullptr) {
      Expect(table->span >= kStuntJumpMinimumSpan, "the planted table spans the city");
      Expect(table->away_from_origin > 0.99f,
             "every planted position is away from the origin");
    }

    // Ranked as the caller ranks them, the true alignment comes first.
    {
      std::vector<StuntJumpCandidate> ranked;
      for (const StuntJumpRun& run : runs) {
        StuntJumpCandidate candidate;
        candidate.run = run;
        for (int step = 0; step < run.count; ++step) {
          candidate.records.push_back(
              ReadStuntJumpRecord(memory.data(), run.offset + run.stride * step));
        }
        candidate.layout_fit = LayoutFit(candidate.records);
        ranked.push_back(std::move(candidate));
      }
      std::stable_sort(ranked.begin(), ranked.end(),
                       [wanted = kJumps](const StuntJumpCandidate& left,
                                         const StuntJumpCandidate& right) {
                         return CandidateRanksBefore(left, right, wanted);
                       });
      Expect(!ranked.empty() && ranked.front().run.offset == kLead &&
                 ranked.front().run.stride == kStride,
             "ranking puts the true alignment first, not a straddling run");
    }

    // An array of one model's bounding volumes: real positions at a constant
    // stride, but around that model's own origin and reaching only a few dozen
    // units, so no run of it qualifies.
    {
      std::vector<unsigned char> model_bounds(kStride * 40, 0);
      for (int index = 0; index < 40; ++index) {
        plant(&model_bounds, kStride * index, 5.0f + static_cast<float>(index),
              -5.0f - static_cast<float>(index), 0);
      }
      const std::vector<StuntJumpPosition> bound_positions =
          FindStuntJumpPositions(model_bounds.data(), model_bounds.size());
      Expect(!bound_positions.empty(), "model bounds do read as positions");
      Expect(FindStuntJumpRuns(bound_positions).empty(),
             "an array of one model's bounds never qualifies as the table");
    }

    // A model-bounds array sharing a block with the table, at the lower address.
    // Both are 36 long, so a search offering one run per block would hand back
    // the decoy and the table would never be seen.
    {
      const std::size_t decoy_lead = 0x40;
      const std::size_t table_lead = decoy_lead + kStride * (kJumps + 2);
      std::vector<unsigned char> shared(table_lead + kStride * (kJumps + 2), 0);
      for (int index = 0; index < kJumps; ++index) {
        plant(&shared, decoy_lead + kStride * index, 6.0f + static_cast<float>(index),
              -6.0f - static_cast<float>(index), 0);
      }
      plant_table(&shared, table_lead);
      const std::vector<StuntJumpRun> shared_runs =
          FindStuntJumpRuns(FindStuntJumpPositions(shared.data(), shared.size()));
      bool found_table = false;
      bool found_decoy = false;
      for (const StuntJumpRun& run : shared_runs) {
        if (run.offset == table_lead && run.count == kJumps) found_table = true;
        if (run.offset == decoy_lead) found_decoy = true;
      }
      Expect(found_table, "the table is offered even behind a decoy at a lower address");
      Expect(!found_decoy, "the decoy sharing the block never qualifies");
    }

    // One jump beside the world origin does not cost the table its run: the
    // origin test is a share of the whole run, never a per-record reject.
    {
      std::vector<unsigned char> with_central(kLead + kStride * (kJumps + 2), 0);
      plant_table(&with_central, kLead);
      plant(&with_central, kLead, 12.0f, -6.0f, 500);
      const std::vector<StuntJumpRun> central_runs = FindStuntJumpRuns(
          FindStuntJumpPositions(with_central.data(), with_central.size()));
      bool intact = false;
      for (const StuntJumpRun& run : central_runs) {
        if (run.offset == kLead && run.count == kJumps && run.stride == kStride) {
          intact = true;
        }
      }
      Expect(intact, "a jump beside the origin leaves the run whole and aligned");
    }

    // A height nothing occupies, and one that is not a number, are both rejected.
    {
      const float in_the_city[3] = {-900.0f, 300.0f, 11.0f};
      Expect(LooksLikeWorldPosition(in_the_city), "a place in the city reads as one");
      const float too_high[3] = {-900.0f, 300.0f, 9000.0f};
      Expect(!LooksLikeWorldPosition(too_high), "nothing sits nine kilometres up");
      const float not_a_number[3] = {-900.0f, 300.0f,
                                     std::numeric_limits<float>::quiet_NaN()};
      Expect(!LooksLikeWorldPosition(not_a_number),
             "a height that is not a number is not a height");
    }

    // The known layout ranks a candidate up but never gates it, so it is read as
    // a share of the run rather than a verdict on it.
    {
      std::vector<StuntJumpRecord> records;
      for (int index = 0; index < kJumps; ++index) {
        records.push_back(ReadStuntJumpRecord(memory.data(), kLead + kStride * index));
      }
      Expect(LayoutFit(records) > 0.99f, "the planted table fits the known layout");
      records[0].reward = -1082130432;  // -1.0f
      Expect(LayoutFit(records) < 1.0f && LayoutFit(records) > 0.9f,
             "one odd record costs a little of the fit, not all of it");
    }

    // Ranking: the game's own count leads, then how well the layout fits.
    {
      StuntJumpCandidate matching;
      matching.run = StuntJumpRun{0x100, kStride, kJumps, 2000.0f, 1.0f};
      matching.layout_fit = 0.5f;
      StuntJumpCandidate longer;
      longer.run = StuntJumpRun{0x200, kStride, kJumps * 3, 4000.0f, 1.0f};
      longer.layout_fit = 1.0f;
      Expect(CandidateRanksBefore(longer, matching, kJumps),
             "the closer layout fit leads, whatever the counts");
      Expect(!CandidateRanksBefore(matching, longer, kJumps),
             "and the count alone does not lead it back");

      // A spatial grid holding exactly as many entries as the game reports,
      // reaching right across the map, and forming no jump record at all: the
      // count and the span both say table, only the fit says otherwise.
      StuntJumpCandidate grid;
      grid.run = StuntJumpRun{0x400, 360, kJumps, 3704.0f, 1.0f};
      grid.layout_fit = 0.0f;
      StuntJumpCandidate table;
      table.run = StuntJumpRun{0x500, kStride, kJumps, 2000.0f, 1.0f};
      table.layout_fit = 1.0f;
      Expect(CandidateRanksBefore(table, grid, kJumps),
             "a table of jumps leads a grid of the same length and wider reach");

      StuntJumpCandidate poorer_fit = table;
      poorer_fit.run.offset = 0x600;
      poorer_fit.layout_fit = 0.6f;
      Expect(CandidateRanksBefore(table, poorer_fit, kJumps),
             "among equal counts the closer layout fit leads");
    }

    // Nothing naming a position yields nothing, rather than a short run.
    {
      std::vector<unsigned char> empty(4096, 0);
      Expect(
          FindStuntJumpRuns(FindStuntJumpPositions(empty.data(), empty.size())).empty(),
          "zeroed memory holds no stunt jump table");
    }
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

  if (failures == 0) {
    std::cout << "OK: protocol self-test passed\n";
    return 0;
  }
  return 1;
}
