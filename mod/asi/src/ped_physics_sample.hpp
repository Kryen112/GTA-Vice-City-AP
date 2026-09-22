#pragma once

#include <array>
#include <cstdint>
#include <cstring>

namespace gtavc {

struct PedPhysicsSample {
  std::array<float, 6> values{}; // position XYZ, then velocity XYZ

  bool IsFinite() const {
    for (const float& value : values) {
      std::uint32_t bits;
      std::memcpy(&bits, &value, sizeof(bits));
      if ((bits & 0x7f800000u) == 0x7f800000u) return false;
    }
    return true;
  }
};

} // namespace gtavc
