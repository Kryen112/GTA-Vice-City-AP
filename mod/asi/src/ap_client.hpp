#pragma once

#include <atomic>
#include <filesystem>
#include <thread>
#include <mutex>
#include <deque>
#include "native_session.hpp"

namespace gtavc {

class ArchipelagoClient {
 public:
  ArchipelagoClient(GameState* game, Logger logger,
                    std::function<bool(const std::string&)> prepare_seed = {},
                    std::filesystem::path state_directory = {}, ConsoleOutput console = {});
  ~ArchipelagoClient();
  void Start();
  void Stop();
  void Command(std::string text);

 private:
  void Run();
  GameState* game_;
  Logger logger_;
  ConsoleOutput console_;
  std::function<bool(const std::string&)> prepare_seed_;
  std::filesystem::path state_directory_;
  std::mutex mutex_;
  std::deque<std::string> commands_;
  std::atomic<bool> stop_{false};
  std::thread thread_;
};

}  // namespace gtavc
