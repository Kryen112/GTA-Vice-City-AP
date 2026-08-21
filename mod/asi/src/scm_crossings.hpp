// The mainland routes, free of any game headers so the console self-test can
// exercise them without plugin-sdk or the game.
//
// The way to the mainland is either one item that opens every vanilla crossing
// or, with split_mainland_access on, one item per crossing that opens only its
// own barrier. Nothing here decides which: the world sends the routes it made,
// one entry or four, each carrying the global its item writes, the name to show,
// and the global of the second item its route needs, which is the Starfish
// causeway and the island its gate stands on.
//
// The mod announces a route because the player otherwise has no way to learn
// which crossing they were handed: the barrier simply vanishes somewhere across
// the city.
#pragma once

#include <cstddef>
#include <string>
#include <vector>

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

// One frame of route reporting, the same shape as the content-lock release plan
// and for the same two reasons: announcing on the first frame a game is observed
// would re-announce every loaded save, and waiting for a change without taking a
// baseline first would lose the announcement for a player whose route item is
// the first item of the game. So the first observation is the baseline and every
// edge after it speaks.
struct RouteReportPlan {
  std::vector<RouteState> next_was;
  std::vector<std::string> announce;
};

inline RouteReportPlan PlanRouteReports(const std::vector<MainlandRoute>& routes,
                                        const std::vector<int>& unlock_values,
                                        const std::vector<int>& needs_values,
                                        const std::vector<RouteState>& was,
                                        bool baseline_ready) {
  RouteReportPlan plan;
  if (routes.size() != unlock_values.size() ||
      routes.size() != needs_values.size()) {
    return plan;
  }
  plan.next_was.reserve(routes.size());
  for (std::size_t index = 0; index < routes.size(); ++index) {
    const MainlandRoute& route = routes[index];
    const RouteState state =
        RouteStateOf(route, unlock_values[index], needs_values[index]);
    plan.next_was.push_back(state);
    // A route whose state the caller has not seen before is a baseline, not an
    // edge: a size change means the seed's routes were only just configured.
    if (!baseline_ready || index >= was.size() || was[index] == state) continue;
    if (state == RouteState::kOpen) {
      plan.announce.push_back(route.label + " is open.");
    } else if (state == RouteState::kWaiting) {
      plan.announce.push_back(route.label + " needs " + route.needs_label + ".");
    }
  }
  return plan;
}

}  // namespace gtavc
