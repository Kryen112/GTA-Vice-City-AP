// The real GameState: reads and writes SCM globals through plugin-sdk. The
// bridge thread posts inbound config, items, checked, and toasts into
// thread-safe mailboxes; all SCM memory access happens on the game frame in
// OnGameFrame, so ScriptSpace is only ever touched by the game thread.
#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "game_state.hpp"
#include "scm_completion.hpp"
#include "scm_effects.hpp"
#include "scm_radio.hpp"

class CVehicle;

namespace gtavc {

using Logger = std::function<void(const std::string&)>;

class ScmGameState : public GameState {
 public:
  explicit ScmGameState(Logger logger);

  // GameState, called from the bridge thread.
  void ApplyConfig(const std::map<std::int64_t, int>& item_globals,
                   const std::map<int, std::int64_t>& completion_watch,
                   const std::map<std::int64_t, ItemEffect>& item_effects,
                   const std::map<int, int>& config_globals,
                   const std::vector<PackageLocation>& package_locations) override;
  std::string SeedHash() override;
  void StampSeedHash(const std::string& expected) override;
  void ApplyItems(const std::vector<std::pair<std::int64_t, std::int64_t>>& items) override;
  void MarkChecked(const std::vector<std::int64_t>& locations) override;
  void ShowToast(const std::string& text) override;
  std::vector<std::int64_t> TakeNewChecks() override;
  bool TakeGoalReached() override;

  // Called from the game frame. All SCM memory access is here.
  void OnGameFrame();

 private:
  static int GetGlobal(int index);
  static void SetGlobal(int index, int value);
  // Sets each collected package's completion global by matching the game's
  // collectable pickups to the configured package coordinates. Only a package
  // seen present this session and then gone counts as collected, so the pool not
  // yet being placed on a new game cannot false-report.
  void DetectCollectedPackages();
  static std::string ReadSeedHash();
  static void WriteSeedHash(const std::string& hash);
  // Applies one consumable effect to the live player through plugin-sdk.
  static void ApplyEffect(const ItemEffect& effect);
  // Applies one one-shot effect: a consumable field write or a trap world
  // action. Arms the timed traps' revert deadlines, so it is not static.
  void ApplyOneShot(const ItemEffect& effect);
  // Fires one trap into the world through plugin-sdk. The timed traps
  // (hostile peds, sped-up and slowed time) record a deadline for UpdateTimedTraps.
  void ApplyTrap(const ItemEffect& effect);
  // Holds the sped-up/slowed clock and the hostile-pedestrian window for their
  // duration, reverting each once its deadline passes. Runs every frame.
  void UpdateTimedTraps();
  // True when the game hands the player control: not in a cutscene, on a
  // mission pass/fail screen, or otherwise script-owned. The one flag the trap
  // deferral keys on.
  static bool PlayerIsControllable();
  // The pause-mode millisecond clock, which advances in real time regardless of
  // any time-scale trap, so a trap's own effect cannot distort its own timer.
  static unsigned int RealTimeMs();
  // The BIGBANG-style trap: blow up every loaded vehicle, the player's included.
  static void ExplodeAllVehicles();
  // The NOBODYLIKESME-style trap: set every loaded pedestrian to attack the
  // player. Re-asserted each frame of the window so freshly spawned peds join.
  static void MakePedestriansHostile();
  // Clears the attack objective from every loaded pedestrian when the window ends.
  static void CalmPedestrians();
  // Keeps every vehicle radio on an unlocked station while the randomize
  // option is on: recomputes the resolve globals from the station unlocks,
  // remaps vehicle station bytes, rewrites pending retune presses so the
  // scroll only visits unlocked stations, and posts a retune request to the
  // APRADIO watcher when a locked station reaches the player's own vehicle.
  void EnforceRadioStations();
  // Rewrites the game's pending retune press count so the vanilla commit
  // lands on the next stop of the allowed cycle instead of the vanilla
  // eleven-position wheel. Classic 1.0 executable only (the press static is
  // a pinned raw address); elsewhere the post-commit correction covers it.
  void RewriteRetunePresses(CVehicle* player_vehicle,
                            const std::array<bool, kRadioStationCount>& unlocked);

  Logger logger_;
  std::mutex mutex_;
  std::map<std::int64_t, int> item_globals_;
  std::map<std::int64_t, ItemEffect> item_effects_;
  std::map<int, int> config_globals_;
  std::map<int, std::int64_t> completion_watch_;
  std::vector<PackageLocation> package_locations_;
  std::set<int> package_seen_present_;
  std::map<std::int64_t, int> location_to_global_;
  std::vector<std::pair<std::int64_t, std::int64_t>> items_;
  std::set<int> reported_;
  // The completion globals as they read when this game started; a real
  // completion is a change away from a zero baseline. Captured once per game.
  std::map<int, int> baseline_;
  std::vector<std::int64_t> outbound_checks_;
  std::vector<std::string> pending_toasts_;
  std::string pending_stamp_;
  std::string cached_seed_hash_;
  bool items_dirty_ = false;
  bool stamp_pending_ = false;
  bool baseline_captured_ = false;
  // Timed-trap state, reverted once each deadline (in real milliseconds) passes.
  bool time_scale_trap_active_ = false;
  unsigned int time_scale_trap_until_ = 0;
  float time_scale_trap_factor_ = 1.0f;
  bool hostile_pedestrians_active_ = false;
  unsigned int hostile_pedestrians_until_ = 0;
  // Retune press bookkeeping: how many presses the player has logically made
  // this scroll, and the raw value last written back, so fresh presses can be
  // told apart from the rewritten count.
  int retune_logical_presses_ = 0;
  int retune_written_presses_ = 0;
};

}  // namespace gtavc
