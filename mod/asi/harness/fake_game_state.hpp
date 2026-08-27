// An in-memory GameState for the console harness: records what the bridge
// applies (welcome hash, items, checked, toasts) and lets the harness queue
// checks and a goal to send upward. Thread-safe, since the bridge thread and
// the harness main thread both touch it.
#pragma once

#include <array>
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

  // Flattened to one string per row, because what the interop check is about is
  // that the Python side and the C++ side agree on the frame: the colours and the
  // line breaks are the console self-test's business, and it drives the row
  // builder directly. The break is kept visible so a row that lost its second
  // line still reads as different from one that never had one.
  void ShowToast(const ToastRow& row) override {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string text;
    for (const std::vector<ToastSegment>& line : row.lines) {
      if (!text.empty()) text += " | ";
      text += ToastLineText(line);
    }
    toasts_.push_back(text);
  }

  void ShowNotice(ToastNotice notice, const std::string& text) override {
    std::lock_guard<std::mutex> lock(mutex_);
    notices_[ToastNoticeSlot(notice)] = text;
  }

  void ClearNotice(ToastNotice notice) override {
    std::lock_guard<std::mutex> lock(mutex_);
    notices_[ToastNoticeSlot(notice)].clear();
  }

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

  // Never any, since nothing in the harness stands in for the game frame that
  // finds a landing. The interop check drives the frames this fake has, and the
  // report planner is exercised directly by the console self-test instead.
  std::vector<std::int64_t> TakeAppliedReports() override { return {}; }

  bool TakeGoalReached() override {
    std::lock_guard<std::mutex> lock(mutex_);
    const bool reached = goal_pending_;
    goal_pending_ = false;
    return reached;
  }

  void ApplyDeathLink(const std::string& source) override {
    std::lock_guard<std::mutex> lock(mutex_);
    death_links_.push_back(source);
  }

  bool TakeDeath() override {
    std::lock_guard<std::mutex> lock(mutex_);
    const bool died = death_pending_;
    death_pending_ = false;
    return died;
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

  void QueueDeath() {
    std::lock_guard<std::mutex> lock(mutex_);
    death_pending_ = true;
  }

  // Who each linked death said it came from, in arrival order, so the interop
  // check can prove the source survived the decode.
  std::vector<std::string> DeathLinks() {
    std::lock_guard<std::mutex> lock(mutex_);
    return death_links_;
  }

  std::string StampedSeedHash() {
    std::lock_guard<std::mutex> lock(mutex_);
    return stamped_seed_hash_;
  }

  // The notices, so a session can assert what the handshake left behind: the
  // welcome path clears the refusal slot, and both being empty afterwards is what
  // says that clear ran. Empty means the slot carries none.
  std::array<std::string, kToastNoticeCount> Notices() {
    std::lock_guard<std::mutex> lock(mutex_);
    return notices_;
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
  std::array<std::string, kToastNoticeCount> notices_{};
  std::vector<std::int64_t> pending_checks_;
  std::vector<std::string> death_links_;
  bool death_pending_ = false;
  bool goal_pending_ = false;
  int pending_percentage_ = -1;
  bool client_connected_ = false;
  bool client_was_connected_ = false;
  ClientStatus client_status_;
};

}  // namespace gtavc
