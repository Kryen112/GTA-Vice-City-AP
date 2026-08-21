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
#include "../src/scm_completion.hpp"

namespace gtavc {

class FakeGameState : public GameState {
 public:
  explicit FakeGameState(std::string presented_seed_hash)
      : presented_seed_hash_(std::move(presented_seed_hash)) {}

  void ApplyConfig(const std::map<std::int64_t, int>& item_globals,
                   const std::map<int, std::int64_t>& completion_watch,
                   const std::map<std::int64_t, ItemEffect>& item_effects,
                   const std::map<int, int>& config_globals,
                   const std::vector<PackageLocation>& package_locations,
                   const std::vector<PickupTarget>& pickup_targets,
                   const std::vector<MainlandRoute>& routes,
                   const std::map<std::int64_t, std::vector<int>>&
                       content_district_globals,
                   const std::vector<PickupDistrict>& pickup_districts) override {
    std::lock_guard<std::mutex> lock(mutex_);
    item_globals_ = item_globals;
    completion_watch_ = completion_watch;
    item_effects_ = item_effects;
    config_globals_ = config_globals;
    package_locations_ = package_locations;
    pickup_targets_ = pickup_targets;
    mainland_routes_ = routes;
    content_district_globals_ = content_district_globals;
    pickup_districts_ = pickup_districts;
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

  void ShowStickyToast(const std::string& text) override { ShowToast(text); }

  void SetClientConnected(bool connected) override {
    std::lock_guard<std::mutex> lock(mutex_);
    client_connected_ = connected;
    // Kept as well as the live flag, because a session always ends
    // disconnected: this is what says the welcome ever marked it up.
    client_was_connected_ = client_was_connected_ || connected;
  }

  void SetClientStatus(const ClientStatus& status) override {
    std::lock_guard<std::mutex> lock(mutex_);
    client_status_ = status;
  }

  std::vector<std::int64_t> TakeNewChecks() override {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::int64_t> drained;
    drained.swap(pending_checks_);
    return drained;
  }

  void RequeueChecks(const std::vector<std::int64_t>& undelivered) override {
    std::lock_guard<std::mutex> lock(mutex_);
    gtavc::RequeueChecks(pending_checks_, undelivered);
  }

  bool TakeGoalReached() override {
    std::lock_guard<std::mutex> lock(mutex_);
    const bool reached = goal_pending_;
    goal_pending_ = false;
    return reached;
  }

  bool TakeProgressPercentage(int& percentage) override {
    std::lock_guard<std::mutex> lock(mutex_);
    if (pending_percentage_ < 0) return false;
    percentage = pending_percentage_;
    pending_percentage_ = -1;
    return true;
  }

  // Harness controls and accessors.
  void QueueCheck(std::int64_t location) {
    std::lock_guard<std::mutex> lock(mutex_);
    pending_checks_.push_back(location);
  }

  void QueuePercentage(int percentage) {
    std::lock_guard<std::mutex> lock(mutex_);
    pending_percentage_ = percentage;
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

  std::map<std::int64_t, ItemEffect> ItemEffects() {
    std::lock_guard<std::mutex> lock(mutex_);
    return item_effects_;
  }

  std::map<int, int> ConfigGlobals() {
    std::lock_guard<std::mutex> lock(mutex_);
    return config_globals_;
  }

  std::vector<PickupTarget> PickupTargets() {
    std::lock_guard<std::mutex> lock(mutex_);
    return pickup_targets_;
  }

  std::vector<MainlandRoute> MainlandRoutes() {
    std::lock_guard<std::mutex> lock(mutex_);
    return mainland_routes_;
  }

  bool ClientConnected() {
    std::lock_guard<std::mutex> lock(mutex_);
    return client_connected_;
  }

  bool ClientWasConnected() {
    std::lock_guard<std::mutex> lock(mutex_);
    return client_was_connected_;
  }

  ClientStatus Status() {
    std::lock_guard<std::mutex> lock(mutex_);
    return client_status_;
  }

 private:
  std::mutex mutex_;
  std::string presented_seed_hash_;
  std::string stamped_seed_hash_;
  std::map<std::int64_t, int> item_globals_;
  std::map<std::int64_t, ItemEffect> item_effects_;
  std::map<int, int> config_globals_;
  std::map<int, std::int64_t> completion_watch_;
  std::vector<PackageLocation> package_locations_;
  std::vector<PickupTarget> pickup_targets_;
  std::vector<MainlandRoute> mainland_routes_;
  std::map<std::int64_t, std::vector<int>> content_district_globals_;
  std::vector<PickupDistrict> pickup_districts_;
  std::vector<std::pair<std::int64_t, std::int64_t>> applied_items_;
  std::vector<std::int64_t> checked_;
  std::vector<std::string> toasts_;
  std::vector<std::int64_t> pending_checks_;
  bool goal_pending_ = false;
  int pending_percentage_ = -1;
  bool client_connected_ = false;
  bool client_was_connected_ = false;
  ClientStatus client_status_;
};

}  // namespace gtavc
