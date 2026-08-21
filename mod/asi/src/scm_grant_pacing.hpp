// Pure grant delivery, free of any game headers so the console self-test can
// exercise it without plugin-sdk or the game: the rate grants leave at, which
// unlock global goes next, and what a game boundary takes with it.
//
// A grant is one thing the game reacts to: an unlock global taking a new value,
// or a one-shot effect running. Delivered all at once they take the game down.
// A hundred items arriving together means a hundred script watchers firing in
// one frame, package rewards spawning vehicles whose models stream in on the
// spot, and weapons doing a blocking load each. So grants leave here at a rate
// the game survives rather than the rate the server sends them at.
//
// The rate is one grant every kGrantIntervalMs and never more than
// kGrantsPerWindow inside ANY window of kGrantWindowMs, which is a burst of
// eight over two seconds and then a pause.
//
// The window SLIDES: each grant's time is remembered and a grant is refused
// while kGrantsPerWindow of them are less than kGrantWindowMs old, so the cap
// holds across any five seconds you care to pick rather than only inside the
// window the pacer happens to be anchored on. An earlier version anchored the
// window and cleared it whole, which let kGrantsPerWindow * 2 - 1 grants fall in
// one span, fifteen at these numbers, because the quota refilled at the
// boundary. The interval was the only hard cap then. A caller asking once a
// frame still gets at most one a frame.
//
// PlanUnlocks below picks which unlock global goes next. Which EFFECT goes
// next is the caller's own received order. The caller holds the pacer across
// frames.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <utility>
#include <vector>

namespace gtavc {

// One grant every quarter second, eight to any five second window.
constexpr unsigned int kGrantIntervalMs = 250;
constexpr unsigned int kGrantWindowMs = 5000;
constexpr int kGrantsPerWindow = 8;

// The sliding window remembers one time per grant it can admit, so it needs a
// slot for each. Sized from the cap rather than beside it, and TakeGrantSlot
// clamps a caller asking for more, which keeps a test free to pass a smaller
// per_window without the ring having to know.
constexpr std::size_t kGrantWindowSlots = static_cast<std::size_t>(kGrantsPerWindow);

// What the pacer carries between frames. The caller owns one. `times` is a ring
// of the grants inside the current window, oldest at `oldest`, `held` of them
// live; a grant ages out when it is kGrantWindowMs old rather than when a window
// ends.
struct GrantPacer {
  unsigned int next_allowed_ms = 0;
  std::array<unsigned int, kGrantWindowSlots> times{};
  std::size_t oldest = 0;
  int held = 0;
  bool started = false;
};

// True when one grant may go now, counting it against the interval and the
// window. Ask only when there is a grant waiting: a slot taken with nothing to
// deliver still spends the interval.
//
// Every comparison is on a signed difference, so the clock wrapping past its
// range costs at most one interval rather than stalling until it wraps again.
inline bool TakeGrantSlot(GrantPacer& pacer, unsigned int now,
                          unsigned int interval_ms, unsigned int window_ms,
                          int per_window) {
  if (per_window <= 0) return false;
  if (per_window > static_cast<int>(kGrantWindowSlots)) {
    per_window = static_cast<int>(kGrantWindowSlots);
  }
  // A clock that has gone backwards is a clock that restarted, which a game
  // restart does. Every time in the ring is a `now` this pacer was already
  // handed, so a `now` below the oldest of them means a restart or, harmlessly,
  // a gap of more than 24.8 days between asks. Catching it here rather than at a
  // call site is what reaches the loads no caller can watch: a load from the
  // pause menu runs the whole restart inside a window where the game frame does
  // not fire at all.
  //
  // It catches only the restarts that land below the oldest time held. One
  // landing above it runs on the previous game's times, which can only
  // under-grant and never over-grant, and those times age out within one window
  // of it, so an undetected restart costs a few seconds of extra wait, never a
  // stall and never a flood.
  if (pacer.started && pacer.held > 0 &&
      static_cast<int>(now - pacer.times[pacer.oldest]) < 0) {
    pacer.started = false;
  }
  if (!pacer.started) {
    pacer.started = true;
    pacer.next_allowed_ms = now;
    pacer.oldest = 0;
    pacer.held = 0;
  }
  if (static_cast<int>(now - pacer.next_allowed_ms) < 0) return false;
  // Age out every grant the window has left behind. This is what makes the cap
  // hold across any window_ms rather than only inside an anchored one: nothing
  // is cleared wholesale, each time leaves on its own.
  while (pacer.held > 0 &&
         static_cast<int>(now - pacer.times[pacer.oldest]) >=
             static_cast<int>(window_ms)) {
    pacer.oldest = (pacer.oldest + 1) % kGrantWindowSlots;
    --pacer.held;
  }
  if (pacer.held >= per_window) return false;
  pacer.times[(pacer.oldest + static_cast<std::size_t>(pacer.held)) %
              kGrantWindowSlots] = now;
  ++pacer.held;
  pacer.next_allowed_ms = now + interval_ms;
  return true;
}

// What one unlock global needs this frame.
enum class UnlockAction {
  kNone,
  // Write the target now. Taking something back is never paced: the target
  // drops to undo what a stale save restored, and an ability left usable for
  // the seconds a pace would cost is a hole rather than a nicety.
  kLowerNow,
  // Write the target as this frame's grant, if the pacer allows one.
  kRaiseAsGrant,
};

// The action for one global, from its target and what the game currently holds.
// Reading the game rather than remembering what was written is what makes this
// self-healing: a global the game or a script clears afterwards reads below its
// target again and is handed over again, and a save loaded mid-session brings
// its own values with it and is answered against those.
//
// `stamped` marks a global the config flags own, written every frame from
// slot_data. Those belong to the stamp and this leaves them alone.
inline UnlockAction PlanUnlock(int target, int current, bool stamped) {
  // A stamped global is the stamp's in both directions. Lowering one fights
  // the stamp, and so does raising one: the stamp rewrites it later in the
  // same frame, before any script sees it, so the raise never takes and the
  // grant slot it spent is spent again next interval, forever, ahead of every
  // other unlock and every effect. This fires in every seed rather than
  // guarding against a case that cannot happen: the tally zeroes all eleven
  // districts of every content class, and the config flags stamp at least the
  // class-district pairs no item covers, so the two sets always overlap. The
  // stamped value is never below the tally's target, so no real raise is lost.
  if (stamped) return UnlockAction::kNone;
  if (target > current) return UnlockAction::kRaiseAsGrant;
  if (target < current) return UnlockAction::kLowerNow;
  return UnlockAction::kNone;
}

// One unlock global as this frame finds it.
struct UnlockObservation {
  int global_index = 0;
  int target = 0;
  int current = 0;
  bool stamped = false;
};

// What a frame does to the unlock globals: every lowering, which is unpaced,
// and at most one raise, which costs a grant.
struct UnlockPlan {
  std::vector<std::pair<int, int>> to_lower;
  bool has_raise = false;
  int raise_index = 0;
  int raise_value = 0;
};

// The raise goes round the table rather than always to the lowest index. A
// global that cannot hold its target, because something else in the game
// writes it every frame, would otherwise take every slot forever and stop
// every later unlock. Starting past the last one handed over bounds that to
// one wasted slot per pass. When nothing is left above it the pass is done and
// the next starts at the lowest pending global again, which is also what
// serves a single pending global that keeps needing the same raise.
//
// `observed` is expected in ascending global order with no index twice.
// Ascending is what makes the rotation stable and the pass finite. Distinct is
// what lets the caller read every global before writing any of them: with a
// repeated index the second reading would have to see the first write.
inline UnlockPlan PlanUnlocks(const std::vector<UnlockObservation>& observed,
                              int last_raised_index) {
  UnlockPlan plan;
  bool has_first = false;
  int first_index = 0;
  int first_value = 0;
  for (const UnlockObservation& entry : observed) {
    switch (PlanUnlock(entry.target, entry.current, entry.stamped)) {
      case UnlockAction::kLowerNow:
        plan.to_lower.push_back({entry.global_index, entry.target});
        break;
      case UnlockAction::kRaiseAsGrant:
        if (!has_first) {
          has_first = true;
          first_index = entry.global_index;
          first_value = entry.target;
        }
        if (!plan.has_raise && entry.global_index > last_raised_index) {
          plan.has_raise = true;
          plan.raise_index = entry.global_index;
          plan.raise_value = entry.target;
        }
        break;
      case UnlockAction::kNone:
        break;
    }
  }
  if (!plan.has_raise && has_first) {
    plan.has_raise = true;
    plan.raise_index = first_index;
    plan.raise_value = first_value;
  }
  return plan;
}

// What a game hands to the next one: nothing. The pacer reads a clock the next
// game restarts, and the rotation cursor counted globals in the game that is
// over.
struct GameScopedGrants {
  GrantPacer pacer;
  int last_raised_index = -1;
};

// Reset at a game boundary. The outbound check queue is passed in precisely so
// that this is the one place a boundary could drop it, and it does not: a
// location is a permanent fact about the slot rather than about the game it
// was found in, and a check dropped here can never be found again, because
// DetectCompletedLocations has already written its global into `reported` and
// nothing ever takes it back out.
inline void ResetGrantsForNewGame(
    GameScopedGrants& grants,
    const std::vector<std::int64_t>& outbound_checks) {
  (void)outbound_checks;
  grants = GameScopedGrants{};
}

}  // namespace gtavc
