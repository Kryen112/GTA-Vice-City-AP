// Pure one-shot effect planning, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// One-shot effects (consumables and traps) apply once, in received order, past
// the saved applied-index. The one wrinkle traps add is deferral: a chaos trap
// only fires while the player is controllable, the single deferral the design
// allows. Stormy weather is exempt (it applies any time), and the consumables
// are never traps, so they never defer. Planning stops at the first effect that
// must wait, so the applied-index never skips past a deferred trap; that effect
// is retried on a later frame once the player is controllable. The caller
// guarantees the player exists before applying anything the plan returns.
#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include "game_state.hpp"

namespace gtavc {

// A trap that reaches into the world defers until the player is controllable.
// Weather is exempt, and any non-trap effect (a consumable) never defers.
inline bool EffectDefersUntilControllable(const std::string& type) {
  return type.rfind("trap_", 0) == 0 && type != "trap_weather";
}

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
  int effect_index = 0;
  for (const auto& [received_index, item_id] : items) {
    const auto it = item_effects.find(item_id);
    if (it == item_effects.end()) continue;
    // Effects before the saved index are already applied; count past them.
    if (effect_index < applied_index) {
      ++effect_index;
      continue;
    }
    // The next unapplied effect. If it must wait for control, stop here so the
    // index does not advance past it, and try again on a later frame.
    if (EffectDefersUntilControllable(it->second.type) && !controllable) break;
    plan.to_apply.push_back(it->second);
    ++effect_index;
    plan.new_applied_index = effect_index;
  }
  return plan;
}

}  // namespace gtavc
