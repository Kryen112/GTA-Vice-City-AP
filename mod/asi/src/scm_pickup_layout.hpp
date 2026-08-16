// Pure ambient-pickup layout planning, free of any game headers so the
// console self-test can exercise it without plugin-sdk or the game.
//
// The randomize_pickups option permutes the ambient world pickups: the world
// ships a target layout (position, pickup type, model, ammo per slot) and the
// plan matches each target to the pickup pool by position and type, returning
// a rewrite for every matched entry whose model differs. Matching on the type
// keeps a script-removed slot dead (its type reads none until the script
// recreates it), and rewriting only on a model difference leaves the game's
// own quantity bookkeeping alone: ammo extraction zeroes a weapon pickup's
// quantity in place, and re-stamping it every frame would refill it.
#pragma once

#include <vector>

#include "game_state.hpp"

namespace gtavc {

// One in-use entry of the game's pickup pool, snapshotted for planning.
struct PickupPoolEntry {
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
  int pickup_type = 0;
  int model = 0;
  int pool_index = 0;
};

// A pool entry to rewrite to the layout's model and ammo.
struct PickupRewrite {
  int pool_index = 0;
  int model = 0;
  int quantity = 0;
};

// One frame of layout planning: the rewrites to apply, plus how many layout
// slots found no pool entry at all (left vanilla; the caller logs them once).
struct PickupLayoutPlan {
  std::vector<PickupRewrite> rewrites;
  int unmatched_targets = 0;
};

inline PickupLayoutPlan PlanPickupLayout(
    const std::vector<PickupTarget>& targets,
    const std::vector<PickupPoolEntry>& pool_entries) {
  // Within one unit (Euclidean) counts as the same slot. Two bounds keep a
  // match unambiguous: the extractor refuses a table whose slots sit closer
  // than 1.5 units (the nearest vanilla pair is 4.49 apart), and the nearest
  // same-type pickup OUTSIDE the table is 1.91 units from a slot (a mission
  // script places a body armor beside the Prawn Island heart), so the
  // tolerance must stay below that; 1.0 only absorbs float round-tripping.
  constexpr double kMatchDistanceSquared = 1.0;
  PickupLayoutPlan plan;
  for (const PickupTarget& target : targets) {
    bool matched = false;
    for (const PickupPoolEntry& entry : pool_entries) {
      if (entry.pickup_type != target.pickup_type) continue;
      const double delta_x = entry.x - target.x;
      const double delta_y = entry.y - target.y;
      const double delta_z = entry.z - target.z;
      const double distance_squared =
          delta_x * delta_x + delta_y * delta_y + delta_z * delta_z;
      if (distance_squared > kMatchDistanceSquared) continue;
      matched = true;
      if (entry.model != target.model) {
        plan.rewrites.push_back({entry.pool_index, target.model, target.quantity});
      }
      break;
    }
    if (!matched) ++plan.unmatched_targets;
  }
  return plan;
}

}  // namespace gtavc
