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
#include <cstring>
#include <vector>

#include "game_state.hpp"

namespace gtavc {

// A collectable pickup position read from the game's pool.
struct WorldPoint {
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
};

inline bool PackageMatchesPosition(const PackageLocation& package, const WorldPoint& position) {
  // SCM places packages at their configured coordinates; allow the same
  // two-unit float tolerance for both detection and save reconciliation.
  const float x = position.x - package.x;
  const float y = position.y - package.y;
  const float z = position.z - package.z;
  return x * x + y * y + z * z <= 4.0f;
}

// Server-confirmed checks survive loading an older save. Local flags include
// a package collected this frame, before its check reaches the server.
template <typename ReadGlobal>
int CheckedPackageCount(const std::vector<PackageLocation>& packages,
                        const std::set<int>& reported, ReadGlobal read) {
  int count = 0;
  for (const auto& package : packages)
    if (reported.count(package.completion_global) || read(package.completion_global) != 0) ++count;
  return count;
}

// Only the package message uses the seed tally; garage and mission messages
// share this buffer. Leave their text, numbers and display timers alone.
inline void SyncPackageMessage(char* key, int& number, int& total, int checked, int package_total) {
  if (std::memcmp(key, "CO_ONE", 7) != 0 && std::memcmp(key, "CO_ALL", 7) != 0) return;
  std::memcpy(key, "CO_ONE", 7);
  number = checked;
  total = package_total;
}

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
  std::vector<int> newly_collected;
  for (const PackageLocation& package : packages) {
    bool here = false;
    for (const WorldPoint& position : present_positions) {
      if (PackageMatchesPosition(package, position)) {
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
