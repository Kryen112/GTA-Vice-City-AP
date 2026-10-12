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
#include <cwchar>
#include <string>
#include <string_view>

namespace gtavc {

using CheckMarkerPalette = std::array<std::array<unsigned char, 3>, 10>;

// Category order matches check_markers.py, plus the fallback and finale assets.
inline constexpr CheckMarkerPalette kDefaultCheckMarkerColors = {{
      {255, 255, 255}, {60, 255, 90}, {255, 130, 140}, {185, 35, 55},
      {255, 155, 30}, {65, 140, 255}, {255, 235, 65}, {55, 240, 240}, {215, 120, 255},
      {180, 255, 35}}};
// muted palette for nine categories, with white for the fallback
// taken from: https://sronpersonalpages.nl/~pault/#sec:qualitative
inline constexpr CheckMarkerPalette kColorblindCheckMarkerColors = {{
      {255, 255, 255}, {136, 204, 238}, {204, 102, 119}, {136, 34, 85},
      {221, 204, 119}, {51, 34, 136}, {17, 119, 51}, {68, 170, 153}, {170, 68, 153},
      {153, 153, 51}}};
inline constexpr const wchar_t* kCheckMarkerColorKeys[] = {
    L"other", L"hidden_packages", L"robbable_stores", L"rampages", L"pickups",
    L"stunt_jumps", L"properties", L"side_events", L"shops", L"finale_assets"};

inline std::array<unsigned char, 3> ParseCheckMarkerColor(
    std::wstring_view value, std::array<unsigned char, 3> fallback) {
  if (!value.empty() && value.front() == L'#') value.remove_prefix(1);
  if (value.size() != 6 || value.find_first_not_of(L"0123456789abcdefABCDEF") != std::wstring_view::npos)
    return fallback;
  const auto rgb = std::wcstoul(std::wstring(value).c_str(), nullptr, 16);
  return {static_cast<unsigned char>(rgb >> 16), static_cast<unsigned char>(rgb >> 8),
          static_cast<unsigned char>(rgb)};
}

template <typename Read>
CheckMarkerPalette LoadCheckMarkerColors(Read read) {
  auto preset = read(L"preset");
  for (auto& c : preset) if (c >= L'A' && c <= L'Z') c += L'a' - L'A';
  if (preset == L"colorblind") return kColorblindCheckMarkerColors;
  auto colors = kDefaultCheckMarkerColors;
  for (std::size_t category = 0; category < colors.size(); ++category)
    colors[category] = ParseCheckMarkerColor(read(kCheckMarkerColorKeys[category]), colors[category]);
  return colors;
}

inline std::array<unsigned char, 3> CheckMarkerColor(
    int category, const CheckMarkerPalette& colors = kDefaultCheckMarkerColors) {
  return colors[category >= 0 && category < static_cast<int>(colors.size()) ? category : 0];
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
