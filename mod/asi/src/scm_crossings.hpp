// The crossings off the start island, free of any game headers so the console
// self-test can exercise them without plugin-sdk or the game.
//
// The way to the mainland is either one item that opens every vanilla crossing
// or, with split_mainland_access on, one item per crossing that opens only its
// own barrier. Starfish Island is a crossing of its own and is always sent.
// Nothing here decides how many: the world sends the routes it made, each
// carrying the global its item writes, the name to show, and the global of the
// second item its route needs, which is the Starfish causeway and the island its
// gate stands on.
//
// Nothing here announces anything. A crossing opening is visible from the road,
// and the item that opened it is named for the crossing, so the pause page's
// CROSSINGS block is the only place it is said.
#pragma once

#include <string>

namespace gtavc {

// One way to the mainland. needs_global is zero when the route needs nothing but
// its own item.
struct MainlandRoute {
  int unlock_global = 0;
  std::string label;
  int needs_global = 0;
  std::string needs_label;
};

// What a route is doing, from the globals alone. Waiting means the item arrived
// but the route is still shut, which only a route with a second requirement can
// be: the causeway opens no gate until the island it stands on is held.
enum class RouteState { kAbsent, kWaiting, kOpen };

inline RouteState RouteStateOf(const MainlandRoute& route, int unlock_value,
                               int needs_value) {
  if (unlock_value < 1) return RouteState::kAbsent;
  if (route.needs_global != 0 && needs_value < 1) return RouteState::kWaiting;
  return RouteState::kOpen;
}

}  // namespace gtavc
