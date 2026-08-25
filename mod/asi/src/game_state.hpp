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

// MainlandRoute and PickupDistrict are part of the configuration this interface
// carries, and the headers holding them are game-free like this one.
#include "scm_content_locks.hpp"
#include "scm_crossings.hpp"
#include "scm_toasts.hpp"

namespace gtavc {

// A one-shot effect applied once past the saved applied-index.
//
// Consumables: "cash" (amount is the value), "weapon", "health", "armor",
// "clear_wanted" (drops the wanted level to zero, like the LEAVEMEALONE cheat).
// Traps: "trap_wanted" (amount is stars to add), "trap_hostile_peds" /
// "trap_speed_up" / "trap_slow_down" / "trap_drunk"
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
  // The completion global of the check on this slot, or 0 when the slot is
  // not a check. Reading zero from a non-zero global means the check is
  // still to be taken, which is when the slot wears the AP marker.
  int check_global = 0;
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  int pickup_type = 0;
  int model = 0;
  int quantity = 0;
  // The weapon type this stand prices from while it wears the AP marker, or 0
  // to let the marker's own price stand. Only Phil's four carry one: they are
  // in-shop pickups the engine sells, so the marker would price them at what it
  // prices every marker at, and what the shop class promises is that a stand
  // costs what it costs in vanilla. A price index and not an amount, because
  // that is what the purchase path reads.
  int price_weapon_type = 0;
};

// One line the client composed for the status page, because only the client knows
// what it says: the seed's goal and how far each mission strand has come are AP
// state, not anything the game's own memory holds.
struct ClientRow {
  std::string label;
  std::string value;
  // Whether the thing this row names is finished, which is all the colour the
  // page needs from the client.
  bool done = false;
};

// Everything the client tells the status page. The counts are AP's own; the rows
// are what only AP can answer.
struct ClientStatus {
  int checks_done = 0;
  int checks_total = 0;
  int items_received = 0;
  bool goal_reached = false;
  std::vector<ClientRow> goal_rows;
  std::vector<ClientRow> strand_rows;
  // The client asking for the story's ending, which only it can know: the
  // hidden-packages goal is a macguffin hunt, and the last fragment ends the
  // game wherever the player is standing. The mod raises the finale warp flag
  // from it and the script's own watcher launches the finale.
  bool finale_warp = false;
};

class GameState {
 public:
  virtual ~GameState() = default;

  // How received items map to SCM state, sent once per connection before the
  // content_district_globals: AP item id -> every district unlock global that
  // item releases, beside item_globals rather than inside it because one content
  // item can release many. content_districts: where each holdable pickup stands
  // and which district it is in, so a pool entry found by type or model can be
  // placed.
  //
  // resync. item_globals: AP item id -> the count global it adds one to (unlock
  // or persistent reward). item_effects: AP item id -> a one-shot consumable
  // effect. config_globals: config-flag global index -> value to stamp.
  // completion_watch: completion global index -> AP location id to poll.
  // pickup_targets: the ambient pickup layout to enforce, empty when vanilla.
  // routes carries every crossing off the start island: the mainland ways, one
  // entry when Mainland Access opens them all and one per crossing when the seed
  // split them, and then Starfish Island, which is always its own row.
  virtual void ApplyConfig(const std::map<std::int64_t, int>& item_globals,
                           const std::map<int, std::int64_t>& completion_watch,
                           const std::map<std::int64_t, ItemEffect>& item_effects,
                           const std::map<int, int>& config_globals,
                           const std::vector<PackageLocation>& package_locations,
                           const std::vector<PickupTarget>& pickup_targets,
                           const std::vector<MainlandRoute>& routes,
                           const std::map<std::int64_t, std::vector<int>>&
                               content_district_globals,
                           const std::vector<PickupDistrict>& pickup_districts) = 0;

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

  // A player-facing row for the in-game toast stack, already built into its
  // coloured segments by the client, since only the client knows which slot is
  // ours and how the server classified an item.
  virtual void ShowToast(const ToastRow& row) = 0;

  // A row that holds its place until something clears it, addressed by what it is
  // about so a repeat replaces rather than stacks. The handshake refusal arrives
  // while the player is still in the frontend, where nothing can be drawn at all,
  // and it is the only thing that explains why nothing in the game will work.
  virtual void ShowNotice(ToastNotice notice, const std::string& text) = 0;
  virtual void ClearNotice(ToastNotice notice) = 0;

  // Whether the client's socket is up, for the pause menu's status page. The
  // page is drawn while the game frame does not run, so it cannot infer this
  // from anything the frame does.
  virtual void SetClientConnected(bool connected) = 0;

  // What only the client knows, for that same page: how many of this seed's
  // locations are checked, how many it has, how many items have arrived, whether
  // AP has this slot finished, and the goal and mission-strand lines. The mod
  // knows which completion globals it watches, but not which of them this seed
  // turned into locations, nor what its goal asks for.
  virtual void SetClientStatus(const ClientStatus& status) = 0;

  // Location ids newly completed in game since the last call (drains the
  // queue). Polled by the bridge each loop.
  virtual std::vector<std::int64_t> TakeNewChecks() = 0;
  // Hands back locations a send could not deliver. Detection cannot find a
  // location twice, so a caller that drains must return what it fails to send.
  virtual void RequeueChecks(const std::vector<std::int64_t>& undelivered) = 0;

  // True once when the goal was newly reached.
  virtual bool TakeGoalReached() = 0;

  // The game's completion percentage, as its stats menu prints it, when it has
  // changed since the last call. False when there is nothing new to report, so
  // the bridge sends a frame per change rather than one per frame.
  virtual bool TakeProgressPercentage(int& percentage) = 0;
};

}  // namespace gtavc
