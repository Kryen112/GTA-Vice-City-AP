// The real GameState: reads and writes SCM globals through plugin-sdk. The
// bridge thread posts inbound config, items, checked, and toasts into
// thread-safe mailboxes; all SCM memory access happens on the game frame in
// OnGameFrame, so ScriptSpace is only ever touched by the game thread.
#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "game_state.hpp"
#include "scm_ability_locks.hpp"
#include "scm_completion.hpp"
#include "scm_content_locks.hpp"
#include "scm_effects.hpp"
#include "scm_minimap.hpp"
#include "scm_pickup_layout.hpp"
#include "scm_radio.hpp"
#include "scm_toasts.hpp"

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
                   const std::vector<PackageLocation>& package_locations,
                   const std::vector<PickupTarget>& pickup_targets) override;
  std::string SeedHash() override;
  void StampSeedHash(const std::string& expected) override;
  void ApplyItems(const std::vector<std::pair<std::int64_t, std::int64_t>>& items) override;
  void MarkChecked(const std::vector<std::int64_t>& locations) override;
  void ShowToast(const std::string& text) override;
  void ShowStickyToast(const std::string& text) override;
  std::vector<std::int64_t> TakeNewChecks() override;
  bool TakeGoalReached() override;

  // Called from the game frame. All SCM memory access is here.
  void OnGameFrame();

  // Called from the pre-world-process hook, before the player ped reads the
  // pad this frame. Applies only the ability locks that constrain input.
  void OnBeforeWorldProcess();

 private:
  static int GetGlobal(int index);
  static void SetGlobal(int index, int value);
  // Writes the game's own unique stunt jump table beside the executable, found
  // by scanning the heap for it. A development tool: the jump positions are the
  // one thing the tracker pack cannot read offline, since the game never writes
  // them down anywhere a build step could reach. Runs only on its key press.
  void DumpStuntJumps();
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
  // Fires one trap into the world through plugin-sdk. The timed traps (hostile
  // peds, sped-up and slowed time, drunk vision) record a deadline for
  // UpdateTimedTraps.
  void ApplyTrap(const ItemEffect& effect);
  // Holds the sped-up/slowed clock, the hostile-pedestrian window, and the
  // drunk-vision window for their duration, reverting each once its deadline
  // passes. Runs every frame.
  void UpdateTimedTraps();
  // True when the game hands the player control: not in a cutscene, on a
  // mission pass/fail screen, or otherwise script-owned. The one flag all item
  // application keys on: unlock globals and one-shot effects alike wait for it.
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
  // Keeps the radar disc hidden while the shuffle option is on and the
  // Minimap item has not arrived, through the game's script-facing radar-hide
  // flag; on the item it releases the flag back to the game once.
  void EnforceMinimap();
  // Enforces the locks of both families that belong on the game frame, after
  // the world has processed: pins the wallet balance to zero, cancels a
  // player-initiated entry into a locked vehicle class, holds the pickups of
  // every held content class, announces a class that has just been released,
  // and answers the status key with the seed's lock status.
  void EnforceLocks();
  // Masks the locked inputs and holds the current weapon on the fists. Runs
  // from the pre-world-process hook, the one point in the frame where a pad
  // write still reaches the player ped (see kBeforeWorldProcessCallSite10).
  void ApplyAbilityInputLocks();
  // Reads the eight lock flags and eight unlocks into `lock_flags` and
  // returns which abilities are locked right now. Both enforcement points
  // derive their own state, so neither depends on the other having run (the
  // input hook only exists on the classic executable).
  AbilityLocks ReadAbilityLocks(std::array<int, kAbilityCount>& lock_flags);
  // Reads the five content lock flags and unlocks into `lock_flags` and
  // returns which classes are held right now.
  ContentLocks ReadContentLocks(std::array<int, kContentCount>& lock_flags);
  // Sinks the pickups of every held class out of reach and raises them back on
  // release: the hidden packages, the rampage icons, and the fifteen property
  // icons. One pool walk covers all three, and the two lock families union, so
  // a weapon-rampage icon is held by either the weapon equip or the rampages
  // key while the two run-them-down icons answer only to the latter.
  void EnforceHeldPickups(const AbilityLocks& locked, const ContentLocks& held);
  // Announces each class on its held-to-released edge. Every class is silent
  // while held (a held jump reads as a failed landing, a held store as not
  // aiming, a held pickup is simply absent), so the release edge is the only
  // place a player is told why the world just changed.
  void ReportReleasedContent(const ContentLocks& held,
                             const std::array<int, kContentCount>& lock_flags);
  // Shows the blocked-attempt toast for one ability, rate-limited per ability.
  void ToastAbilityBlocked(int ability);
  // Shows this seed's whole lock status on the status key, as ONE message:
  // which configured abilities are locked or unlocked and which configured
  // content classes are held or available. Queued messages play in sequence, so
  // splitting the status across several would hold the screen for a multiple of
  // a message's time.
  void ToastLockStatus(const AbilityLocks& locked,
                       const std::array<int, kAbilityCount>& ability_flags,
                       const ContentLocks& held,
                       const std::array<int, kContentCount>& content_flags);
  // Keeps the ambient pickup pool on the configured layout: matches each
  // layout slot to a pool entry by position and type and rewrites the model
  // and quantity where they differ, dropping the stale visible objects so the
  // game recreates them from the new model. Runs every frame, so a script
  // that removes and recreates a slot (the vanilla scripts do, with vanilla
  // models) is re-enforced on the next frame. Empty layout means vanilla.
  void EnforcePickupLayout();

  Logger logger_;
  std::mutex mutex_;
  std::map<std::int64_t, int> item_globals_;
  std::map<std::int64_t, ItemEffect> item_effects_;
  std::map<int, int> config_globals_;
  std::map<int, std::int64_t> completion_watch_;
  std::vector<PackageLocation> package_locations_;
  std::vector<PickupTarget> pickup_targets_;
  std::set<int> package_seen_present_;
  std::map<std::int64_t, int> location_to_global_;
  std::vector<std::pair<std::int64_t, std::int64_t>> items_;
  std::set<int> reported_;
  // The completion globals as they read when this game started; a real
  // completion is a change away from a zero baseline. Captured once per game.
  std::map<int, int> baseline_;
  std::vector<std::int64_t> outbound_checks_;
  std::vector<std::string> pending_toasts_;
  // Lines that wait for a game rather than for the next post. The frontend
  // cannot display a message, and the game boundary clears the ordinary queue,
  // so a handshake refusal would otherwise be lost to the log alone.
  std::vector<std::string> sticky_toasts_;
  // When the next post may hand the game a message, so a backlog waits in the
  // queue above instead of in the game's own few-slot one.
  unsigned int next_toast_ms_ = 0;
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
  bool drunk_trap_active_ = false;
  unsigned int drunk_trap_until_ = 0;
  // Retune press bookkeeping: how many presses the player has logically made
  // this scroll, and the raw value last written back, so fresh presses can be
  // told apart from the rewritten count.
  int retune_logical_presses_ = 0;
  int retune_written_presses_ = 0;
  // Whether the minimap enforcement is holding the radar-hide flag, so the
  // unlock releases it exactly once and then leaves the flag to the game.
  bool minimap_forcing_hidden_ = false;
  // Blocked-attempt toast rate limiting, one slot per ability, and the
  // status-key edge detector. Reset on the game boundary.
  std::array<bool, kAbilityCount> ability_toast_shown_{};
  std::array<unsigned int, kAbilityCount> ability_toast_last_ms_{};
  bool ability_status_key_was_down_ = false;
  // The stunt jump dump key's edge detector, so one press writes one file.
  bool stunt_jump_key_was_down_ = false;
  // The kill-frenzy skull model, resolved by name and latched on the first
  // hit; negative while unresolved, when the rampage icons stay vanilla.
  // Reset on the game boundary with the other per-game state.
  int kill_frenzy_model_ = -1;
  bool kill_frenzy_lookup_logged_ = false;
  // Whether each content class was held last frame, so a release is announced
  // once rather than every frame. Reset on the game boundary, so a class
  // released before a reload does not announce itself again.
  ContentLocks content_was_held_{};
  // The last pool action logged per held pickup class, so the log names which
  // classes the walk reached and in which direction without repeating itself
  // every frame. Reset on the game boundary.
  std::array<PickupHoldAction, kHeldPickupClassCount> held_class_logged_{};
  // Whether the release baseline has been taken. The first frame a game is
  // observed sets the baseline instead of announcing from it, so a save that
  // already holds a content item stays quiet while a class released during play
  // always announces exactly once.
  bool content_baseline_ready_ = false;
  // Whether the world was loaded last frame, so a new game or a save load
  // re-derives the unlock globals from the received items instead of
  // trusting whatever the save restored.
  bool world_was_loaded_ = false;
  // Frames the pickup layout enforcement has run this game, so the
  // unmatched-slot diagnostic fires once, past the init mission's pickup
  // creation window. Reset on the game boundary and on a fresh config.
  int pickup_enforce_frames_ = 0;
};

}  // namespace gtavc
