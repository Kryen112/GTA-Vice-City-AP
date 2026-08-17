// Everything the bridge needs from the game, behind an interface so the
// console harness can fake it and the real .asi can back it with SCM globals
// through plugin-sdk. The bridge runs on a background thread and calls these,
// so an implementation that touches game memory must be thread-safe or marshal
// to the game frame internally.
#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace gtavc {

// A one-shot effect applied once past the saved applied-index.
//
// Consumables: "cash" (amount is the value), "weapon", "health", "armor",
// "clear_wanted" (drops the wanted level to zero, like the LEAVEMEALONE cheat).
// Traps: "trap_wanted" (amount is stars to add), "trap_explode_cars",
// "trap_hostile_peds" / "trap_speed_up" / "trap_slow_down" / "trap_drunk"
// (amount is the duration in seconds), and "trap_weather" (amount is the
// eWeather id to force). Like all item application, every effect waits until
// the player is controllable. has_amount records whether the descriptor
// carried the amount, so a round trip echoes the exact param list.
struct ItemEffect {
  std::string type;
  int amount = 0;
  bool has_amount = false;
};

// A hidden package: the completion global to set when it is collected, and its
// world position, so the ASI can match a collected collectable pickup to its
// package by coordinate (the game reports only a running count, not which one).
struct PackageLocation {
  int completion_global = 0;
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
};

// One ambient pickup slot of the randomize_pickups layout: the slot's world
// position and pickup type identify it in the pool; model and quantity are
// what the permutation assigns to stand there. An empty layout means the
// option is off and the pool is never touched. The position is kept at the
// wire's double precision so the interop harness echoes it back exactly; the
// pool matching happens well inside float tolerance either way.
struct PickupTarget {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  int pickup_type = 0;
  int model = 0;
  int quantity = 0;
};

class GameState {
 public:
  virtual ~GameState() = default;

  // How received items map to SCM state, sent once per connection before the
  // resync. item_globals: AP item id -> the count global it adds one to (unlock
  // or persistent reward). item_effects: AP item id -> a one-shot consumable
  // effect. config_globals: config-flag global index -> value to stamp.
  // completion_watch: completion global index -> AP location id to poll.
  // pickup_targets: the ambient pickup layout to enforce, empty when vanilla.
  virtual void ApplyConfig(const std::map<std::int64_t, int>& item_globals,
                           const std::map<int, std::int64_t>& completion_watch,
                           const std::map<std::int64_t, ItemEffect>& item_effects,
                           const std::map<int, int>& config_globals,
                           const std::vector<PackageLocation>& package_locations,
                           const std::vector<PickupTarget>& pickup_targets) = 0;

  // The seed hash to present on hello, read from the reserved SCM global.
  // Empty when no game has been started for this seed.
  virtual std::string SeedHash() = 0;

  // The expected hash from welcome. A new game stamps it into the reserved
  // global; an existing game leaves its stored value alone.
  virtual void StampSeedHash(const std::string& expected) = 0;

  // The full cumulative received-items list, as (index, item id). The
  // implementation re-derives every unlock global and re-applies one-shot
  // grants only past its saved applied-index.
  virtual void ApplyItems(const std::vector<std::pair<std::int64_t, std::int64_t>>& items) = 0;

  // Location ids AP already has checked, so the game does not re-send them.
  virtual void MarkChecked(const std::vector<std::int64_t>& locations) = 0;

  // A player-facing message for the in-game toast queue.
  virtual void ShowToast(const std::string& text) = 0;

  // The same, for a message that must survive until a game is running: the
  // handshake refusal arrives while the player is still in the frontend, where
  // no message can be displayed, and it is the only thing that explains why
  // nothing in the game will work.
  virtual void ShowStickyToast(const std::string& text) = 0;

  // Location ids newly completed in game since the last call (drains the
  // queue). Polled by the bridge each loop.
  virtual std::vector<std::int64_t> TakeNewChecks() = 0;

  // True once when the goal was newly reached.
  virtual bool TakeGoalReached() = 0;
};

}  // namespace gtavc
