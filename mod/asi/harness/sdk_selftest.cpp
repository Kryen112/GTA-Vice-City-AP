// Link the built SDK without a game process: array bindings must not read game memory.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <CPickups.h>

int main() {
  assert(reinterpret_cast<std::uintptr_t>(&CPickups::aPickUps) == 0x945D30);
  assert(reinterpret_cast<std::uintptr_t>(&CPickups::aPickUpsCollected) == 0x94AF48);
  assert(reinterpret_cast<std::uintptr_t>(&CPickups::aMessages) == 0x7E9B08);
  std::puts("SDK pickup array bindings passed");
}
