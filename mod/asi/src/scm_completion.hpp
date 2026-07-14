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

}  // namespace gtavc
