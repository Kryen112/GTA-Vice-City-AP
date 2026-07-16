// Pure hidden-package detection, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// The game reports only a running count of collected packages, never which one,
// so the ASI matches the collectable pickups still present in the pool to each
// package by coordinate. A package seen present this game and then gone was
// collected. The persistent SCM completion global is the record that a package
// is already collected, in this session or restored from a save, so a package
// already recorded never reports again and one never seen present (an unplaced
// pool on a fresh game, or a save loaded with it already gone) is not treated
// as collected.
#pragma once

#include <set>
#include <vector>

#include "game_state.hpp"

namespace gtavc {

// A collectable pickup position read from the game's pool.
struct WorldPoint {
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
};

inline std::vector<int> DetectNewlyCollectedPackages(
    const std::vector<PackageLocation>& packages,
    const std::vector<WorldPoint>& present_positions,
    std::set<int>& seen_present,
    const std::set<int>& already_collected) {
  // Within two units (Euclidean) counts as the same package; the SCM places
  // each collectable at exactly its configured coordinate, so the tolerance
  // only absorbs float noise.
  constexpr float kMatchDistanceSquared = 4.0f;
  std::vector<int> newly_collected;
  for (const PackageLocation& package : packages) {
    bool here = false;
    for (const WorldPoint& position : present_positions) {
      const float delta_x = position.x - package.x;
      const float delta_y = position.y - package.y;
      const float delta_z = position.z - package.z;
      const float distance_squared =
          delta_x * delta_x + delta_y * delta_y + delta_z * delta_z;
      if (distance_squared <= kMatchDistanceSquared) {
        here = true;
        break;
      }
    }
    if (here) {
      seen_present.insert(package.completion_global);
    } else if (seen_present.count(package.completion_global) != 0 &&
               already_collected.count(package.completion_global) == 0) {
      newly_collected.push_back(package.completion_global);
    }
  }
  return newly_collected;
}

}  // namespace gtavc
