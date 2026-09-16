#pragma once
#include <cstddef>
#include <cstring>

namespace gtavc {
constexpr int kPolePositionChargeGlobal = 10171;

// Change only int8 operands in the existing interior thread. Keeping every
// instruction's size preserves saved script instruction pointers and branches.
inline bool PatchPolePositionCharge(unsigned char* script, std::size_t size, int charge) {
  if (charge < 1 || charge > 100) return false;
  const unsigned char spend[] = {
      0x09, 0x01, 0x02, 0x08, 0x00, 0x04, 0xFB, // add_score $player_char -5
      0x06, 0x00, 0x03, 0x10, 0x00, 0x04, 0x00, // TIMERA = 0
      0x08, 0x00, 0x02, 0xF8, 0x10, 0x04, 0x05, // $1086 += 5
      0x08, 0x00, 0x02, 0xFC, 0x10, 0x04, 0x01}; // $1087 += 1
  const unsigned char affordability[] = {0x0A, 0x01, 0x02, 0x08, 0x00, 0x04};
  std::size_t found = 0;
  for (std::size_t i = 75; i + sizeof(spend) <= size; ++i) {
    if (std::memcmp(script + i, spend, 6) ||
        std::memcmp(script + i + 7, spend + 7, 13) ||
        std::memcmp(script + i + 21, spend + 21, 7) ||
        std::memcmp(script + i - 75, affordability, sizeof(affordability))) continue;
    const int previous = script[i + 20];
    if (previous < 1 || previous > 100 || script[i + 6] != static_cast<unsigned char>(-previous) ||
        script[i - 69] != previous) continue;
    if (found) return false; // Ambiguous script: change nothing.
    found = i;
  }
  if (!found) return false;
  script[found - 69] = static_cast<unsigned char>(charge);
  script[found + 6] = static_cast<unsigned char>(-charge);
  script[found + 20] = static_cast<unsigned char>(charge);
  return true;
}
}
