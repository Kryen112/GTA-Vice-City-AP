#include "bridge.hpp"

#include <chrono>
#include <utility>
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
      game_->ApplyConfig(item_globals, completion_watch, item_effects, config_globals,
                         package_locations, pickup_targets, mainland_routes);
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
    }
  } catch (const json::exception& error) {
    logger_(std::string("ignoring malformed message: ") + error.what());
  }
}

void BridgeClient::PumpOutbound() {
  for (const std::int64_t location : game_->TakeNewChecks()) {
    SendMessage(CheckMessage(location));
  }
  if (game_->TakeGoalReached()) {
    SendMessage(GoalReachedMessage());
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
