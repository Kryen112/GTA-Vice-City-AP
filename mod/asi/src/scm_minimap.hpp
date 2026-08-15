// Pure minimap enforcement planning, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// With the shuffle option on the radar disc stays hidden until the Minimap
// item arrives. The game exposes a script-facing radar-hide flag (the
// DISPLAY_RADAR opcode's backing static); while the item is missing the plan
// asserts it every frame, winning over any script that shows the radar. Once
// the item arrives the plan clears the flag exactly once and then leaves it
// to the game, so the vanilla missions that hide the radar keep their hide.
#pragma once

namespace gtavc {

enum class MinimapAction { kLeaveAlone, kForceHidden, kReleaseOnce };

struct MinimapPlan {
  MinimapAction action = MinimapAction::kLeaveAlone;
  bool forcing = false;
};

// One frame of minimap planning: `shuffled` and `unlocked` read from the
// reserved globals, `forcing` carried between frames so the release fires
// once on the locked-to-unlocked transition instead of stomping the flag
// forever. With the option off the plan never touches the flag, the vanilla
// semantics.
inline MinimapPlan PlanMinimapEnforcement(bool shuffled, bool unlocked, bool forcing) {
  MinimapPlan plan;
  if (!shuffled) return plan;
  if (!unlocked) {
    plan.action = MinimapAction::kForceHidden;
    plan.forcing = true;
  } else if (forcing) {
    plan.action = MinimapAction::kReleaseOnce;
  }
  return plan;
}

}  // namespace gtavc
