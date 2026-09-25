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
  bool commands_queued = false;
  bool check_queued = false;
  auto commands_queued_at = std::chrono::steady_clock::time_point{};
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(20);
  while (std::chrono::steady_clock::now() < deadline) {
    if (!commands_queued && game.ClientConnected() && !game.AppliedItems().empty()) {
      client.Command("hello from the ASI");
      client.Command("/hint Package");
      commands_queued_at = std::chrono::steady_clock::now();
      commands_queued = true;
    }
    if (commands_queued && !check_queued && game.ClientConnected() &&
        std::chrono::steady_clock::now() - commands_queued_at >= std::chrono::milliseconds(200)) {
      game.QueueCheck(101);
      game.CompleteGoalLocation(101);
      check_queued = true;
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
