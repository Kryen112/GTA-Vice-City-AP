// Pure completion detection, free of any game headers so the console self-test
// can exercise it without plugin-sdk or the game.
//
// A location is newly checked when its completion global was zero at the moment
// this game started (so it is a real, declared, zero-initialized global) and
// now reads nonzero, and it has not been reported yet. A global that was
// already nonzero at the game's start is not a declared completion global: it
// reads leftover mission bytecode from an install whose main.scm did not
// reserve that index, so it is ignored. This keeps an incomplete or mismatched
// main.scm from reporting every location at once.
#pragma once

#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <vector>

namespace gtavc {

inline std::vector<std::int64_t> DetectCompletedLocations(
    const std::map<int, std::int64_t>& completion_watch,
    const std::map<int, int>& baseline,
    const std::map<int, int>& current,
    std::set<int>& reported) {
  std::vector<std::int64_t> completed;
  for (const auto& [global_index, location] : completion_watch) {
    if (reported.count(global_index)) continue;
    const auto baseline_it = baseline.find(global_index);
    if (baseline_it == baseline.end() || baseline_it->second != 0) continue;
    const auto current_it = current.find(global_index);
    if (current_it == current.end() || current_it->second == 0) continue;
    completed.push_back(location);
    reported.insert(global_index);
  }
  return completed;
}

// Whether this frame takes the completion baseline. A baseline is an answer
// about the globals the config names, and every global absent from one is
// skipped for the life of the game above, so an empty baseline is a permanent
// answer to a question nobody has asked yet. The welcome and the config are
// separate frames on the wire, so a game stamped in the window between them
// would report nothing at all for the rest of its life.
inline bool ShouldCaptureBaseline(bool already_captured, bool watch_empty) {
  return !already_captured && !watch_empty;
}

// The checks that leave for the server now, taken out of the queue. Holding
// while the player has no control is what keeps a check from arriving in the
// middle of a cutscene, on a frame the player could not have earned it.
//
// Holding costs a delay and never a check. The queue is not emptied, not
// trimmed and not dropped at a game boundary: a location is a permanent fact
// about the slot rather than about the game it was found in, and there is one
// game per seed, so sending a stale one costs nothing while dropping one
// costs it forever. DetectCompletedLocations writes the global into `reported`
// the moment it finds it and nothing ever takes it back out, so a check
// dropped here cannot be found a second time; and a save made with that
// global set hands the next game a baseline that reads it as never having
// been a completion global at all.
inline std::vector<std::int64_t> DrainChecks(
    std::vector<std::int64_t>& queued, bool held) {
  if (held) return {};
  std::vector<std::int64_t> leaving;
  leaving.swap(queued);
  return leaving;
}

// Puts back what a send could not deliver, which is what makes draining safe to
// undo. A location leaves the queue before it is on the wire, and detection
// cannot find it a second time: the reported set holds it for the life of the
// process, and once the player saves, its completion global folds into the next
// game's baseline and stops reading as a declared completion at all. So a
// failed send has to hand the locations back rather than drop them.
//
// They go in front of whatever arrived since, so the order the game found them
// in survives a dropped socket, and a location the queue already holds is not
// added twice, since a detection pass can run between the failure and the
// retry.
inline void RequeueChecks(std::vector<std::int64_t>& queued,
                          const std::vector<std::int64_t>& undelivered) {
  std::vector<std::int64_t> restored;
  restored.reserve(undelivered.size() + queued.size());
  for (const std::int64_t location : undelivered) {
    if (std::find(restored.begin(), restored.end(), location) == restored.end()) {
      restored.push_back(location);
    }
  }
  for (const std::int64_t location : queued) {
    if (std::find(restored.begin(), restored.end(), location) == restored.end()) {
      restored.push_back(location);
    }
  }
  queued.swap(restored);
}

}  // namespace gtavc
