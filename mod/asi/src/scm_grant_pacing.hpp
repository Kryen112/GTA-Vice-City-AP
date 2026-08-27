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
// kGrantsPerWindow inside ANY window of kGrantWindowMs, which at these numbers is
// sixteen over just under four seconds and then a short wait. The interval is the
// binding constraint almost always, since sixteen intervals fit inside one window,
// so what a backlog actually drains at is close to four a second.
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

// One grant every quarter second, sixteen to any five second window.
//
// THE WINDOW CAP IS THE NUMBER TO LOWER IF A STREAMING CRASH COMES BACK. The
// crash this pacer exists for was in a streaming routine, and streaming is the
// one thing here that is explicitly cross-frame, so a per-frame argument does not
// bound it. Sixteen inside four seconds is close to the ceiling the 2026-08-21
// note recorded as untested, now as the steady state rather than as a worst case.
constexpr unsigned int kGrantIntervalMs = 250;
constexpr unsigned int kGrantWindowMs = 5000;
constexpr int kGrantsPerWindow = 16;

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
  // The earliest received index of any item that counts toward this global,
  // which is what orders the raises: the player gets things in the order
  // Archipelago handed them over, not in the order the globals happen to be
  // numbered. Always at or below the index of every item needing this global, so
  // a global an early item needs is always swept before one only a later item
  // needs, which is what bounds how long a landing report can wait for the ones
  // that arrived before it.
  std::int64_t arrival_index = 0;
};

// Where the raise sweep left off: the key of the last global handed over. A pair
// rather than one number because the key is a pair, and the rotation needs a
// distinct total order to be finite. Global index breaks the tie, so the eleven
// district globals one content item releases are consecutive in the sweep and
// that item lands within one run of them rather than one per pass.
struct UnlockCursor {
  std::int64_t arrival_index = -1;
  int global_index = -1;
};

// Whether one key comes after another in the sweep.
inline bool UnlockKeyAfter(std::int64_t arrival_index, int global_index,
                           const UnlockCursor& cursor) {
  if (arrival_index != cursor.arrival_index) {
    return arrival_index > cursor.arrival_index;
  }
  return global_index > cursor.global_index;
}

// Whether one key comes before another, for picking the lowest pending.
inline bool UnlockKeyBefore(std::int64_t arrival_index, int global_index,
                            std::int64_t other_arrival, int other_global) {
  if (arrival_index != other_arrival) return arrival_index < other_arrival;
  return global_index < other_global;
}

// What a frame does to the unlock globals: every lowering, which is unpaced,
// and at most one raise, which costs a grant.
struct UnlockPlan {
  std::vector<std::pair<int, int>> to_lower;
  bool has_raise = false;
  int raise_index = 0;
  int raise_value = 0;
  // The arrival key of the chosen raise, so the caller sets its cursor from what
  // was selected rather than searching the observations for it again. It is also
  // what the caller weighs the next pending one-shot effect against, since both
  // kinds of grant are ordered by the same received index.
  std::int64_t raise_arrival_index = 0;
};

// THE SWEEP IS IN ARRIVAL ORDER, by (arrival_index, global_index), which is the
// order Archipelago handed the items over. Global numbering has nothing to do
// with when an item arrived, so sweeping by global index delivered an item list
// in an order unrelated to the one every other Archipelago surface shows, and
// the landing reports built on top of it either had to follow that order or wait
// for it. Twenty items whose globals run opposite to their arrival showed the
// player nothing for eleven seconds and then all twenty at once, because the
// report walk holds at the first item that has not landed and the item that
// arrived first was granted last.
//
// The raise still goes ROUND the table rather than always to the lowest key. A
// global that cannot hold its target, because something else in the game writes
// it every frame, would otherwise take every slot forever and stop every later
// unlock. Starting past the last one handed over bounds that to one wasted slot
// per pass. When nothing is left above it the pass is done and the next starts at
// the lowest pending key again, which is also what serves a single pending global
// that keeps needing the same raise.
//
// `observed` may be in any order, and the lowest and next-above-the-cursor
// candidates are both picked by comparison rather than by position: the caller
// keeps it in ascending global order so that reading a global is a search rather
// than a scan, and sorting it by key every frame would buy nothing. What is
// required is that no global appears twice, which is what lets the caller read
// every global before writing any of them (with a repeated index the second
// reading would have to see the first write) and what makes the key a distinct
// total order, so the rotation is finite.
inline UnlockPlan PlanUnlocks(const std::vector<UnlockObservation>& observed,
                              const UnlockCursor& cursor) {
  UnlockPlan plan;
  bool has_lowest = false;
  std::int64_t lowest_arrival = 0;
  int lowest_index = 0;
  int lowest_value = 0;
  bool has_next = false;
  std::int64_t next_arrival = 0;
  int next_index = 0;
  for (const UnlockObservation& entry : observed) {
    switch (PlanUnlock(entry.target, entry.current, entry.stamped)) {
      case UnlockAction::kLowerNow:
        plan.to_lower.push_back({entry.global_index, entry.target});
        break;
      case UnlockAction::kRaiseAsGrant:
        if (!has_lowest ||
            UnlockKeyBefore(entry.arrival_index, entry.global_index,
                            lowest_arrival, lowest_index)) {
          has_lowest = true;
          lowest_arrival = entry.arrival_index;
          lowest_index = entry.global_index;
          lowest_value = entry.target;
        }
        if (UnlockKeyAfter(entry.arrival_index, entry.global_index, cursor) &&
            (!has_next ||
             UnlockKeyBefore(entry.arrival_index, entry.global_index,
                             next_arrival, next_index))) {
          has_next = true;
          next_arrival = entry.arrival_index;
          next_index = entry.global_index;
          plan.has_raise = true;
          plan.raise_index = entry.global_index;
          plan.raise_value = entry.target;
          plan.raise_arrival_index = entry.arrival_index;
        }
        break;
      case UnlockAction::kNone:
        break;
    }
  }
  // Nothing left above the cursor ends the pass, and the next one starts at the
  // lowest pending key.
  if (!plan.has_raise && has_lowest) {
    plan.has_raise = true;
    plan.raise_index = lowest_index;
    plan.raise_value = lowest_value;
    plan.raise_arrival_index = lowest_arrival;
  }
  return plan;
}

// Everything the game says about whether the player is actually playing, read on
// the frame and answered by WorldIsPlayable below.
struct PlayableState {
  // The game hands the player control: not a cutscene, not a mission pass or fail
  // screen, not otherwise script-owned.
  bool controllable = false;
  // The game's own pause, either the player's or the code's.
  bool paused = false;
  // The frontend menu is up, which is its own state: the pause flags and the menu
  // are set by different things and a load from the menu reaches neither reliably.
  bool menu_open = false;
  // The player state is PLAYING rather than wasted, arrested or failed.
  bool player_playing = false;
  // Inside one of the game's interiors, which is where the shops are.
  bool in_interior = false;
  // The game is showing its help box, which is what a shop stand puts on screen
  // while the player stands at it.
  bool help_message_up = false;
};

// Whether a grant may leave and a landing may be reported at all.
//
// THIS IS A DEFERRAL LIST, which the framework invariant in CLAUDE.md forbade
// until it was amended for this. The reason the clause gives for forbidding one is
// that a second condition is where lost grants hide, and nothing here can lose a
// grant: every unlock target is re-read from the live globals on every frame and
// the one-shot applied-index lives in the save, so a condition that is false today
// costs a delay and never a delivery. That is why the amendment is safe, and it is
// also the property any further condition added here has to keep.
//
// What it does NOT gate is LOWERING. Taking an ability back stays immediate, since
// an ability left usable for as long as one of these states lasts is a hole rather
// than a nicety, which is the same reason lowering was never paced.
inline bool WorldIsPlayable(const PlayableState& state) {
  if (!state.controllable) return false;
  if (state.paused || state.menu_open) return false;
  if (!state.player_playing) return false;
  // A shop stand shows a help box while the player is standing at it, and the
  // stands are indoors. Both halves are needed: an interior on its own would hold
  // every indoor mission for as long as it lasted, and a help box on its own is
  // the channel every tutorial hint in the game uses.
  if (state.in_interior && state.help_message_up) return false;
  return true;
}

// Whether this frame's unlock raise gives up its grant slot to a one-shot effect.
//
// Both kinds of grant draw on one budget and both are ordered by the same received
// index, so the earlier arrival goes first. Without this the unlock path took
// every slot while ANY global was below its target, whatever their arrival order,
// and an effect early in the list waited out the whole unlock backlog. Nothing is
// lost by that in delivery, and everything is lost by it in the landing reports:
// they hold at the first item that has not landed, so an early effect held every
// row behind it for the length of the release and then let the run go at once.
//
// `player_exists` is what keeps a yield from wasting the frame: the effect path
// needs a player ped to write into, so yielding to an effect that cannot run would
// spend the slot on neither. The caller must also be somewhere the effect path
// will actually be reached this frame, which is why the one call site sits inside
// the controllable branch: PlanEffects returns nothing without control, and a
// yield to it there would be a yield to nothing.
inline bool RaiseYieldsToEffect(bool has_raise, std::int64_t raise_arrival_index,
                                bool effect_pending,
                                std::int64_t effect_arrival_index,
                                bool player_exists) {
  // No raise is not a yield: there is nothing to give up, and the effect path
  // takes the slot on its own.
  if (!has_raise) return false;
  if (!effect_pending || !player_exists) return false;
  return effect_arrival_index < raise_arrival_index;
}

// What a game hands to the next one: nothing. The pacer reads a clock the next
// game restarts, and the rotation cursor points into the sweep of the game that
// is over.
struct GameScopedGrants {
  GrantPacer pacer;
  UnlockCursor cursor;
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
