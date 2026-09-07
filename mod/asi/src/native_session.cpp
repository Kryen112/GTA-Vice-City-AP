#include "native_session.hpp"

#include <algorithm>
#include <fstream>
#include <windows.h>
#include <bcrypt.h>
#include "native_data.hpp"

#pragma comment(lib, "bcrypt.lib")

namespace gtavc {
namespace {
constexpr const char* kGame = "Grand Theft Auto Vice City";

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
                             std::filesystem::path state_directory)
    : game_(game), logger_(std::move(logger)), send_(std::move(send)),
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
    throw std::runtime_error("Cannot save pending Archipelago checks beside the game");
}

bool NativeSession::Activate() {
  if (!online_ || !items_ready_) return false;
  if (!SeedMatches()) {
    game_->ShowNotice(ToastNotice::kHandshakeRefusal,
                     "Wrong seed save loaded. Load this seed's save or start a new game.");
    return false;
  }
  json configuration = config_;
  configuration["type"] = msg::kConfig;
  for (const char* field : {"item_globals", "completion_watch", "config_globals"}) {
    if (!configuration.contains(field) || !configuration[field].is_object())
      throw std::runtime_error(std::string("Slot data is missing ") + field);
  }
  configuration["check_markers"] = json::object();
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
    game_->ShowNotice(ToastNotice::kHandshakeRefusal,
                     "Archipelago refused: " + packet.value("errors", json::array()).dump());
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
    all_locations_ = packet.at("missing_locations").get<std::set<std::int64_t>>();
    all_locations_.insert(checked_.begin(), checked_.end());
    pending_.clear();
    state_file_.clear();
    received_ = json::array();
    percentage_ = -1;
    last_send_ = {};
    death_link_ = Enabled(config_.value("death_link", json(false)));
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
  } else if (command == "PrintJSON" && online_ && active_) {
    if (packet.value("type", std::string()) == "ItemSend" && packet.contains("item")) {
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
  game_->ShowToast(BuildToastRow(segments));
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
  if (complete && !finished_) finished_ = Send({{"cmd", "StatusUpdate"}, {"status", 30}});
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
  for (const auto location : checks)
    if (all_locations_.count(location) && !checked_.count(location)) pending_.insert(location);
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
  if (online_ && now - last_send_ >= std::chrono::seconds(1)) {
    if (!pending_.empty()) { PersistChecks(); Send({{"cmd", "LocationChecks"}, {"locations", pending_}}); }
    PublishStatus();
    last_send_ = now;
  }
}

}  // namespace gtavc
