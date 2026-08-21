#include "bridge.hpp"

#include <chrono>
#include <utility>
#include <cstddef>
#include <vector>

#include "game_state.hpp"

namespace gtavc {
namespace {
constexpr int kRetryDelayMs = 1000;
constexpr int kRecvTimeoutMs = 100;
constexpr int kHandshakeTimeoutMs = 30000;
}  // namespace

BridgeClient::BridgeClient(std::string host, int port, GameState* game, Logger logger)
    : host_(std::move(host)), port_(port), game_(game), logger_(std::move(logger)) {}

BridgeClient::~BridgeClient() { Stop(); }

void BridgeClient::Start() {
  if (thread_.joinable()) return;
  stop_ = false;
  thread_ = std::thread([this] { RunLoop(); });
}

void BridgeClient::Stop() {
  stop_ = true;
  if (thread_.joinable()) thread_.join();
  client_.Close();
}

void BridgeClient::RunLoop() {
  while (!stop_) {
    if (!client_.Connect(host_, port_)) {
      SleepInterruptible(kRetryDelayMs);
      continue;
    }
    logger_("connected to the client listener");
    reader_ = MessageReader();
    RunSession();
    // The page says "not connected" from here until the next welcome, which is
    // the truth for the whole retry wait as well as for a dropped session.
    game_->SetClientConnected(false);
    client_.Close();
    if (!stop_) SleepInterruptible(kRetryDelayMs);
  }
}

bool BridgeClient::RunSession() {
  if (!SendMessage(HelloMessage(game_->SeedHash()))) return false;
  bool welcomed = false;
  const auto handshake_deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds(kHandshakeTimeoutMs);
  while (!stop_) {
    char buffer[4096];
    const int received = client_.RecvSome(buffer, sizeof(buffer), kRecvTimeoutMs);
    if (received < 0) {
      logger_("connection closed");
      return false;
    }
    if (received > 0) {
      // A ProtocolError or any json type error from a malformed frame ends the
      // session cleanly and reconnects; it must never escape this thread and
      // terminate the game.
      try {
        for (const json& message : reader_.Feed(buffer, static_cast<std::size_t>(received))) {
          if (welcomed) {
            HandleMessage(message);
            continue;
          }
          const std::string type = message.value("type", std::string());
          if (type == msg::kRefused) {
            const std::string reason = message.value("reason", std::string());
            game_->ShowStickyToast("Archipelago refused this game: " + reason);
            logger_("refused by client: " + reason);
            return false;
          }
          if (type != msg::kWelcome) {
            logger_("unexpected handshake reply");
            return false;
          }
          game_->StampSeedHash(message.value("seed_hash", std::string()));
          welcomed = true;
          game_->SetClientConnected(true);
          logger_("welcomed by client");
        }
      } catch (const std::exception& error) {
        // ProtocolError, json type errors, and the config key conversions
        // (std::stoll/std::stoi) all derive from std::exception. A bad frame
        // ends the session and reconnects; it never escapes this thread.
        logger_(std::string("bad frame: ") + error.what());
        return false;
      }
    }
    if (!welcomed && std::chrono::steady_clock::now() >= handshake_deadline) {
      logger_("timed out waiting for welcome");
      return false;
    }
    if (welcomed) PumpOutbound();
  }
  return true;
}

bool BridgeClient::SendMessage(const json& message) {
  for (const std::string& frame : writer_.Frames(message)) {
    if (!client_.SendAll(frame)) return false;
  }
  return true;
}

void BridgeClient::HandleMessage(const json& message) {
  try {
    const std::string type = message.value("type", std::string());
    if (type == msg::kConfig) {
      std::map<std::int64_t, int> item_globals;
      for (auto it = message.at("item_globals").begin(); it != message.at("item_globals").end(); ++it) {
        item_globals[std::stoll(it.key())] = it.value().get<int>();
      }
      std::map<int, std::int64_t> completion_watch;
      for (auto it = message.at("completion_watch").begin();
           it != message.at("completion_watch").end(); ++it) {
        completion_watch[std::stoi(it.key())] = it.value().get<std::int64_t>();
      }
      std::map<std::int64_t, ItemEffect> item_effects;
      if (message.contains("item_effects")) {
        for (auto it = message.at("item_effects").begin();
             it != message.at("item_effects").end(); ++it) {
          const json& descriptor = it.value();
          ItemEffect effect;
          effect.type = descriptor.at(0).get<std::string>();
          if (descriptor.size() > 1) {
            effect.amount = descriptor.at(1).get<int>();
            effect.has_amount = true;
          }
          item_effects[std::stoll(it.key())] = effect;
        }
      }
      std::map<int, int> config_globals;
      if (message.contains("config_globals")) {
        for (auto it = message.at("config_globals").begin();
             it != message.at("config_globals").end(); ++it) {
          config_globals[std::stoi(it.key())] = it.value().get<int>();
        }
      }
      std::vector<PackageLocation> package_locations;
      if (message.contains("package_coords")) {
        for (auto it = message.at("package_coords").begin();
             it != message.at("package_coords").end(); ++it) {
          const json& coord = it.value();
          PackageLocation package;
          package.completion_global = std::stoi(it.key());
          package.x = coord.at(0).get<float>();
          package.y = coord.at(1).get<float>();
          package.z = coord.at(2).get<float>();
          package_locations.push_back(package);
        }
      }
      std::vector<PickupTarget> pickup_targets;
      if (message.contains("pickup_layout")) {
        for (const json& row : message.at("pickup_layout")) {
          PickupTarget target;
          target.x = row.at(0).get<double>();
          target.y = row.at(1).get<double>();
          target.z = row.at(2).get<double>();
          target.pickup_type = row.at(3).get<int>();
          target.model = row.at(4).get<int>();
          target.quantity = row.at(5).get<int>();
          pickup_targets.push_back(target);
        }
      }
      std::vector<MainlandRoute> mainland_routes;
      if (message.contains("mainland_routes")) {
        for (const json& entry : message.at("mainland_routes")) {
          MainlandRoute route;
          route.unlock_global = entry.value("global", 0);
          route.label = entry.value("label", std::string());
          route.needs_global = entry.value("needs_global", 0);
          route.needs_label = entry.value("needs_label", std::string());
          // A route with no global to read announces nothing and would list a
          // name against a state it never has; a route claiming a second
          // requirement it cannot name would announce "needs ." Both are dropped
          // rather than kept.
          const bool names_its_requirement =
              route.needs_global == 0 || !route.needs_label.empty();
          if (route.unlock_global != 0 && !route.label.empty() &&
              names_its_requirement) {
            mainland_routes.push_back(route);
          }
        }
      }
      std::map<std::int64_t, std::vector<int>> content_district_globals;
      if (message.contains("content_district_globals")) {
        for (auto it = message.at("content_district_globals").begin();
             it != message.at("content_district_globals").end(); ++it) {
          std::vector<int> globals;
          for (const json& global_index : it.value()) {
            globals.push_back(global_index.get<int>());
          }
          content_district_globals[std::stoll(it.key())] = std::move(globals);
        }
      }
      std::vector<PickupDistrict> pickup_districts;
      if (message.contains("content_districts")) {
        for (const json& entry : message.at("content_districts")) {
          PickupDistrict placed;
          placed.x = entry.at("x").get<float>();
          placed.y = entry.at("y").get<float>();
          placed.content_index = entry.at("class").get<int>();
          placed.district = entry.at("district").get<int>();
          // A row naming a class or a district outside the block would index
          // past the lock array, so it is dropped rather than trusted.
          if (placed.content_index < 0 || placed.content_index >= kContentCount) continue;
          if (placed.district < 0 || placed.district >= kDistrictCount) continue;
          pickup_districts.push_back(placed);
        }
      }
      game_->ApplyConfig(item_globals, completion_watch, item_effects, config_globals,
                         package_locations, pickup_targets, mainland_routes,
                         content_district_globals, pickup_districts);
    } else if (type == msg::kItems) {
      std::vector<std::pair<std::int64_t, std::int64_t>> items;
      for (const json& entry : message.at("items")) {
        items.emplace_back(entry.at(0).get<std::int64_t>(), entry.at(1).get<std::int64_t>());
      }
      game_->ApplyItems(items);
    } else if (type == msg::kChecked) {
      std::vector<std::int64_t> locations;
      for (const json& location : message.at("locations")) {
        locations.push_back(location.get<std::int64_t>());
      }
      game_->MarkChecked(locations);
    } else if (type == msg::kToast) {
      game_->ShowToast(message.value("text", std::string()));
    } else if (type == msg::kStatus) {
      ClientStatus status;
      status.checks_done = message.value("checks_done", 0);
      status.checks_total = message.value("checks_total", 0);
      status.items_received = message.value("items_received", 0);
      status.goal_reached = message.value("goal_reached", false);
      status.finale_warp = message.value("finale_warp", false);
      // Both row lists are optional, so a client and a mod one field apart still
      // talk and the page simply leaves those blocks out.
      for (const char* field : {"goal_rows", "strand_rows"}) {
        if (!message.contains(field)) continue;
        std::vector<ClientRow>& rows = std::string(field) == "goal_rows"
                                           ? status.goal_rows
                                           : status.strand_rows;
        for (const json& entry : message.at(field)) {
          if (!entry.is_array() || entry.size() < 2) continue;
          ClientRow row;
          row.label = entry.at(0).get<std::string>();
          row.value = entry.at(1).get<std::string>();
          row.done = entry.size() > 2 && entry.at(2).get<bool>();
          rows.push_back(std::move(row));
        }
      }
      game_->SetClientStatus(status);
    }
  } catch (const json::exception& error) {
    logger_(std::string("ignoring malformed message: ") + error.what());
  }
}

void BridgeClient::PumpOutbound() {
  // One at a time, and the first failure hands the rest back. Draining the
  // queue takes the locations out of the only place they can be found again:
  // the game state records each one as reported the moment it detects it, and a
  // save folds its completion global into the next baseline, so a location
  // dropped here is dropped for good and a lost progression check makes the
  // multiworld unbeatable. The client re-sends what it has on every connect, so
  // handing them back is all this side has to do.
  const std::vector<std::int64_t> checks = game_->TakeNewChecks();
  for (std::size_t index = 0; index < checks.size(); ++index) {
    if (!SendMessage(CheckMessage(checks[index]))) {
      game_->RequeueChecks({checks.begin() + static_cast<std::ptrdiff_t>(index),
                            checks.end()});
      return;
    }
  }
  if (game_->TakeGoalReached()) {
    SendMessage(GoalReachedMessage());
  }
  int percentage = 0;
  if (game_->TakeProgressPercentage(percentage)) {
    SendMessage(ProgressMessage(percentage));
  }
}

void BridgeClient::SleepInterruptible(int milliseconds) {
  int slept = 0;
  while (slept < milliseconds && !stop_) {
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    slept += 50;
  }
}

}  // namespace gtavc
