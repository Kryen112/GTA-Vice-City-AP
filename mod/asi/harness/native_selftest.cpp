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
  for (wchar_t c : std::wstring(L"Vice City 123 /connect C:\\Games [chat] + ! ? &"))
    assert(ViceCityConsoleGlyph(c) == c);
  for (wchar_t c : std::wstring(L"_<>@^{}|~")) assert(ViceCityConsoleGlyph(c) == 0);
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
  NativeSession session(&game, logger, sender, "rando.vc", "", directory);
  login(session, connected);
  assert(game.AppliedItems().size() == 1);
  assert(game.Markers().size() == 2);
  assert(game.Markers().at(9102).category == 1);
  assert(game.Markers().at(9102).content_unlock_global == DistrictUnlockGlobal(kContentHiddenPackages, 0));
  assert(game.Markers().at(9103).content_unlock_global == DistrictUnlockGlobal(kContentHiddenPackages, 1));
  // All five lockable marker classes use their class/district cell; ambient
  // pickups, side events and shops remain independent of content locks.
  const auto marker_data = json::parse(kNativeData).at("markers");
  std::set<int> gated_classes;
  const std::map<int, int> marker_content = {{1, kContentHiddenPackages}, {2, kContentRobbableStores},
      {3, kContentRampages}, {5, kContentStuntJumps}, {6, kContentPropertyPurchases}};
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
                                [&](const ConsoleMessage& message) { colored = message; });
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
  const auto& continuation = long_popup.Advance(4250, 9, glyph_width);
  assert(continuation.size() == 2 && continuation.front().colors[0] == 5 && continuation.back().colors[0] == 6);
  assert(continuation.front().popup_until == 7500); // waiting lines start their clock when shown
  long_popup.Pause(10000);
  assert(long_popup.Advance(10001, 9, glyph_width).front().popup_until == 13250);
  assert(long_popup.Advance(13250, 9, glyph_width).empty() && long_popup.empty());
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
  assert(ConsolePopupAlpha(popup_until, 3500) == 255);
  assert(ConsolePopupAlpha(popup_until, 3875) == 127);
  assert(ConsolePopupAlpha(popup_until, 4250) == 0);
  assert(ConsolePopupAlpha(0, 1000) == 0);
  ConsolePopupQueue burst;
  for (int i = 0; i < 8; ++i) burst.Add({std::to_wstring(i), {0xAF99EF}});
  const auto& first_batch = burst.Advance(1000, 86);
  assert(first_batch.size() == 4 && first_batch.front().text == L"0" && first_batch.back().text == L"3");
  burst.Add({L"8", {0xAF99EF}});
  assert(burst.Advance(2000, 86).front().text == L"0"); // new arrivals cannot displace visible rows
  assert(burst.Advance(4249, 86).back().text == L"3");
  const auto& second_batch = burst.Advance(4250, 86);
  assert(second_batch.size() == 4 && second_batch.front().text == L"4" && second_batch.back().text == L"7");
  assert(second_batch.front().popup_until == 7500 && second_batch.front().colors[0] == 0xAF99EF);
  assert(burst.Advance(7500, 86).front().text == L"8");
  assert(burst.Advance(10750, 86).empty() && burst.empty());
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
  std::cout << "Native client checks passed\n";
}
