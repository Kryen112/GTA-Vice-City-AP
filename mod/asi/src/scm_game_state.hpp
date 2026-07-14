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

namespace gtavc {

using Logger = std::function<void(const std::string&)>;

class ScmGameState : public GameState {
 public:
  explicit ScmGameState(Logger logger);

  // GameState, called from the bridge thread.
  void ApplyConfig(const std::map<std::int64_t, int>& item_globals,
                   const std::map<int, std::int64_t>& completion_watch) override;
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
  static std::string ReadSeedHash();
  static void WriteSeedHash(const std::string& hash);

  Logger logger_;
  std::mutex mutex_;
  std::map<std::int64_t, int> item_globals_;
  std::map<int, std::int64_t> completion_watch_;
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
};

}  // namespace gtavc
