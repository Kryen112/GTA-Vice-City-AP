// The ASI side of the bridge: a background thread that connects to the client
// listener with retry, performs the hello/welcome handshake, applies inbound
// items and checked and toast messages to the game, and sends the game's new
// checks and goal upward. No plugin-sdk dependency, so the console harness
// drives it against the real Python bridge with no game.
#pragma once

#include <atomic>
#include <functional>
#include <string>
#include <thread>

#include "net.hpp"
#include "protocol.hpp"

namespace gtavc {

class GameState;

using Logger = std::function<void(const std::string&)>;

class BridgeClient {
 public:
  BridgeClient(std::string host, int port, GameState* game, Logger logger);
  ~BridgeClient();
  BridgeClient(const BridgeClient&) = delete;
  BridgeClient& operator=(const BridgeClient&) = delete;

  void Start();
  void Stop();

 private:
  void RunLoop();
  bool RunSession();
  bool SendMessage(const json& message);
  void HandleMessage(const json& message);
  void PumpOutbound();
  void SleepInterruptible(int milliseconds);

  std::string host_;
  int port_;
  GameState* game_;
  Logger logger_;
  TcpClient client_;
  MessageReader reader_;
  MessageWriter writer_;
  std::thread thread_;
  std::atomic<bool> stop_{false};
};

}  // namespace gtavc
