// Run with scripts/build_native_client.ps1 -Test (MSVC, Windows).
#include <cassert>
#include <fstream>
#include <iostream>
#include "fake_game_state.hpp"
#include "../src/native_session.hpp"

using namespace gtavc;

struct TestGame : FakeGameState {
  TestGame() : FakeGameState("") {}
  std::vector<std::int64_t> landings;
  std::string loaded;
  std::string SeedHash() override { return loaded.empty() ? FakeGameState::SeedHash() : loaded; }
  std::vector<std::int64_t> TakeAppliedReports() override {
    auto result = landings;
    landings.clear();
    return result;
  }
};

int main(int argc, char** argv) {
  assert(argc == 2);
  const auto directory = std::filesystem::path(argv[1]);
  std::filesystem::create_directories(directory);
  assert(NativeSeedHash("test-seed", "rando.vc") == "bd99f23ba1178029");
  TestGame game;
  std::vector<json> sent;
  bool transport = true;
  const auto sender = [&](const json& messages) {
    if (!transport) return false;
    for (const auto& message : messages) sent.push_back(message);
    return true;
  };
  const auto logger = [](const std::string& text) { std::cout << text << '\n'; };
  auto connected = json{
      {"cmd", "Connected"}, {"slot", 1}, {"team", 0},
      {"slot_info", {{"1", {{"name", "rando.vc"}, {"game", "Grand Theft Auto Vice City"}}}}},
      {"players", json::array({{{"slot", 1}, {"team", 0}, {"alias", "Rando"}}})},
      {"missing_locations", {101, 102}}, {"checked_locations", json::array()},
      {"slot_data", {{"item_globals", {{"542100000", 9005}}},
                     {"config_globals", json::object()},
                     {"completion_watch", {{"9102", 101}, {"9103", 102}, {"9104", 103}}},
                     {"goal", "final_mission"}, {"final_location_id", 102}, {"death_link", true}}}};
  const auto item = json{{"item", 542100000}, {"location", 101}, {"player", 1}, {"flags", 1}};
  const auto login = [&](NativeSession& session, json config) {
    session.Handle({{"cmd", "RoomInfo"}, {"seed_name", "test-seed"}});
    assert(sent.back().at("cmd") == "Connect");
    assert(sent.back().at("name") == "rando.vc");
    assert(sent.back().at("items_handling") == 7);
    session.Handle(config);
    session.Handle({{"cmd", "ReceivedItems"}, {"index", 0}, {"items", json::array({item})}});
  };
  NativeSession session(&game, logger, sender, "rando.vc", "", directory);
  login(session, connected);
  assert(game.AppliedItems().size() == 1);
  assert(game.Markers().size() == 2);
  assert(game.Markers().at(9102).category == 1);
  assert(game.Toasts().empty());
  game.landings = {0};
  session.Tick(true);
  assert(game.Toasts().size() == 1);
  session.Handle({{"cmd", "ReceivedItems"}, {"index", 3}, {"items", json::array({item})}});
  assert(sent.back().at("cmd") == "Sync");
  assert(game.AppliedItems().size() == 1);
  session.Handle({{"cmd", "ReceivedItems"}, {"index", 1}, {"items", json::array({item})}});
  session.Handle({{"cmd", "ReceivedItems"}, {"index", 1}, {"items", json::array({item})}});
  assert(game.AppliedItems().size() == 2); // Duplicate batches preserve indices.
  transport = false;
  game.QueueCheck(101);
  game.QueuePercentage(42);
  session.Tick(false);
  const auto state = directory / ("GtaVcAp." + NativeSeedHash("test-seed", "rando.vc") + ".json");
  auto saved = json::parse(std::ifstream(state));
  assert(saved.at("checks") == json::array({101}));
  assert(saved.at("percentage") == 42);
  transport = true;
  NativeSession reconnected(&game, logger, sender, "rando.vc", "", directory);
  login(reconnected, connected);
  reconnected.Tick(true);
  assert(std::any_of(sent.begin(), sent.end(), [](const json& message) {
    return message.at("cmd") == "LocationChecks" && message.at("locations") == json::array({101});
  }));
  reconnected.Handle({{"cmd", "RoomUpdate"}, {"checked_locations", {101}}});
  saved = json::parse(std::ifstream(state));
  assert(saved.at("checks").empty());
  game.QueueDeath();
  reconnected.Tick(true);
  const auto death = sent.back();
  assert(death.at("cmd") == "Bounce");
  reconnected.Handle({{"cmd", "Bounced"}, {"tags", {"DeathLink"}}, {"data", death.at("data")} });
  assert(game.DeathLinks().empty());
  auto data = death.at("data");
  data["time"] = data.at("time").get<double>() + 1;
  data["source"] = "Other Player";
  reconnected.Handle({{"cmd", "Bounced"}, {"tags", {"DeathLink"}}, {"data", data}});
  assert(game.DeathLinks() == std::vector<std::string>{"Other Player"});
  reconnected.Handle({{"cmd", "RoomUpdate"}, {"checked_locations", {102}}});
  assert(std::any_of(sent.begin(), sent.end(), [](const json& message) {
    return message.at("cmd") == "StatusUpdate" && message.at("status") == 30;
  }));
  TestGame wrong;
  wrong.loaded = "ffffffffffffffff";
  NativeSession refused(&wrong, logger, sender, "rando.vc", "", directory);
  login(refused, connected);
  assert(wrong.AppliedItems().empty() && wrong.ConfigGlobals().empty());
  assert(!wrong.Notices()[ToastNoticeSlot(ToastNotice::kHandshakeRefusal)].empty());
  assert(!ApplyClientMessage(&game, {{"type", "config"}, {"item_globals", {{"1", -1}}},
                                    {"completion_watch", json::object()}}, logger));
  assert(game.ItemGlobals().count(542100000)); // Rejected config was atomic.
  TestGame hunt;
  NativeSession hunt_session(&hunt, logger, sender, "rando.vc", "", directory);
  auto hunt_config = connected;
  hunt_config["slot_data"]["goal"] = "hidden_packages";
  hunt_config["slot_data"]["hidden_packages_required"] = 1;
  hunt_config["slot_data"]["hidden_package_item_id"] = 542100000;
  login(hunt_session, hunt_config);
  assert(hunt.Status().goal_reached && hunt.Status().finale_warp);
  TestGame hundred;
  NativeSession hundred_session(&hundred, logger, sender, "rando.vc", "", directory);
  auto hundred_config = connected;
  hundred_config["slot_data"]["goal"] = "hundred_percent";
  hundred_config["slot_data"]["goal_uncounted_locations"] = {102};
  login(hundred_session, hundred_config);
  assert(!hundred.Status().goal_reached);
  hundred_session.Handle({{"cmd", "RoomUpdate"}, {"checked_locations", {101}}});
  assert(hundred.Status().goal_reached);
  std::cout << "Native client checks passed\n";
}
