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

// How many effects one frame applies. One, because an effect can do work the
// game expects to own a frame by itself: a weapon streams its model in with a
// blocking load, and several of those in one frame stall it. One a frame is
// the ceiling; what a backlog actually arrives at is whatever the caller's
// grant pacing allows, which is slower again.
//
// The cap is what a frame costs, whatever the backlog behind it. The index the
// caller saves is a script global, which reaches disk only when the player
// saves, so a crash resumes from the last saved index and not from the last
// applied effect: an effect that faults every time it runs is not something
// the index can step over.
constexpr int kEffectsPerFrame = 1;

// The next one-shot effect waiting to be applied, as its position in the received
// item list. Unlock raises and effects draw on the same grant budget, so the frame
// weighs one against the other, and this is the effect side's key: the same
// received index the unlock side sorts by.
//
// Without it the unlock path took every slot while any global was below its
// target, whatever their arrival order, and an effect early in the list waited
// out the whole unlock backlog. That is invisible in delivery, since nothing is
// lost either way, and loud in the landing reports: they hold at the first item
// that has not landed, so an early effect held every row behind it for the length
// of the release and then let the whole run go at once.
struct NextEffect {
  bool pending = false;
  std::int64_t received_index = 0;
};

// The caller must be somewhere the effect path is reached this frame, which today
// means inside the controllable branch: PlanEffects returns nothing without
// control, so "pending" there would hand a slot to a plan that comes back empty.
// This takes no controllable flag of its own precisely so the two cannot disagree
// about what the saved index means.
inline NextEffect NextPendingEffect(
    const std::vector<std::pair<std::int64_t, std::int64_t>>& items,
    const std::map<std::int64_t, ItemEffect>& item_effects, int applied_index) {
  int effect_position = 0;
  for (const auto& [received_index, item_id] : items) {
    if (item_effects.find(item_id) == item_effects.end()) continue;
    if (effect_position >= applied_index) return {true, received_index};
    ++effect_position;
  }
  return {};
}

inline EffectPlan PlanEffects(
    const std::vector<std::pair<std::int64_t, std::int64_t>>& items,
    const std::map<std::int64_t, ItemEffect>& item_effects,
    int applied_index, bool controllable, int max_per_frame) {
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
    // A frame with no room left applies nothing and holds the index where it
    // is, so the rest keep their place in the list and arrive on the frames
    // after this one, in the same received order.
    if (static_cast<int>(plan.to_apply.size()) >= max_per_frame) break;
    plan.to_apply.push_back(it->second);
    ++effect_index;
    plan.new_applied_index = effect_index;
  }
  return plan;
}

}  // namespace gtavc
