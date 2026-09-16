#include <chrono>
#include <iostream>
#include <thread>
#include "fake_game_state.hpp"
#include "../src/ap_client.hpp"

int main(int, char** argv) {
  gtavc::FakeGameState game("");
  gtavc::ArchipelagoClient client(&game, [](const std::string& line) {
    std::cout << line << std::endl;
  }, {}, std::filesystem::absolute(argv[0]).parent_path() / "state");
  client.Start();
  bool queued = false;
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(20);
  while (std::chrono::steady_clock::now() < deadline) {
    if (!queued && !game.AppliedItems().empty()) {
      client.Command("hello from the ASI");
      client.Command("/hint Package");
      game.QueueCheck(101);
      queued = true;
    }
    if (game.Status().goal_reached && game.AppliedItems().size() == 2) {
      std::this_thread::sleep_for(std::chrono::milliseconds(200));
      client.Stop();
      std::cout << "Native WebSocket integration passed" << std::endl;
      return 0;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(25));
  }
  client.Stop();
  for (const auto& notice : game.Notices()) std::cerr << notice << '\n';
  return 1;
}
