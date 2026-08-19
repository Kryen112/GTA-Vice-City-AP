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

// The game pays for hidden packages in the EXECUTABLE, not the script: the
// pickup code hands the player $100 for every package and another $100,000 as
// the count reaches the total, alongside the CO_ALL message. With the
// hidden-packages class on the AP check is the reward and its cash is mirrored
// back into the pool as filler, so the vanilla payout is taken back in the same
// frame it lands, before anything draws.
constexpr int kPackageCash = 100;
constexpr int kAllPackagesCash = 100000;

// What to take back, given how many packages the detection above just reported
// and the game's own live counters. Reads no remembered state, so a save loaded
// mid-session cannot look like a payment: the detection is what says a package
// was collected here and now, and it already refuses one whose completion global
// a save restored. The count before this frame is `collected` less what was just
// reported, and the bonus rides on the game's own condition, so a count already
// at the total pays nothing again. The claw-back never exceeds the money on hand,
// so a wallet the ability lock pins at nothing cannot go negative.
inline int PackageCashClawBack(int newly_collected, int collected, int total,
                               int money) {
  if (newly_collected <= 0) return 0;
  int amount = newly_collected * kPackageCash;
  const int before = collected - newly_collected;
  if (total > 0 && before < total && collected >= total) {
    amount += kAllPackagesCash;
  }
  const int available = money > 0 ? money : 0;
  return amount < available ? amount : available;
}

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
