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

class GameState {
 public:
  virtual ~GameState() = default;

  // How received items map to SCM globals, sent once per connection before the
  // resync. item_globals: AP item id -> the unlock global it counts toward.
  // completion_watch: completion global index -> AP location id to poll.
  virtual void ApplyConfig(const std::map<std::int64_t, int>& item_globals,
                           const std::map<int, std::int64_t>& completion_watch) = 0;

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

  // Location ids newly completed in game since the last call (drains the
  // queue). Polled by the bridge each loop.
  virtual std::vector<std::int64_t> TakeNewChecks() = 0;

  // True once when the goal was newly reached.
  virtual bool TakeGoalReached() = 0;
};

}  // namespace gtavc
