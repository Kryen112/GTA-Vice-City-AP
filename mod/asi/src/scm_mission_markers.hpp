#pragma once

namespace gtavc {

// Match C3dMarkers::Render's horizontal range before allocating its 32 slots.
inline bool ContactMarkerInRange(float delta_x, float delta_y) {
  return delta_x * delta_x + delta_y * delta_y < 150.0f * 150.0f;
}

}  // namespace gtavc
