// Run with scripts/build_native_client.ps1 -Test (MSVC, Windows).
#include <cassert>
#include <array>
#include <fstream>
#include <iostream>
#include "fake_game_state.hpp"
#include "../src/native_session.hpp"
#include "../src/save_isolation.hpp"
#include "../src/scm_pickup_layout.hpp"
#include "../src/native_data.hpp"
#include "../src/console_font.hpp"
#include "../src/scm_effects.hpp"

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
  _set_error_mode(_OUT_TO_STDERR); // keep assertion failures in the test log
  std::cout << std::unitbuf;
  assert(argc == 2);
  // Test the marker parser and evaluator with both generated route tables.
  const auto native_tables = json::parse(kNativeData);
  json marker_config = {{"type", msg::kConfig}, {"item_globals", json::object()},
      {"completion_watch", json::object()}, {"config_globals", json::object()},
      {"check_markers", native_tables.at("markers")}};
  for (auto it = native_tables.at("markers").begin(); it != native_tables.at("markers").end(); ++it)
    marker_config["completion_watch"][it.key()] = std::stoll(it.key());
  TestGame marker_game;
  for (int split = 0; split < 2; ++split) {
    marker_config["marker_requirements"] = native_tables.at("marker_requirements")[split];
    assert(ApplyClientMessage(&marker_game, marker_config, [](const std::string&) {}));
    const auto knife = marker_game.Markers().at(9512);
    std::map<int, int> memory;
    const auto read = [&](int index) { return memory[index]; };
    assert(!knife.Available(read)); // The Job has not spawned the Malibu knife.
    memory[9376] = 1;
    assert(!knife.Available(read)); // The pickup district still holds the knife.
    memory[knife.content_unlock_global] = kDistrictReleased;
    assert(knife.Available(read));
    memory[9376] = 0; // Loading an older save must hide it again.
    assert(!knife.Available(read));
    // Every generated marker is satisfiable with all requirements met.
    for (const auto& [global, marker] : marker_game.Markers()) {
      memory.clear();
      for (const auto& threshold : marker.requirements)
        for (const auto& route : threshold.alternatives)
          for (const auto& term : route) memory[term.global] = std::max(memory[term.global], term.minimum);
      memory[marker.content_unlock_global] = kDistrictReleased;
      assert(marker.Available(read));
    }
  }
  CheckMarker route_marker;
  // All 35 rampage skulls restore from AP checks after New Game or an older save is loaded.
  int rampage_count = 0;
  const auto rampage_markers = marker_game.Markers();
  for (const auto& [global, marker] : rampage_markers) {
    if (marker.category != 3) continue;
    ++rampage_count;
    assert(CheckedRampageAt(rampage_markers, {global}, marker.x, marker.y) == global);
    assert(CheckedRampageAt(rampage_markers, {}, marker.x, marker.y) == 0);
    assert(CheckedRampageAt({}, {global}, marker.x, marker.y) == 0); // Class disabled.
    assert(CheckedRampageAt(rampage_markers, {global}, marker.x + 2.0f, marker.y) == 0);
    auto different_category = marker;
    different_category.category = 4;
    assert(CheckedRampageAt({{global, different_category}}, {global}, marker.x, marker.y) == 0);
  }
  assert(rampage_count == 35);
  std::map<int, int> restored_jumps;
  std::set<int> checked_jumps;
  for (const auto& [global, marker] : rampage_markers)
    if (marker.category == 5) checked_jumps.insert(global);
  assert(checked_jumps.size() == 36);
  const auto write_jump = [&](int global, int value) { restored_jumps[global] = value; };
  RestoreStuntJumpChecks(rampage_markers, {}, write_jump);
  assert(restored_jumps.empty()); // Failed or unfinished jumps remain available.
  RestoreStuntJumpChecks({}, checked_jumps, write_jump);
  assert(restored_jumps.empty()); // Disabled class.
  RestoreStuntJumpChecks(rampage_markers, checked_jumps, write_jump);
  assert(restored_jumps.size() == 36 && restored_jumps.at(9237) == 1 && restored_jumps.at(9272) == 1);
  restored_jumps.clear(); // Starting a new game must retain AP completion.
  RestoreStuntJumpChecks(rampage_markers, checked_jumps, write_jump);
  assert(restored_jumps.size() == 36);
  std::map<int, int> rampage_globals;
  const auto read_rampage = [&](int global) { return rampage_globals[global]; };
  const auto write_rampage = [&](int global, int value) { rampage_globals[global] = value; };
  std::set<int> checked_rampages;
  for (int index = 0; index < kRampageCount; ++index) checked_rampages.insert(kRampageCheckBase + index);
  assert(!RestoreRampageProgress({}, checked_rampages, read_rampage, write_rampage));
  assert(read_rampage(kRampagesCompletedGlobal) == 0); // Disabled class stays vanilla.
  rampage_globals[kRampagePassedBase + 1] = 1; // A rampage already in the loaded save.
  rampage_globals[kRampagesCompletedGlobal] = 1;
  assert(RestoreRampageProgress(rampage_markers, {kRampageCheckBase}, read_rampage, write_rampage));
  assert(read_rampage(kRampagesCompletedGlobal) == 2 && read_rampage(kRampageCheckBase) == 1);
  assert(!RestoreRampageProgress(rampage_markers, {kRampageCheckBase}, read_rampage, write_rampage));
  assert(read_rampage(kRampagesCompletedGlobal) == 2); // Repeated frames do not count twice.
  rampage_globals.clear(); // New Game resets GTA globals, but AP checks survive.
  assert(RestoreRampageProgress(rampage_markers, checked_rampages, read_rampage, write_rampage));
  assert(read_rampage(kRampagesCompletedGlobal) == 35);
  assert(!RestoreRampageProgress(rampage_markers, checked_rampages, read_rampage, write_rampage));
  route_marker.requirements = {{1, {{{10, 1, 20}, {11, 1, 0}}, {{12, 2, 0}}}}};
  std::map<int, int> route_memory{{20, 1}};
  const auto read_route = [&](int index) { return route_memory[index]; };
  assert(!route_marker.Available(read_route));
  route_memory[10] = 1; // Vehicle unlock alone is insufficient without its source.
  assert(!route_marker.Available(read_route));
  route_memory[11] = 1;
  assert(route_marker.Available(read_route));
  route_memory[10] = 0; route_memory[20] = 0; // Disabled ability lock is free.
  assert(route_marker.Available(read_route));
  route_memory[11] = 0; route_memory[12] = 1;
  assert(!route_marker.Available(read_route));
  route_memory[12] = 2; // Either complete route is enough.
  assert(route_marker.Available(read_route));
  route_marker.content_unlock_global = 30;
  assert(!route_marker.Available(read_route));
  route_memory[30] = kDistrictReleased;
  assert(route_marker.Available(read_route));
  for (const auto& bad_term : {json::array({65128, 1, 0}), json::array({4294976672LL, 1, 0}),
                              json::array({9376, 4294967297LL, 0}), json::array({9376, 1, -1})}) {
    marker_config["marker_requirements"]["9512"] = json::array({json::array({1, json::array({json::array({bad_term})})})});
    assert(!ApplyClientMessage(&marker_game, marker_config, [](const std::string&) {}));
  }
  ConsoleCommandCompletion completion;
  std::wstring command_text = L"/re";
  std::size_t command_cursor = command_text.size();
  assert(completion.Complete(command_text, command_cursor) && command_text == L"/ready");
  assert(completion.Complete(command_text, command_cursor) && command_text == L"/received");
  assert(completion.Complete(command_text, command_cursor, true) && command_text == L"/ready");
  assert(completion.Complete(command_text, command_cursor, true) && command_text == L"/received");
  completion.Reset(); // Editing starts a fresh prefix search.
  command_text = L"!hint_l Ocean Beach"; command_cursor = 7;
  assert(completion.Complete(command_text, command_cursor));
  assert(command_text == L"!hint_location Ocean Beach" && command_cursor == 14);
  command_cursor = command_text.size();
  assert(!completion.Complete(command_text, command_cursor)); // No argument completion.
  for (const auto text : {L"", L"hello", L"/unknown", L"/password secret"}) {
    completion.Reset(); command_text = text; command_cursor = command_text.size();
    assert(!completion.Complete(command_text, command_cursor) && command_text == text);
  }
  completion.Reset(); command_text = L"/re"; command_cursor = 3;
  assert(completion.Complete(command_text, command_cursor, true) && command_text == L"/received");
  completion.Reset(); command_text = L"/receXYZ"; command_cursor = 5;
  assert(completion.Complete(command_text, command_cursor) && command_text == L"/received");
  completion.Reset(); command_text = L"/re " + std::wstring(1020, L'x'); command_cursor = 3;
  const auto full_input = command_text;
  assert(!completion.Complete(command_text, command_cursor) && command_text == full_input);
  // Ocean Beach plaza bribe. Its vanilla script consumes the collection before
  // APPICKUP can see it; the ASI observes the ring first without clearing it.
  const std::vector<PickupTarget> pickup_targets = {{9399, 116.0, -1313.1, 4.4, 15, 375, 0}};
  PickupPoolEntry bribe{116.0f, -1313.1f, 4.4f, 15, 376, 9};
  std::array<std::uint32_t, 20> ring{};
  ring[0] = (7u << 16) | 9;
  assert(CollectedPickupCheck(pickup_targets, ring[0], 7, bribe) == 9399);
  assert(ring[0] == ((7u << 16) | 9)); // the vanilla consumer still gets its event
  ring[0] = 0; // vanilla consumes it; later CLEO polling would now miss it
  assert(CollectedPickupCheck(pickup_targets, ring[0], 7, bribe) == 0);
  assert(CollectedPickupCheck(pickup_targets, (6u << 16) | 9, 7, bribe) == 0);
  assert(CollectedPickupCheck(pickup_targets, (7u << 16) | 10, 7, bribe) == 0);
  assert(CollectedPickupCheck({}, (7u << 16) | 9, 7, bribe) == 0);
  bribe.x += 0.94f; // a foreign pickup near the slot must not count
  assert(CollectedPickupCheck(pickup_targets, (7u << 16) | 9, 7, bribe) == 0);
  bribe.x = 116.0f;
  bribe.pickup_type = 2;
  assert(CollectedPickupCheck(pickup_targets, (7u << 16) | 9, 7, bribe) == 0);
  bribe.pickup_type = 0; // collected one-shot pickup, still the same generation
  assert(CollectedPickupCheck(pickup_targets, (7u << 16) | 9, 7, bribe) == 9399);
  const auto directory = std::filesystem::path(argv[1]);
  std::filesystem::create_directories(directory);
  for (wchar_t c : std::wstring(L"Vice City 123 connect C:\\Games [chat] + ! ? &"))
    assert(ViceCityConsoleGlyph(c) == c);
  for (wchar_t c : std::wstring(L"/_<>@^{}|~")) assert(ViceCityConsoleGlyph(c) == 0);
  assert(ViceCityConsoleGlyph(L'\u00e9') == 0x9E); // accented letters keep the native font
  assert(ViceCityConsoleGlyph(L'\u00e4') == 0x9A);
  assert(ViceCityConsoleGlyph(L'\u00f1') == 0xAE);
  assert(ViceCityConsoleGlyph(L'\u20ac') == 0); // absent glyph uses Windows fallback
  // Exercise the actual Windows font path, including every keyboard symbol
  // that Vice City's fixed font cannot represent. Whitespace still advances.
  for (wchar_t c = 33; c <= 126; ++c) {
    ConsoleTextBitmap glyph(std::wstring(1, c), 10, 24);
    assert(glyph.pixels && glyph.advance > 0);
    assert(std::any_of(glyph.pixels, glyph.pixels + glyph.width * glyph.height,
                       [](std::uint32_t pixel) { return (pixel & 255) != 0; }));
  }
  ConsoleTextBitmap letter(L"a", 10, 24), spaced(L"a ", 10, 24), pair(L"ab", 10, 24);
  ConsoleTextBitmap slash(L"/", 10, 24);
  assert(slash.pixels && slash.advance == letter.advance);
  assert(spaced.advance == pair.advance && pair.advance > letter.advance);
  ConsoleTextBitmap accented(L"\u00e9\u00e4\u00f1", 10, 24);
  assert(accented.pixels);
  ConsoleTextBitmap preview(L"/slot player_name  C:\\Games\\Vice_City  ~ ! @ # $ % ^ & * [ ] { } | \u00e9", 10, 24);
  assert(preview.pixels);
  BITMAPFILEHEADER bmp{};
  bmp.bfType = 0x4D42;
  bmp.bfOffBits = sizeof(bmp) + sizeof(BITMAPINFOHEADER);
  bmp.bfSize = bmp.bfOffBits + preview.width * preview.height * 4;
  BITMAPINFOHEADER info{};
  info.biSize = sizeof(info); info.biWidth = preview.width; info.biHeight = -preview.height;
  info.biPlanes = 1; info.biBitCount = 32; info.biCompression = BI_RGB;
  std::ofstream font_preview(directory / "console-font.bmp", std::ios::binary);
  font_preview.write(reinterpret_cast<const char*>(&bmp), sizeof(bmp));
  font_preview.write(reinterpret_cast<const char*>(&info), sizeof(info));
  font_preview.write(reinterpret_cast<const char*>(preview.pixels), preview.width * preview.height * 4);
  font_preview.close();
  assert(NativeSeedHash("test-seed", "rando.vc") == "bd99f23ba1178029");
  TestGame game;
  std::vector<json> sent;
  bool transport = true;
  const auto sender = [&](const json& messages) {
    if (!transport) return false;
    for (const auto& message : messages) sent.push_back(message);
    return true;
  };
  std::vector<std::string> logs;
  const auto logger = [&](const std::string& text) { logs.push_back(text); std::cout << text << '\n'; };
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
  {
    TestGame menu_game;
    const auto menu_directory = directory / "main-menu-connection";
    std::filesystem::create_directories(menu_directory);
    bool prepared = false;
    NativeSession menu_session(&menu_game, logger, sender, "rando.vc", "", menu_directory,
        [&](const std::string&) { return prepared; });
    assert(!menu_session.Connected());
    menu_session.Handle({{"cmd", "RoomInfo"}, {"seed_name", "test-seed"}});
    assert(!menu_session.Connected());
    menu_session.Handle(connected);
    assert(menu_session.Connected() && !menu_game.ClientConnected());
    menu_session.Handle({{"cmd", "ReceivedItems"}, {"index", 0}, {"items", json::array({item})}});
    menu_session.Tick(true);
    assert(menu_session.Connected() && !menu_game.ClientConnected());
    assert(menu_game.AppliedItems().empty());
    prepared = true;
    menu_session.Tick(true);
    assert(menu_session.Connected() && menu_game.ClientConnected());
    assert(menu_game.AppliedItems().size() == 1);
    menu_session.Tick(false);
    assert(!menu_session.Connected() && !menu_game.ClientConnected());
    menu_session.Handle({{"cmd", "RoomInfo"}, {"seed_name", "test-seed"}});
    menu_session.Handle({{"cmd", "ConnectionRefused"}, {"errors", {"InvalidSlot"}}});
    assert(!menu_session.Connected());
  }
  {
    TestGame empty_game;
    const auto empty_directory = directory / "empty-inventory";
    std::filesystem::create_directories(empty_directory);
    NativeSession empty_session(&empty_game, logger, sender, "rando.vc", "", empty_directory);
    empty_session.Handle({{"cmd", "RoomInfo"}, {"seed_name", "test-seed"}});
    empty_game.ShowNotice(ToastNotice::kBridgeDown, "Archipelago client disconnected.");
    empty_session.Handle(connected);
    assert(empty_session.Connected());
    assert(empty_game.Notices()[ToastNoticeSlot(ToastNotice::kBridgeDown)].empty());
    empty_session.Tick(true);
    assert(!empty_game.ClientConnected());
    const auto trap_key = "gta_vice_city_consumed_traps_0_1_" + NativeSeedHash("test-seed", "rando.vc");
    empty_session.Handle({{"cmd", "Retrieved"}, {"keys", {{trap_key, nullptr}}}});
    empty_session.Tick(true);
    assert(empty_game.ClientConnected() && empty_game.AppliedItems().empty());
    empty_session.Handle({{"cmd", "ReceivedItems"}, {"index", 0}, {"items", json::array({item})}});
    assert(empty_game.AppliedItems().size() == 1);
    empty_session.Tick(false);
    assert(!empty_session.Connected() && !empty_game.ClientConnected());
  }
  {
    TestGame jump_game;
    const auto jump_directory = directory / "jump-markers";
    std::filesystem::create_directories(jump_directory);
    NativeSession jump_session(&jump_game, logger, sender, "rando.vc", "", jump_directory);
    auto config = connected;
    config["slot_data"]["completion_watch"] = {{"9268", 101}, {"9269", 102}};
    config["slot_data"]["check_markers"] = {
        {"9268", {453.1, -511.7, 5}}, {"9269", {464.8, -527.3, 5}}};
    login(jump_session, config);
    assert(std::abs(jump_game.Markers().at(9268).x - 464.8) < 0.01);
    assert(std::abs(jump_game.Markers().at(9269).x - 453.1) < 0.01);
    assert(!jump_game.Markers().at(9268).requirements.empty());
    config["slot_data"]["mission_shuffle"] = true;
    config["slot_data"]["marker_requirements"] = json::object();
    login(jump_session, config);
    assert(jump_game.Markers().at(9268).requirements.empty());
  }
  NativeSession session(&game, logger, sender, "rando.vc", "", directory);
  assert(!game.ClientConnected());
  login(session, connected);
  assert(game.ClientConnected());
  assert(game.AppliedItems().size() == 1);
  assert(game.Markers().size() == 2);
  assert(game.Markers().at(9102).category == 1);
  assert(game.Markers().at(9102).content_unlock_global == DistrictUnlockGlobal(kContentHiddenPackages, 0));
  assert(game.Markers().at(9103).content_unlock_global == DistrictUnlockGlobal(kContentHiddenPackages, 1));
  // Lockable marker classes use their class/district cell.
  // Side events and shops remain independent of content locks.
  const auto marker_data = json::parse(kNativeData).at("markers");
  std::set<int> gated_classes;
  const std::map<int, int> marker_content = {{1, kContentHiddenPackages}, {2, kContentRobbableStores},
      {3, kContentRampages}, {5, kContentStuntJumps}, {6, kContentPropertyPurchases},
      {4, kContentPickups}};
  for (const auto& marker : marker_data) {
    const int category = marker.at(2).get<int>();
    const auto content = marker_content.find(category);
    if (content == marker_content.end()) { assert(marker.size() == 3); continue; }
    const int district = marker.at(3).get<int>() - DistrictUnlockGlobal(content->second, 0);
    assert(district >= 0 && district < kDistrictCount);
    gated_classes.insert(content->second);
  }
  assert(gated_classes.size() == kContentCount);
  assert(game.Toasts().empty());
  game.landings = {0};
  session.Tick(true);
  assert(game.Toasts().empty() && game.landings.empty()); // receipt no longer draws a second notification
  assert(game.AppliedItems().size() == 1);
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
  assert(!game.ClientConnected());
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
  assert(game.Toasts().size() == 1); // non-item notifications still work
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

  // Chat and server output do not depend on game item/toast state.
  TestGame colored_game;
  ConsoleMessage colored;
  NativeSession colored_session(&colored_game, logger, sender, "rando.vc", "", directory / "colors", {},
                                [&](const ConsoleMessage& message, bool notify) { assert(notify); colored = message; });
  auto colored_config = connected;
  colored_config["slot_info"]["2"] = {{"group_members", {1}}};
  login(colored_session, colored_config);
  for (int receiving : {1, 3}) {
    colored_session.Handle({{"cmd", "PrintJSON"}, {"type", "ItemSend"}, {"item", item},
        {"receiving", receiving}, {"data", json::array({{{"text", "Item movement"}}})}});
    assert(colored.size() == 1 && colored[0].text == "Item movement");
    assert(colored_game.Toasts().empty()); // sent and received items use the new popup sink
  }
  const auto log_count = logs.size();
  colored_session.Handle({{"cmd", "PrintJSON"}, {"data", json::array({
    {{"type", "player_id"}, {"text", "1"}},
    {{"text", " sent "}},
    {{"type", "item_id"}, {"text", "542100000"}, {"player", 1}, {"flags", 7}},
    {{"type", "player_name"}, {"text", "Other player"}},
    {{"type", "item_name"}, {"text", "Useful"}, {"flags", 2}},
    {{"type", "item_name"}, {"text", "Trap"}, {"flags", 4}},
    {{"type", "item_name"}, {"text", "Filler"}},
    {{"type", "location_name"}, {"text", "Location"}},
    {{"type", "entrance_name"}, {"text", "Entrance"}},
    {{"type", "player_id"}, {"text", "2"}},
    {{"type", "color"}, {"color", "bold;orange"}, {"text", "Countdown"}},
    {{"type", "color"}, {"color", "unrecognized"}, {"text", "~r~literal"}},
    {{"type", "hint_status"}, {"hint_status", 0}, {"text", "unspecified"}},
    {{"type", "hint_status"}, {"hint_status", 10}, {"text", "no priority"}},
    {{"type", "hint_status"}, {"hint_status", 20}, {"text", "avoid"}},
    {{"type", "hint_status"}, {"hint_status", 30}, {"text", "priority"}},
    {{"type", "hint_status"}, {"hint_status", 40}, {"text", "found"}}
  })}});
  const std::vector<std::uint32_t> expected_colors = {
    0xEE00EE, 0xFFFFFF, 0xAF99EF, 0xFAFAD2, 0x6D8BE8, 0xFA8072, 0x00EEEE,
    0x00FF7F, 0x6495ED, 0xEE00EE, 0xFF7700, 0xFFFFFF,
    0xFFFFFF, 0x6D8BE8, 0xFA8072, 0xAF99EF, 0x00FF7F
  };
  assert(colored.size() == expected_colors.size());
  for (std::size_t i = 0; i < colored.size(); ++i) assert(colored[i].color == expected_colors[i]);
  assert(colored[0].text == "Rando" && colored[2].text != "542100000");
  assert(colored[11].text == "~r~literal"); // rendering escapes game tokens, not AP markup
  assert(logs.size() == log_count); // rich output is not repeated as a plain message
  colored_session.Handle({{"cmd", "Print"}, {"text", "Server announcement"}});
  assert(colored.size() == 1 && colored[0].text == "Server announcement" && colored[0].color == 0xFFFFFF);
  assert(logs.size() == log_count); // plain server notices also reach the popup/history sink once
  colored_session.Handle({{"cmd", "PrintJSON"}, {"data", json::array({
    {{"type", "color"}, {"color", "cyan"}, {"text", std::string(20000, 'x')}}, {{"text", "overflow"}}
  })}});
  assert(colored.size() == 1 && colored[0].text.size() == 16384);
  const auto wrapped = WrapConsoleText({std::wstring(60, L'a') + L" " + std::wstring(40, L'b') + L"\nTail",
      [] { std::vector<std::uint32_t> colors(61, 0xEE00EE); colors.insert(colors.end(), 45, 0x00FF7F); return colors; }()});
  assert(wrapped.size() == 3 && wrapped[0].text.size() == 60 && wrapped[1].text.size() == 40);
  assert(wrapped[2].text == L"Tail" && wrapped[0].colors.back() == 0xEE00EE);
  assert(wrapped[1].colors.front() == 0x00FF7F && wrapped[2].colors.back() == 0x00FF7F);
  const auto hard_wrap = WrapConsoleText({std::wstring(100, L'x'), std::vector<std::uint32_t>(100, 0xAF99EF)});
  assert(hard_wrap.size() == 2 && hard_wrap[0].text.size() == 86 && hard_wrap[1].colors.size() == 14);
  const ConsoleLine long_message{std::wstring(100, L'i'), std::vector<std::uint32_t>(100, 0xAF99EF)};
  const auto console_history = WrapConsoleText(long_message, static_cast<float>(long_message.text.size()));
  assert(console_history.size() == 1 && console_history[0].text == long_message.text);
  assert(WrapConsoleText(console_history[0], 590, [](std::wstring_view) { return 3.0f; }).size() == 1);
  assert(WrapConsoleText(console_history[0]).size() == 2); // Popup rows remain shorter.
  // Equal character counts have different widths in Vice City's proportional font.
  const auto glyph_width = [](std::wstring_view glyph) { return glyph == L"W" ? 9.0f : 3.0f; };
  const auto wide_rows = WrapConsoleText({L"WWWW", {1, 2, 3, 4}, 1234, 77}, 18, glyph_width);
  assert(wide_rows.size() == 2 && wide_rows[0].text == L"WW" && wide_rows[1].text == L"WW");
  assert(wide_rows[1].colors == std::vector<std::uint32_t>({3, 4}) && wide_rows[1].popup_until == 1234);
  assert(wide_rows[1].history_id == 77);
  ConsolePopupQueue long_popup;
  long_popup.Add({L"WWWWWW", {1, 2, 3, 4, 5, 6}});
  const auto& first_part = long_popup.Advance(1000, 9, glyph_width);
  assert(first_part.size() == 4 && first_part.front().colors[0] == 1 && first_part.back().colors[0] == 4);
  const auto& continuation = long_popup.Advance(4750, 9, glyph_width);
  assert(continuation.size() == 2 && continuation.front().colors[0] == 5 && continuation.back().colors[0] == 6);
  assert(continuation.front().popup_until == 8500); // waiting lines start their clock when shown
  long_popup.Pause(10000);
  assert(long_popup.Advance(10001, 9, glyph_width).front().popup_until == 13750);
  assert(long_popup.Advance(13750, 9, glyph_width).empty() && long_popup.empty());
  assert(WrapConsoleText({L"iiii", {1, 1, 1, 1}}, 18, glyph_width).size() == 1);
  const auto words = WrapConsoleText({L"WW iii", {1, 1, 1, 2, 2, 2}}, 27, glyph_width);
  assert(words.size() == 2 && words[0].text == L"WW" && words[1].text == L"iii");
  const auto blank = WrapConsoleText({L"a\n\nb", {1, 1, 1, 1}}, 18, glyph_width);
  assert(blank.size() == 3 && blank[1].text.empty() && WrapConsoleText(blank[1], 18, glyph_width).size() == 1);
  const auto unicode = WrapConsoleText({L"a\U0001f600b", {1, 2, 2, 3}}, 3, glyph_width);
  assert(unicode.size() == 3 && unicode[1].text == L"\U0001f600" && unicode[1].colors.size() == 2);
  assert(WrapConsoleText({L"W", {1}}, 1, glyph_width).size() == 1); // always make progress
  const auto popup_until = 1000 + kConsolePopupLifetimeMs;
  assert(ConsolePopupAlpha(popup_until, 1000) == 255);
  assert(ConsolePopupAlpha(popup_until, 4000) == 255);
  assert(ConsolePopupAlpha(popup_until, 4375) == 127);
  assert(ConsolePopupAlpha(popup_until, 4750) == 0);
  assert(ConsolePopupAlpha(0, 1000) == 0);
  ConsolePopupQueue burst;
  for (int i = 0; i < 8; ++i) burst.Add({std::to_wstring(i), {0xAF99EF}});
  const auto& first_batch = burst.Advance(1000, 86);
  assert(first_batch.size() == 4 && first_batch.front().text == L"0" && first_batch.back().text == L"3");
  burst.Add({L"8", {0xAF99EF}});
  assert(burst.Advance(2000, 86).front().text == L"0"); // new arrivals cannot displace visible rows
  assert(burst.Advance(4749, 86).back().text == L"3");
  const auto& second_batch = burst.Advance(4750, 86);
  assert(second_batch.size() == 4 && second_batch.front().text == L"4" && second_batch.back().text == L"7");
  assert(second_batch.front().popup_until == 8500 && second_batch.front().colors[0] == 0xAF99EF);
  assert(burst.Advance(8500, 86).front().text == L"8");
  assert(burst.Advance(12250, 86).empty() && burst.empty());
  assert(ConsoleScrollAfterArrival(0, 5, 105) == 0); // follow live chat only when already at the bottom
  assert(ConsoleScrollAfterArrival(12, 5, 105) == 17);
  assert(ConsoleScrollAfterArrival(12, 5, 100) == 17); // works when old history rows were trimmed
  assert(ConsoleScrollAfterArrival(82, 5, 100) == 82); // oldest retained page remains reachable
  reconnected.Handle({{"cmd", "Print"}, {"text", "Server announcement"}});
  assert(logs.back() == "Server announcement");
  for (const auto* type : {"Chat", "Hint", "Countdown", "Release", "Goal"}) {
    reconnected.Handle({{"cmd", "PrintJSON"}, {"type", type}, {"data", json::array({
      {{"type", "player_id"}, {"text", "1"}}, {{"text", " says hello"}}})}});
    assert(logs.back() == "Rando says hello");
  }
  reconnected.Command("hello room");
  assert(sent.back() == json({{"cmd", "Say"}, {"text", "hello room"}}));
  reconnected.Command("/hint Package");
  assert(sent.back().at("text") == "!hint Package");
  reconnected.Command("!release");
  assert(sent.back().at("text") == "!release");
  reconnected.Command("/deathlink off");
  assert(sent.back().at("tags") == json::array({"AP"}));
  reconnected.Command("/deathlink on");
  assert(sent.back().at("tags") == json::array({"AP", "DeathLink"}));
  auto count = sent.size();
  reconnected.Command("hello\n!release");
  reconnected.Command("/unknown");
  assert(sent.size() == count);
  reconnected.Tick(false);
  reconnected.Command("offline message");
  assert(sent.size() == count);

  bool save_ready = false;
  TestGame waiting;
  NativeSession waiting_session(&waiting, logger, sender, "rando.vc", "", directory,
      [&](const std::string& hash) { assert(hash == NativeSeedHash("test-seed", "rando.vc")); return save_ready; });
  login(waiting_session, connected);
  assert(waiting.AppliedItems().empty() && waiting.SeedHash().empty());
  save_ready = true;
  waiting_session.Tick(true);
  assert(waiting.AppliedItems().size() == 1);
  const auto documents = std::filesystem::absolute(directory);
  assert(SeedSaveDirectory(documents, "0123456789abcdef") == documents / "AP_Seeds" / "0123456789abcdef");
  for (const auto* invalid : {"", "../career", "FFFFFFFFFFFFFFFF", "0123456789abcde/"}) {
    bool rejected = false;
    try { SeedSaveDirectory(documents, invalid); } catch (const std::runtime_error&) { rejected = true; }
    assert(rejected);
  }
  // Consecutive pickups must both leave before the one-second retry timer.
  TestGame immediate;
  std::filesystem::create_directories(directory / "immediate");
  NativeSession immediate_session(&immediate, logger, sender, "rando.vc", "", directory / "immediate");
  login(immediate_session, connected);
  immediate_session.Tick(true); // start the periodic timer with no pending checks
  for (const auto location : {101, 102}) {
    sent.clear();
    immediate.QueueCheck(location);
    immediate_session.Tick(true);
    assert(std::any_of(sent.begin(), sent.end(), [&](const json& message) {
      if (message.at("cmd") != "LocationChecks") return false;
      const auto locations = message.at("locations").get<std::vector<int>>();
      return std::find(locations.begin(), locations.end(), location) != locations.end();
    }));
  }
  sent.clear();
  immediate.QueueCheck(102); // a repeated observation must not trigger another send
  immediate_session.Tick(true);
  assert(sent.empty());
  // Client-only commands: paginated local output, server-backed groups, and
  // state changes that survive reconnects without overwriting goal completion.
  TestGame command_game;
  std::vector<ConsoleMessage> output;
  std::vector<bool> notifications;
  const auto command_dir = directory / "commands";
  std::filesystem::create_directories(command_dir);
  NativeSession commands(&command_game, logger, sender, "rando.vc", "", command_dir, {},
      [&](const ConsoleMessage& row, bool notify) { output.push_back(row); notifications.push_back(notify); });
  login(commands, connected);
  assert(std::any_of(sent.begin(), sent.end(), [](const json& packet) {
    return packet.at("cmd") == "Get" && packet.at("keys").size() == 8;
  }));
  const std::string item_groups_key = "_read_item_name_groups_Grand Theft Auto Vice City";
  const std::string location_groups_key = "_read_location_name_groups_Grand Theft Auto Vice City";
  json groups_packet = {{"cmd", "Retrieved"}, {"keys", json::object()}};
  groups_packet["keys"][item_groups_key] = {{"Weapons", {"Pistol", "Shotgun"}}};
  groups_packet["keys"][location_groups_key] = {{"Ocean Beach", {"Docks", "Beach"}}};
  commands.Handle(groups_packet);
  const auto run_command = [&](const std::string& command) {
    output.clear(); notifications.clear();
    const auto sent_before = sent.size();
    commands.Command(command);
    assert(sent.size() == sent_before); // Browsing never chats or purchases a hint.
    assert(std::none_of(notifications.begin(), notifications.end(), [](bool notify) { return notify; }));
  };
  run_command("/item_groups");
  assert(output.size() == 2 && output[1][0].text == "Weapons");
  run_command("/item_groups Weapons");
  assert(output.size() == 3 && output[1][0].text == "Pistol");
  run_command("/location_groups Ocean Beach");
  assert(output.size() == 3 && output[1][0].text == "Beach");
  run_command("/locations 1 cortez");
  assert(output.size() > 1 && output.size() < 22);
  run_command("/items");
  assert(output.size() == 22 && output.back()[0].text == "Next: /items 2");
  const auto first_item = output[1][0].text;
  run_command("/items 2");
  assert(output[1][0].text != first_item);
  run_command("/items 0");
  assert(output.empty() && logs.back() == "Page must be a positive number.");
  run_command("/items 999999999999999999999999");
  assert(output.empty());
  run_command("/received 2");
  assert(output.empty() && logs.back().find("Page out of range") == 0);
  json history = json::array();
  for (int index = 0; index < 21; ++index) history.push_back(item);
  history[20]["location"] = -2;
  commands.Handle({{"cmd", "ReceivedItems"}, {"index", 0}, {"items", history}});
  run_command("/received");
  assert(output.size() == 22 && output[1][1].color == 0xAF99EF);
  run_command("/received 2");
  assert(output.size() == 2 && output[1][0].text == "21. " && output[1].back().text == "Starting inventory");
  commands.Command("/deathlink off");
  assert(sent.back().at("tags") == json::array({"AP"}));
  commands.Command("/deathlink seed");
  assert(sent.back().at("tags") == json::array({"AP", "DeathLink"}));
  auto no_deathlink = connected;
  no_deathlink["slot_data"]["death_link"] = false;
  login(commands, no_deathlink);
  assert(sent.back().at("cmd") == "ConnectUpdate" && sent.back().at("tags") == json::array({"AP"}));
  commands.Command("/ready");
  assert(sent.back() == json({{"cmd", "StatusUpdate"}, {"status", 10}}));
  login(commands, no_deathlink);
  assert(sent.back() == json({{"cmd", "StatusUpdate"}, {"status", 10}}));
  transport = false;
  commands.Command("/ready");
  assert(logs.back().find("Ready status was not changed") == 0);
  commands.Command("/deathlink on");
  assert(logs.back().find("DeathLink was not changed") == 0);
  transport = true;
  commands.Command("/ready");
  assert(sent.back().at("status") == 5); // Failed send did not change the toggle.
  commands.Command("/deathlink");
  assert(sent.back().at("tags") == json::array({"AP", "DeathLink"}));
  commands.Handle({{"cmd", "RoomUpdate"}, {"checked_locations", {102}}});
  const auto before_ready = sent.size();
  commands.Command("/ready");
  assert(sent.size() == before_ready && sent.back().at("status") == 30);
  commands.Handle({{"cmd", "Print"}, {"text", "Announcement"}});
  assert(notifications.back()); // Server popups still work.
  bool invalid_groups = false;
  groups_packet["keys"][item_groups_key] = {{"Weapons", {12}}};
  try { commands.Handle(groups_packet); }
  catch (const std::runtime_error&) { invalid_groups = true; }
  assert(invalid_groups);
  // Activity progress survives without a GTA save or a completed AP milestone.
  {
    const auto progress_directory = directory / "emergency-progress";
    const auto hash = NativeSeedHash("test-seed", "rando.vc");
    const auto key = [&](const char* activity) {
      return "gta_vice_city_emergency_0_1_" + hash + "_" + activity;
    };
    const auto cache_file = progress_directory / ("GtaVcAp." + hash + ".json");
    TestGame progress_game;
    NativeSession progress_session(&progress_game, logger, sender, "rando.vc", "", progress_directory);
    login(progress_session, connected);
    assert(std::any_of(sent.begin(), sent.end(), [&](const json& packet) {
      return packet.at("cmd") == "Get" &&
          std::find(packet.at("keys").begin(), packet.at("keys").end(), key("taxi")) != packet.at("keys").end();
    }));
    // Six fares survive even when the next AP milestone is at ten.
    progress_game.SetEmergencyProgress({6, 3, 20, 6, 4});
    progress_session.Tick(false);
    std::ifstream input(cache_file);
    const auto cached = json::parse(input);
    input.close();
    assert(cached.at("emergency_progress").at("0").at("taxi") == 6);
    assert(cached.at("emergency_progress").at("0").at("firefighter") == 20);

    TestGame restarted_game;
    NativeSession restarted_session(&restarted_game, logger, sender, "rando.vc", "", progress_directory);
    login(restarted_session, connected);
    assert((restarted_game.GetEmergencyProgress() == EmergencyProgress{6, 3, 20, 6, 4}));
    sent.clear();
    restarted_session.Tick(true);
    assert(std::any_of(sent.begin(), sent.end(), [&](const json& packet) {
      return packet.at("cmd") == "Set" && packet.at("key") == key("taxi") && packet.at("want_reply") == true &&
          packet.at("operations") == json::array({{{"operation", "max"}, {"value", 6}}});
    }));
    restarted_session.Handle({{"cmd", "Retrieved"}, {"keys", {
        {key("taxi"), 9}, {key("paramedic"), 5}, {key("firefighter"), 7},
        {key("vigilante"), 18}, {key("pizza"), nullptr}}}});
    assert((restarted_game.GetEmergencyProgress() == EmergencyProgress{9, 5, 20, 18, 4}));
    restarted_session.Handle({{"cmd", "SetReply"}, {"key", key("taxi")}, {"value", 2}});
    assert(restarted_game.GetEmergencyProgress()[0] == 9); // Stale replies never roll progress back.
    restarted_session.Tick(true);
    TestGame another_restart;
    NativeSession another_session(&another_restart, logger, sender, "rando.vc", "", progress_directory);
    login(another_session, connected);
    assert((another_restart.GetEmergencyProgress() == EmergencyProgress{9, 5, 20, 18, 4}));

    for (const auto& invalid : {json(-1), json(true), json(1.5), json("9"), json(2147483648LL)}) {
      bool rejected = false;
      try {
        another_session.Handle({{"cmd", "SetReply"}, {"key", key("taxi")}, {"value", invalid}});
      } catch (const std::runtime_error&) { rejected = true; }
      assert(rejected && another_restart.GetEmergencyProgress()[0] == 9);
    }
    for (const auto& activity : {"paramedic", "pizza"}) {
      bool rejected = false;
      try {
        another_session.Handle({{"cmd", "SetReply"}, {"key", key(activity)}, {"value", 13}});
      } catch (const std::runtime_error&) { rejected = true; }
      assert(rejected);
    }

    TestGame remote_only_game;
    NativeSession remote_only(&remote_only_game, logger, sender, "rando.vc", "", directory / "remote-only");
    login(remote_only, connected);
    remote_only.Handle({{"cmd", "Retrieved"}, {"keys", {{key("taxi"), 9}, {key("vigilante"), 18}}}});
    assert((remote_only_game.GetEmergencyProgress() == EmergencyProgress{9, 0, 0, 18, 0}));
    remote_only.Tick(true);

    auto other_team_config = connected;
    other_team_config["team"] = 1;
    TestGame other_team_game;
    NativeSession other_team(&other_team_game, logger, sender, "rando.vc", "", progress_directory);
    login(other_team, other_team_config);
    assert(other_team_game.GetEmergencyProgress() == EmergencyProgress{});
    other_team_game.SetEmergencyProgress({1, 0, 0, 0, 0});
    other_team.Tick(true);
    TestGame original_team_game;
    NativeSession original_team(&original_team_game, logger, sender, "rando.vc", "", progress_directory);
    login(original_team, connected);
    assert((original_team_game.GetEmergencyProgress() == EmergencyProgress{9, 5, 20, 18, 4}));

    TestGame other_seed_game;
    NativeSession other_seed_session(&other_seed_game, logger, sender, "rando.vc", "", progress_directory);
    other_seed_session.Handle({{"cmd", "RoomInfo"}, {"seed_name", "another-seed"}});
    other_seed_session.Handle(connected);
    other_seed_session.Handle({{"cmd", "ReceivedItems"}, {"index", 0}, {"items", json::array({item})}});
    assert(other_seed_game.GetEmergencyProgress() == EmergencyProgress{});

    const auto temporary = std::filesystem::path(cache_file.wstring() + L".tmp");
    std::filesystem::create_directory(temporary);
    another_restart.SetEmergencyProgress({11, 5, 20, 18, 4});
    bool failed = false;
    try { another_session.Tick(false); } catch (const std::exception&) { failed = true; }
    assert(failed);
    std::filesystem::remove(temporary);
    another_session.Tick(false); // Failed writes stay dirty and retry while offline.
    std::ifstream retried(cache_file);
    assert(json::parse(retried).at("emergency_progress").at("0").at("taxi") == 11);
  }
  // Consumed receipts survive New Game, disconnects, and process restarts.
  const auto trap_directory = directory / "traps";
  std::filesystem::create_directories(trap_directory);
  TestGame trap_game;
  NativeSession trap_session(&trap_game, logger, sender, "rando.vc", "", trap_directory);
  const std::string trap_key = "gta_vice_city_consumed_traps_0_1_bd99f23ba1178029";
  const auto retrieved_traps = [&](const json& value) {
    return json{{"cmd", "Retrieved"}, {"keys", {{trap_key, value}}}};
  };
  login(trap_session, connected);
  assert(trap_game.ConsumeTrap(7) == TrapAction::kWait);
  trap_session.Handle(retrieved_traps(nullptr));
  assert(trap_game.ConsumeTrap(7) == TrapAction::kApply);
  assert(trap_game.ConsumeTrap(7) == TrapAction::kSkip);
  transport = false;
  trap_session.Tick(false); // Local consumption survives an unconfirmed server write.
  assert(trap_game.ConsumeTrap(6) == TrapAction::kApply); // Already queued during the outage.
  transport = true;
  login(trap_session, connected);
  assert(trap_game.ConsumeTrap(7) == TrapAction::kWait);
  trap_session.Handle(retrieved_traps(nullptr));
  assert(trap_game.ConsumeTrap(7) == TrapAction::kSkip);
  sent.clear();
  trap_session.Tick(true);
  assert(std::any_of(sent.begin(), sent.end(), [&](const json& packet) {
    return packet.at("cmd") == "Set" && packet.at("key") == trap_key &&
        packet.at("want_reply") == true && packet.at("operations") ==
        json::array({{{"operation", "update"}, {"value", {{"6", true}, {"7", true}}}}});
  }));
  trap_session.Handle({{"cmd", "SetReply"}, {"key", trap_key}, {"value", {{"6", true}, {"7", true}, {"9", true}}}});
  assert(trap_game.ConsumeTrap(9) == TrapAction::kSkip); // Another client's consumed receipt.
  assert(trap_game.ConsumeTrap(10) == TrapAction::kApply); // Another copy still triggers.
  TrapHistory restarted(trap_directory / "GtaVcAp.bd99f23ba1178029.0.traps.json");
  restarted.Merge({{"6", true}, {"7", true}, {"9", true}});
  assert(restarted.Pending() == json({{"10", true}}));
  restarted.Merge({{"6", true}, {"7", true}, {"9", true}, {"10", true}});
  assert(restarted.Pending().empty());
  const std::map<std::int64_t, ItemEffect> trap_effects = {
      {1, {"trap_wanted", 1}}, {2, {"money", 100}}};
  const std::vector<std::pair<std::int64_t, std::int64_t>> trap_items = {
      {0, 99}, {7, 1}, {8, 2}, {10, 1}, {11, 1}};
  const auto fresh_game = PlanEffects(trap_items, trap_effects, 0, true, 10);
  assert((fresh_game.received_indices == std::vector<std::int64_t>{7, 8, 10, 11}));
  assert(fresh_game.new_applied_index == 4 && fresh_game.to_apply[1].type == "money");
  assert(restarted.Consume(fresh_game.received_indices[0]) == TrapAction::kSkip);
  assert(restarted.Consume(fresh_game.received_indices[2]) == TrapAction::kSkip);
  assert(restarted.Consume(fresh_game.received_indices[3]) == TrapAction::kApply);
  TrapHistory other_seed(trap_directory / "other-seed.json");
  other_seed.Merge(nullptr);
  assert(other_seed.Consume(7) == TrapAction::kApply);
  for (const auto& invalid : {json::array(), json({{"-1", true}}),
                             json({{"07", true}}), json({{"12", false}})}) {
    bool rejected = false;
    try { restarted.Merge(invalid); } catch (const std::runtime_error&) { rejected = true; }
    assert(rejected && restarted.Consume(7) == TrapAction::kSkip);
  }
  // A failed cache write must defer the trap without marking it consumed.
  const auto blocked_temporary = trap_directory / "blocked.json.tmp";
  std::filesystem::create_directory(blocked_temporary);
  TrapHistory blocked(trap_directory / "blocked.json");
  blocked.Merge(nullptr);
  bool write_failed = false;
  try { blocked.Consume(7); } catch (const std::exception&) { write_failed = true; }
  assert(write_failed && blocked.Pending().empty());
  std::filesystem::remove(blocked_temporary);
  assert(blocked.Consume(7) == TrapAction::kApply);
  std::cout << "Native client checks passed\n";
}
