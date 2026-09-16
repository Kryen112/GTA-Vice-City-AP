#pragma once

#include <algorithm>
#include <array>

namespace gtavc {

// Completed taxi fares, paramedic levels, firefighter levels, vigilante levels, pizza levels.
using EmergencyProgress = std::array<int, 5>;
inline constexpr std::array<const char*, 5> kEmergencyActivityNames = {
    "taxi", "paramedic", "firefighter", "vigilante", "pizza"};

inline void MergeEmergencyProgress(EmergencyProgress& current, const EmergencyProgress& incoming) {
  for (std::size_t index = 0; index < current.size(); ++index)
    current[index] = std::max(current[index], incoming[index]);
}

}  // namespace gtavc
