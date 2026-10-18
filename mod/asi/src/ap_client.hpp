#pragma once

#include <atomic>
#include <filesystem>
#include <thread>
#include <mutex>
#include <deque>
#include <charconv>
#include <string_view>
#include <stdexcept>
#include "native_session.hpp"

namespace gtavc {

inline std::string ServerWithPort(std::string server, std::string_view port) {
  if (port.empty() || port.size() > 5) throw std::runtime_error("Port must be 1..65535.");
  unsigned value = 0;
  const auto parsed = std::from_chars(port.data(), port.data() + port.size(), value);
  if (parsed.ec != std::errc() || parsed.ptr != port.data() + port.size() ||
      value == 0 || value > 65535) throw std::runtime_error("Port must be 1..65535.");
  const auto scheme = server.find("://");
  const auto start = scheme == std::string::npos ? 0 : scheme + 3;
  if (start == server.size()) throw std::runtime_error("Set a server host first.");
  if (server[start] == '[') {
    const auto end = server.find(']', start);
    if (end == std::string::npos) throw std::runtime_error("Invalid IPv6 server address.");
    server.erase(end + 1);
  } else {
    const auto colon = server.find(':', start);
    if (colon != std::string::npos) {
      if (server.find(':', colon + 1) != std::string::npos)
        throw std::runtime_error("Put IPv6 server addresses in brackets.");
      server.erase(colon);
    }
  }
  return server + ':' + std::string(port);
}

class ArchipelagoClient {
 public:
  ArchipelagoClient(GameState* game, Logger logger,
                    std::function<bool(const std::string&)> prepare_seed = {},
                    std::filesystem::path state_directory = {}, ConsoleOutput console = {},
                    CompletionOutput completion = {});
  ~ArchipelagoClient();
  void Start();
  void Stop();
  void Command(std::string text);
  bool Connected() const { return connected_; }

 private:
  void Run();
  GameState* game_;
  Logger logger_;
  ConsoleOutput console_;
  CompletionOutput completion_;
  std::function<bool(const std::string&)> prepare_seed_;
  std::filesystem::path state_directory_;
  std::mutex mutex_;
  std::deque<std::string> commands_;
  std::atomic<bool> stop_{false};
  std::atomic<bool> connected_{false};
  std::thread thread_;
};

}  // namespace gtavc
