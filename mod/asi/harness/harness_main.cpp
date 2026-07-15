// Console harness: runs the real ASI bridge against the Python client with a
// fake game state, so C++ to Python interop is verified with no game. It
// connects, completes the handshake, receives the resync, emits one check, and
// prints a JSON summary of everything the bridge applied for the Python driver
// to assert.
#include <chrono>
#include <iostream>
#include <string>
#include <thread>

#include "../src/bridge.hpp"
#include "../third_party/json.hpp"
#include "fake_game_state.hpp"

using gtavc::BridgeClient;
using gtavc::FakeGameState;
using json = nlohmann::json;

namespace {

std::string ArgValue(int argc, char** argv, const std::string& flag, const std::string& fallback) {
  for (int index = 1; index + 1 < argc; ++index) {
    if (flag == argv[index]) return argv[index + 1];
  }
  return fallback;
}

}  // namespace

int main(int argc, char** argv) {
  const std::string host = ArgValue(argc, argv, "--host", "127.0.0.1");
  const int port = std::stoi(ArgValue(argc, argv, "--port", "52300"));
  const std::string seed_hash = ArgValue(argc, argv, "--seed-hash", "");
  const long long emit_check = std::stoll(ArgValue(argc, argv, "--emit-check", "-1"));
  const int run_ms = std::stoi(ArgValue(argc, argv, "--run-ms", "1500"));

  FakeGameState game(seed_hash);
  BridgeClient bridge(host, port, &game,
                      [](const std::string& line) { std::cerr << "[bridge] " << line << "\n"; });
  bridge.Start();

  // Let the handshake and resync complete, then emit a check upward.
  std::this_thread::sleep_for(std::chrono::milliseconds(400));
  if (emit_check >= 0) game.QueueCheck(emit_check);
  std::this_thread::sleep_for(std::chrono::milliseconds(run_ms > 400 ? run_ms - 400 : 100));

  bridge.Stop();

  json summary;
  summary["welcome_seed_hash"] = game.StampedSeedHash();
  summary["items"] = json::array();
  for (const auto& item : game.AppliedItems()) {
    summary["items"].push_back(json::array({item.first, item.second}));
  }
  summary["checked"] = game.Checked();
  summary["toasts"] = game.Toasts();
  summary["item_globals"] = json::object();
  for (const auto& entry : game.ItemGlobals()) {
    summary["item_globals"][std::to_string(entry.first)] = entry.second;
  }
  summary["completion_watch"] = json::object();
  for (const auto& entry : game.CompletionWatch()) {
    summary["completion_watch"][std::to_string(entry.first)] = entry.second;
  }
  summary["item_effects"] = json::object();
  for (const auto& entry : game.ItemEffects()) {
    json descriptor = json::array({entry.second.type});
    if (entry.second.type == "cash") descriptor.push_back(entry.second.amount);
    summary["item_effects"][std::to_string(entry.first)] = descriptor;
  }
  summary["config_globals"] = json::object();
  for (const auto& entry : game.ConfigGlobals()) {
    summary["config_globals"][std::to_string(entry.first)] = entry.second;
  }
  std::cout << summary.dump() << "\n";
  return 0;
}
