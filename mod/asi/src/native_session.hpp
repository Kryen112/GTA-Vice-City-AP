#pragma once

#include <filesystem>
#include <chrono>
#include <set>
#include "bridge.hpp"
#include "game_state.hpp"
#include "console_text.hpp"

namespace gtavc {

std::string NativeSeedHash(const std::string& seed, const std::string& slot);

class NativeSession {
 public:
  using Sender = std::function<bool(const json&)>;
  NativeSession(GameState* game, Logger logger, Sender send,
                std::string slot_name, std::string password, std::filesystem::path state_directory,
                std::function<bool(const std::string&)> prepare_seed = {}, ConsoleOutput console = {});
  void Handle(const json& packet);
  void Tick(bool socket_connected);
  void Command(const std::string& text);

 private:
  bool Send(json message);
  bool Activate();
  void PublishItems();
  void PublishStatus();
  bool GoalReached() const;
  void PublishPercentage();
  void PersistChecks();
  bool SeedMatches() const;
  bool ConcernsSelf(int slot) const;
  std::string PlayerName(int slot) const;
  std::string Name(std::int64_t id, int slot, bool item) const;
  void ItemToast(const json& item, int receiving);
  void OutputConsole(const ConsoleMessage& message, bool notify = false);

  GameState* game_;
  Logger logger_;
  ConsoleOutput console_;
  Sender send_;
  std::function<bool(const std::string&)> prepare_seed_;
  std::string slot_name_, password_, seed_name_, seed_hash_;
  std::filesystem::path state_directory_, state_file_;
  json defaults_, config_, slot_info_, players_, received_ = json::array();
  json data_packages_ = json::object();
  json name_groups_ = json::object();
  std::set<std::int64_t> all_locations_, checked_, pending_;
  int slot_ = 0, team_ = 0, percentage_ = -1;
  bool online_ = false, active_ = false, items_ready_ = false, finished_ = false;
  bool death_link_ = false;
  bool ready_ = false;
  int death_link_override_ = -1;
  double last_death_ = 0.0;
  std::chrono::steady_clock::time_point last_send_{};
};

}  // namespace gtavc
