#pragma once

class CEntity;

namespace gtavc {
// Classic VC's eight water-creature slots. Entity references are cleared by
// CEntity::ResolveReferences when streaming or a restart deletes their objects.
struct WaterCreature {
  CEntity* object;
  float speed, turn;
  int alpha;
  float target_speed;
  int state;
};
static_assert(sizeof(WaterCreature) == 24);

inline void RetireDeletedWaterCreatures(WaterCreature (&creatures)[8], int& count) {
  for (auto& creature : creatures) {
    if (creature.object == nullptr && creature.state != 4) {
      creature = {};
      creature.state = 4;
      if (count > 0) --count;
    }
  }
}
}  // namespace gtavc
