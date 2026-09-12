#include "native_session.hpp"

#include <algorithm>
#include <charconv>
#include <cctype>
#include <fstream>
#include <windows.h>
#include <bcrypt.h>
#include "native_data.hpp"

#pragma comment(lib, "bcrypt.lib")

namespace gtavc {
namespace {
constexpr const char* kGame = "Grand Theft Auto Vice City";

// Archipelago NetUtils.JSONtoTextParser / the Python client's default palette.
std::uint32_t ConsoleColor(const std::string& names) {
  static const std::pair<const char*, std::uint32_t> colors[] = {
    {"black", 0x000000}, {"red", 0xEE0000}, {"green", 0x00FF7F}, {"yellow", 0xFAFAD2},
    {"blue", 0x6495ED}, {"magenta", 0xEE00EE}, {"cyan", 0x00EEEE}, {"slateblue", 0x6D8BE8},
    {"plum", 0xAF99EF}, {"salmon", 0xFA8072}, {"white", 0xFFFFFF}, {"orange", 0xFF7700}
  };
  // AP permits semicolon-separated color/style names. Ignore unknown styles.
  for (std::size_t start = 0; start < names.size();) {
    const auto end = names.find(';', start);
    const auto name = names.substr(start, end == std::string::npos ? end : end - start);
    for (const auto& color : colors) if (name == color.first) return color.second;
    if (end == std::string::npos) break;
    start = end + 1;
  }
  return 0xFFFFFF;
}

bool Enabled(const json& value) {
  return value == true || value == 1;
}

double Now() {
  return std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
}
}  // namespace

std::string NativeSeedHash(const std::string& seed, const std::string& slot) {
  std::string input = seed + '\x1f' + slot;
  unsigned char digest[32];
  if (BCryptHash(BCRYPT_SHA256_ALG_HANDLE, nullptr, 0,
                 reinterpret_cast<PUCHAR>(input.data()), static_cast<ULONG>(input.size()),
                 digest, sizeof(digest)) < 0) throw std::runtime_error("Cannot hash the seed identity");
  std::string result;
  for (int index = 0; index < 8; ++index) {
    result += "0123456789abcdef"[digest[index] >> 4];
    result += "0123456789abcdef"[digest[index] & 15];
  }
  return result;
}

NativeSession::NativeSession(GameState* game, Logger logger, Sender send,
                             std::string slot_name, std::string password,
                             std::filesystem::path state_directory,
                             std::function<bool(const std::string&)> prepare_seed, ConsoleOutput console)
    : game_(game), logger_(std::move(logger)), console_(std::move(console)), send_(std::move(send)),
      prepare_seed_(std::move(prepare_seed)),
      slot_name_(std::move(slot_name)), password_(std::move(password)),
      state_directory_(std::move(state_directory)), defaults_(json::parse(kNativeData)) {}

bool NativeSession::Send(json message) {
  return send_(json::array({std::move(message)}));
}

bool NativeSession::SeedMatches() const {
  const std::string loaded = game_->SeedHash();
  return !seed_hash_.empty() && (loaded.empty() || loaded == seed_hash_);
}

void NativeSession::PersistChecks() {
  if (state_file_.empty()) return;
  const std::filesystem::path temporary = state_file_.wstring() + L".tmp";
  std::ofstream file(temporary, std::ios::binary | std::ios::trunc);
  file.exceptions(std::ios::failbit | std::ios::badbit);
  file << json({{"seed_hash", seed_hash_}, {"checks", pending_}, {"percentage", percentage_}}).dump();
  file.close();
  if (!MoveFileExW(temporary.c_str(), state_file_.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
    throw std::runtime_error("Cannot persist pending Archipelago checks");
}

bool NativeSession::Activate() {
  if (!online_ || !items_ready_) return false;
  if (!SeedMatches()) {
    game_->ShowNotice(ToastNotice::kHandshakeRefusal,
                     "Wrong seed save loaded. Load this seed's save or start a new game.");
    return false;
  }
  if (prepare_seed_ && !prepare_seed_(seed_hash_)) return false;
  json configuration = config_;
  configuration["type"] = msg::kConfig;
  for (const char* field : {"item_globals", "completion_watch", "config_globals"}) {
    if (!configuration.contains(field) || !configuration[field].is_object())
      throw std::runtime_error(std::string("Slot data is missing ") + field);
  }
  configuration["check_markers"] = json::object();
  configuration["marker_requirements"] = defaults_.at("marker_requirements").at(
      Enabled(config_.value("split_mainland_access", json(false))) ? 1 : 0);
  for (auto entry = defaults_["markers"].begin(); entry != defaults_["markers"].end(); ++entry) {
    const auto watched = configuration["completion_watch"].find(entry.key());
    if (watched == configuration["completion_watch"].end() || !watched->is_number_integer() ||
        !all_locations_.count(watched->get<std::int64_t>())) continue;
    json marker = entry.value();
    if (config_.contains("check_markers") && config_["check_markers"].is_object()) {
      const auto supplied = config_["check_markers"].find(entry.key());
      if (supplied != config_["check_markers"].end() && supplied->is_array() && supplied->size() >= 2) {
        marker[0] = (*supplied)[0];
        marker[1] = (*supplied)[1];
      }
    }
    configuration["check_markers"][entry.key()] = marker;
  }
  state_file_ = state_directory_ / ("GtaVcAp." + seed_hash_ + ".json");
  if (std::filesystem::exists(state_file_)) {
    std::ifstream file(state_file_, std::ios::binary);
    const json stored = json::parse(file);
    if (stored.value("seed_hash", std::string()) != seed_hash_)
      throw std::runtime_error("Pending checks belong to another seed");
    for (const auto location : stored.at("checks").get<std::set<std::int64_t>>())
      if (all_locations_.count(location) && !checked_.count(location)) pending_.insert(location);
    percentage_ = stored.value("percentage", -1);
  }
  if (!ApplyClientMessage(game_, configuration, logger_))
    throw std::runtime_error("Invalid Archipelago slot configuration");
  game_->StampSeedHash(seed_hash_);
  PublishItems();
  game_->MarkChecked({checked_.begin(), checked_.end()});
  game_->MarkChecked({pending_.begin(), pending_.end()});
  game_->ClearNotice(ToastNotice::kHandshakeRefusal);
  game_->SetClientConnected(true);
  active_ = true;
  logger_("Connected directly to Archipelago; seed " + seed_hash_);
  PublishPercentage();
  PublishStatus();
  if (ready_ && !finished_) Send({{"cmd", "StatusUpdate"}, {"status", 10}});
  return true;
}

void NativeSession::PublishItems() {
  std::vector<std::pair<std::int64_t, std::int64_t>> items;
  for (std::size_t index = 0; index < received_.size(); ++index)
    items.emplace_back(index, received_[index].at("item").get<std::int64_t>());
  game_->ApplyItems(items);
}

void NativeSession::Handle(const json& packet) {
  const std::string command = packet.at("cmd").get<std::string>();
  if (command == "RoomInfo") {
    online_ = items_ready_ = false;
    game_->SetClientConnected(false);
    seed_name_ = packet.at("seed_name").get<std::string>();
    Send({{"cmd", "Connect"}, {"game", kGame}, {"name", slot_name_}, {"password", password_},
          {"uuid", NativeSeedHash("GtaVcAp", slot_name_)}, {"items_handling", 7}, {"slot_data", true},
          {"tags", json::array({"AP"})},
          {"version", {{"major", 0}, {"minor", 6}, {"build", 7}, {"class", "Version"}}}});
  } else if (command == "ConnectionRefused") {
    online_ = false;
    const auto reason = "Archipelago refused: " + packet.value("errors", json::array()).dump();
    logger_(reason);
    game_->ShowNotice(ToastNotice::kHandshakeRefusal, reason);
  } else if (command == "Connected") {
    const int new_slot = packet.at("slot").get<int>();
    const auto canonical = packet.at("slot_info").at(std::to_string(new_slot)).value("name", slot_name_);
    const auto new_hash = NativeSeedHash(seed_name_, canonical);
    if (!seed_hash_.empty() && seed_hash_ != new_hash)
      throw std::runtime_error("The server changed seeds. Restart Vice City before connecting to the new seed.");
    slot_ = packet.at("slot").get<int>();
    team_ = packet.at("team").get<int>();
    config_ = packet.at("slot_data");
    slot_info_ = packet.at("slot_info");
    players_ = packet.at("players");
    seed_hash_ = new_hash;
    online_ = true;
    active_ = items_ready_ = finished_ = false;
    checked_ = packet.at("checked_locations").get<std::set<std::int64_t>>();
    name_groups_.clear();
    Send({{"cmd", "Get"}, {"keys", {
        std::string("_read_item_name_groups_") + kGame,
        std::string("_read_location_name_groups_") + kGame}}});
    all_locations_ = packet.at("missing_locations").get<std::set<std::int64_t>>();
    all_locations_.insert(checked_.begin(), checked_.end());
    pending_.clear();
    state_file_.clear();
    received_ = json::array();
    percentage_ = -1;
    last_send_ = {};
    death_link_ = Enabled(config_.value("death_link", json(false)));
    if (death_link_override_ >= 0) death_link_ = death_link_override_ != 0;
    Send({{"cmd", "ConnectUpdate"}, {"tags", death_link_ ? json::array({"AP", "DeathLink"})
                                                                     : json::array({"AP"})}});
    std::set<std::string> games;
    for (const auto& info : slot_info_) {
      const auto game = info.value("game", std::string());
      if (!game.empty() && game != kGame && game != "__Server") games.insert(game);
    }
    if (!games.empty()) Send({{"cmd", "GetDataPackage"}, {"games", games}});
  } else if (command == "ReceivedItems" && online_) {
    const auto index = packet.at("index").get<std::size_t>();
    const json& batch = packet.at("items");
    if (!batch.is_array() || index > received_.size() || (index != 0 && !items_ready_)) {
      Send({{"cmd", "Sync"}});
      return;
    }
    for (const auto& item : batch) {
      if (!item.is_object() || !item.at("item").is_number_integer() ||
          !item.at("player").is_number_integer() || !item.at("location").is_number_integer())
        throw std::runtime_error("Invalid received item");
    }
    if (index == 0) received_ = batch;
    else for (std::size_t offset = 0; offset < batch.size(); ++offset) {
      if (index + offset < received_.size()) received_[index + offset] = batch[offset];
      else received_.push_back(batch[offset]);
    }
    items_ready_ = true;
    if (!active_) Activate();
    else if (SeedMatches()) { PublishItems(); PublishStatus(); }
  } else if (command == "RoomUpdate" && online_) {
    for (const auto location : packet.value("checked_locations", json::array()).get<std::vector<std::int64_t>>()) {
      if (!all_locations_.count(location)) continue;
      checked_.insert(location);
      pending_.erase(location);
      if (active_) game_->MarkChecked({location});
    }
    if (packet.contains("players")) players_ = packet["players"];
    if (active_) { PersistChecks(); PublishStatus(); }
  } else if (command == "Retrieved" && online_) {
    for (const char* kind : {"item", "location"}) {
      const std::string key = std::string("_read_") + kind + "_name_groups_" + kGame;
      const auto& keys = packet.at("keys");
      if (!keys.contains(key)) continue;
      const auto& groups = keys.at(key);
      if (!groups.is_object()) throw std::runtime_error("Invalid name groups from server");
      for (const auto& members : groups) {
        if (!members.is_array() || std::any_of(members.begin(), members.end(),
            [](const json& name) { return !name.is_string(); }))
          throw std::runtime_error("Invalid name group members from server");
      }
      name_groups_[kind] = groups;
    }
  } else if (command == "DataPackage") {
    const json& games = packet.at("data").at("games");
    for (auto game = games.begin(); game != games.end(); ++game) {
      json inverted = {{"items", json::object()}, {"locations", json::object()}};
      for (const char* type : {"item", "location"}) {
        const auto& names = game.value().at(std::string(type) + "_name_to_id");
        for (auto name = names.begin(); name != names.end(); ++name)
          inverted[std::string(type) + "s"][std::to_string(name.value().get<std::int64_t>())] = name.key();
      }
      data_packages_[game.key()] = std::move(inverted);
    }
  } else if (command == "Print") {
    const auto text = packet.at("text").get<std::string>().substr(0, 16384);
    OutputConsole(ConsoleMessage{{text, 0xFFFFFF}}, true);
  } else if (command == "PrintJSON") {
    std::string text;
    ConsoleMessage spans;
    for (const auto& part : packet.at("data")) {
      if (text.size() >= 16384) break;
      auto value = part.value("text", std::string());
      const auto type = part.value("type", std::string());
      std::string color = type == "color" ? part.value("color", std::string()) : "white";
      if (type == "player_id" || type == "player_name") color = "yellow";
      else if (type == "item_id" || type == "item_name") {
        const int flags = part.value("flags", 0);
        color = flags & 1 ? "plum" : flags & 2 ? "slateblue" : flags & 4 ? "salmon" : "cyan";
      } else if (type == "location_id" || type == "location_name") color = "green";
      else if (type == "entrance_name") color = "blue";
      else if (type == "hint_status") {
        switch (part.value("hint_status", -1)) {
          case 0: color = "white"; break;
          case 10: color = "slateblue"; break;
          case 20: color = "salmon"; break;
          case 30: color = "plum"; break;
          case 40: color = "green"; break;
          default: color = "red"; break;
        }
      }
      if (type == "player_id" || type == "item_id" || type == "location_id") {
        try {
          std::size_t end = 0;
          const auto id = std::stoll(value, &end);
          if (end == value.size()) {
            if (type == "player_id" && ConcernsSelf(static_cast<int>(id))) color = "magenta";
            value = type == "player_id" ? PlayerName(static_cast<int>(id)) :
                Name(id, part.value("player", slot_), type == "item_id");
          }
        } catch (const std::invalid_argument&) {} catch (const std::out_of_range&) {}
      }
      value = value.substr(0, 16384 - text.size());
      text += value;
      if (!value.empty()) spans.push_back({std::move(value), ConsoleColor(color)});
    }
    OutputConsole(spans, true);
    if (online_ && active_ && packet.value("type", std::string()) == "ItemSend" && packet.contains("item")) {
      const int receiving = packet.at("receiving").get<int>();
      if (!ConcernsSelf(receiving) && ConcernsSelf(packet["item"].at("player").get<int>()))
        ItemToast(packet["item"], receiving);
    }
  } else if (command == "Bounced" && online_ && active_ && death_link_ && SeedMatches()) {
    const auto tags = packet.value("tags", std::vector<std::string>{});
    if (std::find(tags.begin(), tags.end(), "DeathLink") == tags.end()) return;
    const json& data = packet.at("data");
    const double timestamp = data.at("time").get<double>();
    if (timestamp <= last_death_) return;
    last_death_ = timestamp;
    const std::string source = data.value("source", std::string("another world"));
    game_->ShowToast(BuildToastRow({{"DeathLink", "trap"}, {" from ", "connective"}, {source, "other_slot"}}));
    game_->ApplyDeathLink(source);
  }
}

bool NativeSession::ConcernsSelf(int slot) const {
  if (slot == slot_) return true;
  const auto entry = slot_info_.find(std::to_string(slot));
  if (entry == slot_info_.end()) return false;
  const auto members = entry->value("group_members", std::vector<int>{});
  return std::find(members.begin(), members.end(), slot_) != members.end();
}

std::string NativeSession::PlayerName(int slot) const {
  if (slot == 0) return "Archipelago";
  for (const auto& player : players_)
    if (player.value("slot", -1) == slot && player.value("team", -1) == team_)
      return player.value("alias", player.value("name", std::to_string(slot)));
  return std::to_string(slot);
}

std::string NativeSession::Name(std::int64_t id, int slot, bool item) const {
  const std::string key = std::to_string(id);
  const auto info = slot_info_.find(std::to_string(slot));
  const std::string game = info == slot_info_.end() ? "" : info->value("game", std::string());
  if (game == kGame || ConcernsSelf(slot)) {
    const auto found = defaults_[item ? "items" : "locations"].find(key);
    if (found != defaults_[item ? "items" : "locations"].end())
      return item ? found->at(0).get<std::string>() : found->get<std::string>();
  }
  const auto package = data_packages_.find(game);
  if (package != data_packages_.end()) return package->at(item ? "items" : "locations").value(key, key);
  return key;
}

void NativeSession::ItemToast(const json& item, int receiving) {
  const int sender = item.at("player").get<int>();
  const auto id = item.at("item").get<std::int64_t>();
  int flags = item.value("flags", 0);
  const auto own = defaults_["items"].find(std::to_string(id));
  if (!(flags & 7) && ConcernsSelf(receiving) && own != defaults_["items"].end())
    flags = own->at(1).get<int>();
  const std::string color = flags & 1 ? "progression" : flags & 2 ? "useful" : flags & 4 ? "trap" : "filler";
  std::vector<std::pair<std::string, std::string>> segments = {{"You", "own_slot"}};
  if (ConcernsSelf(sender) && ConcernsSelf(receiving)) {
    segments.emplace_back(" found your ", "connective");
    segments.emplace_back(Name(id, receiving, true), color);
  } else {
    segments.emplace_back(ConcernsSelf(receiving) ? " received " : " sent ", "connective");
    segments.emplace_back(Name(id, receiving, true), color);
    segments.emplace_back(ConcernsSelf(receiving) ? " from " : " to ", "connective");
    segments.emplace_back(PlayerName(ConcernsSelf(receiving) ? sender : receiving), "other_slot");
  }
  const auto location = item.at("location").get<std::int64_t>();
  if (location > 0) {
    segments.emplace_back(" (", "connective");
    segments.emplace_back(Name(location, sender, false), "location");
    segments.emplace_back(")", "connective");
  }
  // PrintJSON already supplies the console and popup; retain only pause history.
  game_->ShowToast(BuildToastRow(segments), false);
}

bool NativeSession::GoalReached() const {
  const std::string goal = config_.value("goal", std::string());
  if (goal == "final_mission") return checked_.count(config_.value("final_location_id", std::int64_t(-1))) != 0;
  if (goal == "hidden_packages") {
    const int required = config_.value("hidden_packages_required", 0);
    const auto fragment = config_.value("hidden_package_item_id", std::int64_t(-1));
    return required > 0 && fragment > 0 && std::count_if(received_.begin(), received_.end(),
        [fragment](const json& item) { return item.at("item") == fragment; }) >= required;
  }
  if (goal == "hundred_percent" && !checked_.empty()) {
    const auto uncounted = config_.value("goal_uncounted_locations", std::set<std::int64_t>{});
    return std::all_of(all_locations_.begin(), all_locations_.end(),
        [&](std::int64_t location) { return checked_.count(location) || uncounted.count(location); });
  }
  return false;
}

void NativeSession::PublishStatus() {
  const bool complete = GoalReached();
  if (complete && !finished_) {
    finished_ = Send({{"cmd", "StatusUpdate"}, {"status", 30}});
    if (finished_) logger_("Goal complete! Your goal has been reported to Archipelago.");
  }
  ClientStatus status;
  status.checks_done = static_cast<int>(checked_.size());
  status.checks_total = static_cast<int>(all_locations_.size());
  status.items_received = static_cast<int>(received_.size());
  status.goal_reached = complete;
  const std::string goal = config_.value("goal", std::string("unknown"));
  status.finale_warp = complete && goal == "hidden_packages";
  status.goal_rows.push_back({"Goal", goal == "final_mission" ? "Keep Your Friends Close" :
      goal == "hidden_packages" ? "Package Fragments" : "Every check in the seed", complete});
  if (goal == "hidden_packages") {
    const auto fragment = config_.value("hidden_package_item_id", std::int64_t(-1));
    const auto count = std::count_if(received_.begin(), received_.end(),
        [fragment](const json& item) { return item.at("item") == fragment; });
    status.goal_rows.push_back({"Fragments", std::to_string(count) + " of " +
                               std::to_string(config_.value("hidden_packages_required", 0)), complete});
  }
  if (goal == "hundred_percent") {
    const auto uncounted = config_.value("goal_uncounted_locations", std::set<std::int64_t>{});
    const auto left = std::count_if(all_locations_.begin(), all_locations_.end(),
        [&](std::int64_t location) { return !checked_.count(location) && !uncounted.count(location); });
    status.goal_rows.push_back({"Checks left", std::to_string(left), complete});
  }
  for (const auto& strand : defaults_["strands"]) {
    if (strand[3] == true && !Enabled(config_.value("enable_properties", json(false)))) continue;
    const int total = strand[2].get<int>();
    const int count = std::min(total, static_cast<int>(std::count_if(received_.begin(), received_.end(),
        [&](const json& item) { return item.at("item") == strand[1]; })));
    status.strand_rows.push_back({strand[0].get<std::string>(), std::to_string(count) + " of " +
                                  std::to_string(total), count >= total});
  }
  game_->SetClientStatus(status);
}

void NativeSession::PublishPercentage() {
  if (percentage_ < 0 || !online_) return;
  Send({{"cmd", "Set"}, {"key", "gta_vice_city_percentage_" + std::to_string(team_) + "_" + std::to_string(slot_)},
        {"default", 0}, {"want_reply", false},
        {"operations", json::array({{{"operation", "replace"}, {"value", percentage_}}})}});
}

void NativeSession::Tick(bool socket_connected) {
  if (!socket_connected && online_) {
    online_ = false;
    game_->SetClientConnected(false);
    logger_("Archipelago disconnected; pending checks are retained");
  }
  if (online_ && !active_) Activate();
  if (!active_) return;
  if (!SeedMatches()) {
    game_->ShowNotice(ToastNotice::kHandshakeRefusal,
                     "Wrong seed save loaded. Load this seed's save or start a new game.");
    return;
  }
  const auto checks = game_->TakeNewChecks();
  bool new_checks = false;
  for (const auto location : checks)
    if (all_locations_.count(location) && !checked_.count(location))
      new_checks = pending_.insert(location).second || new_checks;
  try {
    if (!checks.empty()) PersistChecks();
  } catch (...) {
    game_->RequeueChecks(checks);
    throw;
  }
  for (const auto index : game_->TakeAppliedReports())
    if (online_ && index >= 0 && static_cast<std::size_t>(index) < received_.size())
      ItemToast(received_[static_cast<std::size_t>(index)], slot_);
  if (game_->TakeDeath() && online_ && death_link_) {
    last_death_ = Now();
    Send({{"cmd", "Bounce"}, {"tags", json::array({"DeathLink"})},
          {"data", {{"time", last_death_}, {"source", PlayerName(slot_)},
                    {"cause", PlayerName(slot_) + " was wasted in Vice City."}}}});
  }
  int percentage;
  if (game_->TakeProgressPercentage(percentage)) {
    percentage_ = percentage;
    PersistChecks();
    PublishPercentage();
  }
  const auto now = std::chrono::steady_clock::now();
  // New checks leave on this tick; only unacknowledged retries wait a second.
  if (online_ && (new_checks || now - last_send_ >= std::chrono::seconds(1))) {
    if (!pending_.empty()) { PersistChecks(); Send({{"cmd", "LocationChecks"}, {"locations", pending_}}); }
    PublishStatus();
    last_send_ = now;
  }
}

void NativeSession::OutputConsole(const ConsoleMessage& message, bool notify) {
  if (console_) console_(message, notify);
  else {
    std::string text;
    for (const auto& span : message) text += span.text;
    logger_(text);
  }
}

void NativeSession::Command(const std::string& text) {
  if (text.empty() || text.size() > 4096 || text.find_first_of("\r\n") != std::string::npos) {
    logger_("Enter one message, up to 4096 bytes.");
    return;
  }
  const auto space = text.find(' ');
  const auto command = text.substr(0, space);
  auto argument = space == std::string::npos ? std::string() : text.substr(space + 1);
  argument.erase(0, argument.find_first_not_of(' '));
  argument.erase(argument.find_last_not_of(' ') + 1);
  if (command == "/received" || command == "/items" || command == "/locations" ||
      command == "/item_groups" || command == "/location_groups") {
    std::size_t page = 1;
    const auto token = argument.substr(0, argument.find(' '));
    if (!token.empty() && token.find_first_not_of("0123456789") == std::string::npos) {
      const auto parsed = std::from_chars(token.data(), token.data() + token.size(), page);
      if (parsed.ec != std::errc() || page == 0) { logger_("Page must be a positive number."); return; }
      argument.erase(0, token.size());
      argument.erase(0, argument.find_first_not_of(' '));
    }
    std::vector<ConsoleMessage> rows;
    if (command == "/received") {
      if (!argument.empty()) { logger_("Usage: /received [page]"); return; }
      if (!items_ready_) { logger_("Received items have not synchronized yet."); return; }
      for (std::size_t index = 0; index < received_.size(); ++index) {
        const auto& item = received_[index];
        const int sender = item.at("player").get<int>();
        const auto location = item.at("location").get<std::int64_t>();
        const int flags = item.value("flags", 0);
        const auto color = ConsoleColor(flags & 1 ? "plum" : flags & 2 ? "slateblue" : flags & 4 ? "salmon" : "cyan");
        rows.push_back({{std::to_string(index + 1) + ". ", 0xFFFFFF},
            {Name(item.at("item").get<std::int64_t>(), slot_, true), color},
            {" from ", 0xFFFFFF}, {PlayerName(sender), ConcernsSelf(sender) ? 0xEE00EEu : 0xFAFAD2u},
            {" at ", 0xFFFFFF}, {location == -2 ? "Starting inventory" : location == -1 ? "Server" :
                Name(location, sender, false), 0x00FF7F}});
      }
    } else {
      const bool item = command == "/items" || command == "/item_groups";
      std::vector<std::string> names;
      if (command == "/item_groups" || command == "/location_groups") {
        const char* kind = item ? "item" : "location";
        if (!name_groups_.contains(kind)) { logger_("Name groups have not synchronized yet. Connect and try again."); return; }
        const auto& groups = name_groups_.at(kind);
        if (argument.empty()) for (auto group = groups.begin(); group != groups.end(); ++group) names.push_back(group.key());
        else {
          const auto group = groups.find(argument);
          if (group == groups.end()) { logger_("Unknown group. Use " + command + " to list group names."); return; }
          names = group->get<std::vector<std::string>>();
        }
      } else {
        const auto lower = [](std::string value) {
          for (auto& c : value) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
          return value;
        };
        const auto filter = lower(argument);
        for (const auto& entry : defaults_[item ? "items" : "locations"]) {
          const auto name = item ? entry.at(0).get<std::string>() : entry.get<std::string>();
          if (lower(name).find(filter) != std::string::npos) names.push_back(name);
        }
      }
      std::sort(names.begin(), names.end());
      for (const auto& name : names) rows.push_back({{name, item ? 0x00EEEEu : 0x00FF7Fu}});
    }
    // Keep each command response readable within the console's bounded history.
    constexpr std::size_t page_size = 20;
    const auto pages = std::max<std::size_t>(1, (rows.size() + page_size - 1) / page_size);
    if (page > pages) { logger_("Page out of range; available pages: 1-" + std::to_string(pages)); return; }
    OutputConsole({{command + ": " + std::to_string(rows.size()) + " results, page " +
        std::to_string(page) + "/" + std::to_string(pages), 0xFFFFFF}});
    for (std::size_t index = (page - 1) * page_size; index < std::min(rows.size(), page * page_size); ++index)
      OutputConsole(rows[index]);
    if (page < pages) OutputConsole({{"Next: " + command + " " + std::to_string(page + 1) +
        (argument.empty() ? "" : " " + argument), 0xFFFFFF}});
    return;
  }
  if (!online_) { logger_("Connect to Archipelago first."); return; }
  if (command == "/ready") {
    if (!argument.empty()) { logger_("Usage: /ready"); return; }
    if (finished_ || GoalReached()) { logger_("Goal already completed; ready status is unchanged."); return; }
    if (!Send({{"cmd", "StatusUpdate"}, {"status", ready_ ? 5 : 10}})) {
      logger_("Ready status was not changed: connection unavailable."); return;
    }
    ready_ = !ready_;
    logger_(ready_ ? "Readied up." : "Unreadied.");
    return;
  }
  if (command == "/deathlink") {
    int override = death_link_override_;
    if (argument.empty()) override = !death_link_;
    else if (argument == "on" || argument == "true" || argument == "1") override = 1;
    else if (argument == "off" || argument == "false" || argument == "0") override = 0;
    else if (argument == "seed") override = -1;
    else { logger_("Usage: /deathlink [on|off|seed]"); return; }
    const bool enabled = override < 0 ? Enabled(config_.value("death_link", json(false))) : override != 0;
    if (!Send({{"cmd", "ConnectUpdate"}, {"tags", enabled ? json::array({"AP", "DeathLink"}) : json::array({"AP"})}})) {
      logger_("DeathLink was not changed: connection unavailable."); return;
    }
    death_link_ = enabled;
    death_link_override_ = override;
    logger_(std::string(enabled ? "DeathLink enabled." : "DeathLink disabled.") +
            (override < 0 ? " Following the seed setting." : ""));
    return;
  }
  std::string message = text;
  if (text == "/hint" || text.rfind("/hint ", 0) == 0) message.replace(0, 5, "!hint");
  else if (text == "/commands") message = "!help";
  else if (text.front() == '/') {
    logger_("Unknown local command. Use /help; server commands start with !."); return;
  }
  if (!Send({{"cmd", "Say"}, {"text", message}})) logger_("Message was not sent: connection unavailable.");
}

}  // namespace gtavc
