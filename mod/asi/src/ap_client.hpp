#pragma once

#include <atomic>
#include <filesystem>
#include <thread>
#include "native_session.hpp"

namespace gtavc {

class ArchipelagoClient {
 public:
  ArchipelagoClient(GameState* game, Logger logger);
  ~ArchipelagoClient();
  void Start();
  void Stop();

 private:
  void Run();
  GameState* game_;
  Logger logger_;
  std::atomic<bool> stop_{false};
  std::thread thread_;
};

}  // namespace gtavc
