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
#include <cstring>
#include <cstdio>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>
#include "emergency_progress.hpp"

namespace gtavc {

constexpr int kTaxiExtraCompletionBase = 9550;
constexpr int kRememberEmergencyGlobal = 10159;
constexpr int kEmergencyProgressBase = 10160;
constexpr int kVigilanteTimeRampGlobal = 10164;
constexpr int kVigilanteWantedRampGlobal = 10165;
constexpr int kTaxiSessionFaresGlobal = 6712;

inline std::optional<std::int64_t> CompletedDistributionCheck(
    bool income_complete, const std::map<int, std::int64_t>& watch, std::set<int>& reported) {
  const auto location = watch.find(9386);
  if (!income_complete || location == watch.end() || !reported.insert(9386).second) return std::nullopt;
  return location->second;
}

inline int MalibuEntranceLock(int vanilla_lock, int death_row_unlock, int death_row_passed) {
  // CELL can deliver its Death Row call after AP has already completed the mission.
  // Its $996 lock must not outlive that mission or wait on an unavailable AP item.
  return vanilla_lock && death_row_unlock > 0 && death_row_passed == 0;
}

inline bool IncreaseCountdown(unsigned int variable, unsigned char direction,
                              int* globals, std::size_t count) {
  if (variable == 0 || variable % sizeof(int) != 0 || variable / sizeof(int) >= count || direction == 0)
    return false;
  int& remaining = globals[variable / sizeof(int)];
  constexpr int extra = 60000;
  if (remaining <= 0 || remaining > std::numeric_limits<int>::max() - extra) return false;
  remaining += extra;
  return true;
}

inline bool SyncTaxiCounter(unsigned int variable, const char* key, bool enabled,
                            int fares, char (&text)[40]) {
  if (!enabled || variable != kTaxiSessionFaresGlobal * sizeof(int) ||
      std::strncmp(key, "FARES", 6) != 0) return false;
  std::snprintf(text, sizeof(text), "%d", std::max(0, fares));
  return true;
}

inline int TaxiCompletionGlobal(int milestone) {
  return milestone <= 10 ? 9308 + milestone : kTaxiExtraCompletionBase + milestone - 11;
}

inline int RestoredTaxiFares(const std::map<int, std::int64_t>& completion_watch,
                            const std::set<int>& reported, int spacing, int current) {
  if (spacing < 1 || spacing > 100) spacing = 10;
  for (int milestone = 100; milestone >= 1; --milestone) {
    const int global = TaxiCompletionGlobal(milestone);
    if (completion_watch.count(global) && reported.count(global))
      return std::max(current, milestone * spacing);
  }
  return current;
}

inline EmergencyProgress CheckedEmergencyProgress(
    const std::map<int, std::int64_t>& completion_watch, const std::set<int>& reported, int spacing) {
  EmergencyProgress progress{RestoredTaxiFares(completion_watch, reported, spacing, 0)};
  const int first[] = {9273, 9297, 9285, 9319};
  for (int activity = 0; activity < 4; ++activity) {
    for (int level = activity == 3 ? 10 : 12; level >= 1; --level) {
      const int global = first[activity] + level - 1;
      if (!completion_watch.count(global) || !reported.count(global)) continue;
      progress[activity + 1] = level;
      break;
    }
  }
  return progress;
}

template <typename Read, typename Write>
void RestoreEmergencyLevels(const EmergencyProgress& progress, Read read, Write write) {
  if (read(kRememberEmergencyGlobal) != 1) return;
  // Supply the SCM's resume counters from AP progress without changing an active mission.
  for (int activity = 0; activity < 4; ++activity) {
    const int level = progress[activity + 1];
    if (level <= 0) continue;
    const int stored = kEmergencyProgressBase + activity;
    int resume = activity == 2 ? level : level + 1;
    if (activity == 0) resume = std::min(resume, 12);
    if (activity == 3) resume = std::min(resume, 10);
    if (resume <= read(stored)) continue;
    write(stored, resume);
    if (activity == 2) {
      // Vanilla starts at 4.0/1.0 and reduces these after each completed level.
      const float time = 4.0f - 0.1f * std::min(level, 13);
      const float wanted = 1.0f - 0.05f * std::min(level, 12);
      int bits;
      std::memcpy(&bits, &time, sizeof(bits));
      write(kVigilanteTimeRampGlobal, bits);
      std::memcpy(&bits, &wanted, sizeof(bits));
      write(kVigilanteWantedRampGlobal, bits);
    }
  }
}

// Completed/total checks: firefighter, taxi, paramedic, vigilante, pizza.
inline std::array<std::pair<int, int>, 5> EmergencyCheckCounts(
    const std::map<int, std::int64_t>& completion_watch, const std::set<int>& reported) {
  // Completion ranges match scm.py; only checks enabled in this seed count.
  const struct { char label; int first; int count; } activities[] = {
      {'F', 9297, 12}, {'T', 9309, 100}, {'A', 9273, 12}, {'V', 9285, 12}, {'P', 9319, 10}};
  std::array<std::pair<int, int>, 5> counts{};
  for (std::size_t activity_index = 0; activity_index < counts.size(); ++activity_index) {
    const auto& activity = activities[activity_index];
    auto& [done, total] = counts[activity_index];
    for (int index = 0; index < activity.count; ++index) {
      const int global = activity.label == 'T' ? TaxiCompletionGlobal(index + 1) : activity.first + index;
      if (!completion_watch.count(global)) continue;
      ++total;
      if (reported.count(global)) ++done;
    }
  }
  return counts;
}

inline std::string EmergencyCheckProgress(
    const std::map<int, std::int64_t>& completion_watch, const std::set<int>& reported) {
  const auto counts = EmergencyCheckCounts(completion_watch, reported);
  std::string text;
  // Alphabetical HUD order: ambulance, firefighter, pizza, taxi, vigilante.
  for (const int activity : {2, 0, 4, 1, 3}) {
    const auto [done, total] = counts[activity];
    if (done == total) continue;
    if (!text.empty()) text += " ";
    text += "FTAVP"[activity];
    text += ':' + std::to_string(done) + '/' + std::to_string(total);
  }
  return text;
}

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
