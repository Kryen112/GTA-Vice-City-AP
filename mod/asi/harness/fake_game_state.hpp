// An in-memory GameState for the console harness: records what the bridge
// applies (welcome hash, items, checked, toasts) and lets the harness queue
// checks and a goal to send upward. Thread-safe, since the bridge thread and
// the harness main thread both touch it.
#pragma once

#include <mutex>
#include <string>
#include <utility>
#include <vector>

#include "../src/game_state.hpp"

namespace gtavc {

class FakeGameState : public GameState {
 public:
  explicit FakeGameState(std::string presented_seed_hash)
      : presented_seed_hash_(std::move(presented_seed_hash)) {}

  void ApplyConfig(const std::map<std::int64_t, int>& item_globals,
                   const std::map<int, std::int64_t>& completion_watch) override {
    std::lock_guard<std::mutex> lock(mutex_);
    item_globals_ = item_globals;
    completion_watch_ = completion_watch;
  }

  std::string SeedHash() override {
    std::lock_guard<std::mutex> lock(mutex_);
    return presented_seed_hash_;
  }

  void StampSeedHash(const std::string& expected) override {
    std::lock_guard<std::mutex> lock(mutex_);
    stamped_seed_hash_ = expected;
    if (presented_seed_hash_.empty()) presented_seed_hash_ = expected;
  }

  void ApplyItems(const std::vector<std::pair<std::int64_t, std::int64_t>>& items) override {
    std::lock_guard<std::mutex> lock(mutex_);
    applied_items_ = items;
  }

  void MarkChecked(const std::vector<std::int64_t>& locations) override {
    std::lock_guard<std::mutex> lock(mutex_);
    checked_ = locations;
  }

  void ShowToast(const std::string& text) override {
    std::lock_guard<std::mutex> lock(mutex_);
    toasts_.push_back(text);
  }

  std::vector<std::int64_t> TakeNewChecks() override {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::int64_t> drained;
    drained.swap(pending_checks_);
    return drained;
  }

  bool TakeGoalReached() override {
    std::lock_guard<std::mutex> lock(mutex_);
    const bool reached = goal_pending_;
    goal_pending_ = false;
    return reached;
  }

  // Harness controls and accessors.
  void QueueCheck(std::int64_t location) {
    std::lock_guard<std::mutex> lock(mutex_);
    pending_checks_.push_back(location);
  }

  std::string StampedSeedHash() {
    std::lock_guard<std::mutex> lock(mutex_);
    return stamped_seed_hash_;
  }

  std::vector<std::pair<std::int64_t, std::int64_t>> AppliedItems() {
    std::lock_guard<std::mutex> lock(mutex_);
    return applied_items_;
  }

  std::vector<std::int64_t> Checked() {
    std::lock_guard<std::mutex> lock(mutex_);
    return checked_;
  }

  std::vector<std::string> Toasts() {
    std::lock_guard<std::mutex> lock(mutex_);
    return toasts_;
  }

  std::map<std::int64_t, int> ItemGlobals() {
    std::lock_guard<std::mutex> lock(mutex_);
    return item_globals_;
  }

  std::map<int, std::int64_t> CompletionWatch() {
    std::lock_guard<std::mutex> lock(mutex_);
    return completion_watch_;
  }

 private:
  std::mutex mutex_;
  std::string presented_seed_hash_;
  std::string stamped_seed_hash_;
  std::map<std::int64_t, int> item_globals_;
  std::map<int, std::int64_t> completion_watch_;
  std::vector<std::pair<std::int64_t, std::int64_t>> applied_items_;
  std::vector<std::int64_t> checked_;
  std::vector<std::string> toasts_;
  std::vector<std::int64_t> pending_checks_;
  bool goal_pending_ = false;
};

}  // namespace gtavc
