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

#include <cmath>
#include <array>

namespace gtavc {

// Category order matches check_markers.py.
inline std::array<unsigned char, 3> CheckMarkerColor(int category) {
  static constexpr std::array<unsigned char, 3> colors[] = {
      {255, 255, 255}, {60, 255, 90}, {255, 130, 140}, {185, 35, 55},
      {255, 155, 30}, {65, 140, 255}, {255, 235, 65}, {55, 240, 240}, {215, 120, 255}};
  return colors[category >= 0 && category < 9 ? category : 0];
}

// Pin nearby dots inside the rim and around the corner in a 3x minimap size radius.
inline bool ProjectCheckMarker(float& x, float& y, float radius_x, float radius_y) {
  if (!std::isfinite(radius_x) || !std::isfinite(radius_y) ||
      radius_x <= 0.0f || radius_y <= 0.0f) return false;
  const float distance = std::hypot(x, y);
  const float rim = 1.0f - std::hypot(4.0f / radius_x, 4.0f / radius_y);
  if (!std::isfinite(distance) || distance > 3.0f || rim <= 0.0f) return false;
  if (distance > rim) {
    x *= rim / distance;
    y *= rim / distance;
  }
  return true;
}

// Main-map dots keep their pixel size as the map zooms. Coordinates are snapped
// before this check so the black outline stays entirely inside the viewport.
inline bool CheckMarkerFitsScreen(float x, float y, float width, float height) {
  return x >= 3.0f && y >= 3.0f && x + 4.0f <= width && y + 4.0f <= height;
}

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
