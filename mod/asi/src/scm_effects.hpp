// Pure one-shot effect planning, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// One-shot effects (consumables and traps) apply once, in received order, past
// the saved applied-index. No effect applies while the player is not
// controllable, the single deferral condition the design allows: before
// control a script still owns the world (the new-game intro, a cutscene), so
// anything given there can be silently undone by it. While the player is not
// controllable the plan is empty and the applied-index holds, so every pending
// effect is retried on a later frame once control arrives. The caller
// guarantees the player exists before applying anything the plan returns.
#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include "game_state.hpp"

namespace gtavc {

// The effects to apply this frame and the resulting applied index.
struct EffectPlan {
  std::vector<ItemEffect> to_apply;
  int new_applied_index = 0;
};

inline EffectPlan PlanEffects(
    const std::vector<std::pair<std::int64_t, std::int64_t>>& items,
    const std::map<std::int64_t, ItemEffect>& item_effects,
    int applied_index, bool controllable) {
  EffectPlan plan;
  plan.new_applied_index = applied_index;
  // Without control nothing applies and the index holds, so no effect is
  // ever skipped; the whole list is retried once the player is controllable.
  if (!controllable) return plan;
  int effect_index = 0;
  for (const auto& [received_index, item_id] : items) {
    const auto it = item_effects.find(item_id);
    if (it == item_effects.end()) continue;
    // Effects before the saved index are already applied; count past them.
    if (effect_index < applied_index) {
      ++effect_index;
      continue;
    }
    plan.to_apply.push_back(it->second);
    ++effect_index;
    plan.new_applied_index = effect_index;
  }
  return plan;
}

}  // namespace gtavc
