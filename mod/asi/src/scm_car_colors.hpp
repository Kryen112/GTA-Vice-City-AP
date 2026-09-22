#pragma once

#include <array>
#include <cstdint>
#include <random>
#include <string_view>

namespace gtavc {

using VehicleColor = std::array<unsigned char, 3>;

inline std::array<VehicleColor, 95> RandomVehiclePalette(std::string_view seed_text) {
  std::uint32_t seed = 2166136261u;
  for (const unsigned char character : seed_text)
    seed = (seed ^ character) * 16777619u;

  std::minstd_rand random(seed);
  std::array<VehicleColor, 95> palette{};
  for (auto& color : palette)
    for (auto& channel : color) channel = static_cast<unsigned char>(random() & 0xFF);
  return palette;
}

}  // namespace gtavc
