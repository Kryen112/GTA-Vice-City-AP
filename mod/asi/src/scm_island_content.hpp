#pragma once

#include "scm_content_locks.hpp"
#include "scm_crossings.hpp"

namespace gtavc {

constexpr int kIslandContentLocksGlobal = 10172;
constexpr int kIslandContentAccessGlobal = 10173;
constexpr int kPlayerIslandContentAccessGlobal = 10174;
constexpr int kStarfishAccessGlobal = 9031;
constexpr int kAllHandsPassedGlobal = 9067;
constexpr int kMainlandContentBit = 1;
constexpr int kStarfishContentBit = 2;

// Match data.region_access_groups, including its air and sea routes to Starfish.
template <typename ReadGlobal>
int IslandContentAccess(const std::vector<MainlandRoute>& routes,
                        const AbilityLocks& locked, ReadGlobal read) {
  if (read(kIslandContentLocksGlobal) == 0) return 3;
  bool mainland = false;
  for (const auto& route : routes) {
    if (route.unlock_global == kStarfishAccessGlobal) continue;
    mainland = mainland || RouteStateOf(route, read(route.unlock_global),
        route.needs_global == 0 ? 0 : read(route.needs_global)) == RouteState::kOpen;
  }
  const bool starfish = read(kStarfishAccessGlobal) > 0 ||
      (mainland && !locked[kAbilityAirVehicles]) ||
      (read(kAllHandsPassedGlobal) > 0 && !locked[kAbilitySeaVehicles]);
  return (mainland ? kMainlandContentBit : 0) | (starfish ? kStarfishContentBit : 0);
}

inline int DistrictIslandBit(int district) {
  if (district == 3) return kStarfishContentBit;
  return district >= 6 && district < kDistrictCount ? kMainlandContentBit : 0;
}

inline bool IslandContentAllowed(int access, int island_bit) {
  return island_bit == 0 || (access & island_bit) != 0;
}

inline ContentLocks HoldIslandContent(ContentLocks held, int access) {
  for (int content = 0; content < kContentCount; ++content) {
    for (int district = 0; district < kDistrictCount; ++district) {
      if (!IslandContentAllowed(access, DistrictIslandBit(district)))
        held[ContentDistrictSlot(content, district)] = true;
    }
  }
  return held;
}

}  // namespace gtavc
