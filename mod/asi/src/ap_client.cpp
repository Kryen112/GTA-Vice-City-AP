#include "ap_client.hpp"

#include <windows.h>
#include <shlobj.h>
#include <memory>
#include "apcpp/Archipelago.h"

namespace gtavc {
namespace {
std::string Setting(const std::filesystem::path& ini, const char* key, const char* fallback) {
  char value[2048]{};
  GetPrivateProfileStringA("archipelago", key, fallback, value, sizeof(value), ini.string().c_str());
  return value;
}

std::string ServerUrl(std::string server) {
  if (server.find_first_of("\r\n\t @?#") != std::string::npos || server.empty())
    throw std::runtime_error("Server must be host:port, ws://host:port or wss://host:port.");
  if (server.find("://") == std::string::npos) {
    const bool local = server.rfind("127.0.0.1:", 0) == 0 || server.rfind("localhost:", 0) == 0 ||
                       server.rfind("[::1]:", 0) == 0;
    server = (local ? "ws://" : "wss://") + server;
  }
  if (server.rfind("ws://", 0) != 0 && server.rfind("wss://", 0) != 0)
    throw std::runtime_error("Only ws:// and wss:// servers are supported.");
  const auto authority = server.substr(server.find("://") + 3);
  const auto colon = authority.rfind(':');
  if (colon == std::string::npos || colon == 0 || authority.find('/') != std::string::npos)
    throw std::runtime_error("Include the server port, for example archipelago.gg:38281.");
  const auto port_text = authority.substr(colon + 1);
  std::size_t end = 0;
  const int port = std::stoi(port_text, &end);
  if (end != port_text.size() || port < 1 || port > 65535) throw std::runtime_error("Invalid server port.");
  return server;
}
}  // namespace

ArchipelagoClient::ArchipelagoClient(GameState* game, Logger logger,
                                     std::function<bool(const std::string&)> prepare_seed,
                                     std::filesystem::path state_directory, ConsoleOutput console)
    : game_(game), logger_(std::move(logger)), console_(std::move(console)), prepare_seed_(std::move(prepare_seed)),
      state_directory_(std::move(state_directory)) {}
ArchipelagoClient::~ArchipelagoClient() { Stop(); }
void ArchipelagoClient::Start() {
  if (!thread_.joinable()) { stop_ = false; thread_ = std::thread(&ArchipelagoClient::Run, this); }
}
void ArchipelagoClient::Stop() {
  stop_ = true;
  if (thread_.joinable()) thread_.join();
}
void ArchipelagoClient::Command(std::string text) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (text.size() <= 4096 && commands_.size() < 32) commands_.push_back(std::move(text));
}

void ArchipelagoClient::Run() {
  // IX callbacks only enqueue events. The session consumes them in order here.
  struct Event { int connection; std::string packet; };
  std::mutex events_mutex;
  std::deque<Event> events;
  std::size_t bytes = 0;
  std::atomic<bool> overflow{false};
  std::unique_ptr<NativeSession> native;
  bool connected = false;
  bool reported_unavailable = false;
  const auto disconnect = [&] {
    if (AP_IsInit()) AP_Shutdown();
    AP_SetPacketCallback({});
    AP_SetTransportCallback({});
    if (native) {
      try { native->Tick(false); }
      catch (const std::exception& error) { logger_(error.what()); }
    }
    connected = false;
    std::lock_guard<std::mutex> lock(events_mutex);
    events.clear(); bytes = 0; overflow = false;
  };
  try {
    HMODULE module = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                      reinterpret_cast<LPCWSTR>(&Setting), &module);
    wchar_t module_path[32768]{};
    if (!GetModuleFileNameW(module, module_path, 32768)) throw std::runtime_error("Cannot locate ASI settings.");
    auto ini = std::filesystem::path(module_path).replace_extension(L".ini");
    auto settings = ini;
    auto data_directory = state_directory_;
    if (data_directory.empty()) {
      wchar_t local[MAX_PATH]{};
      if (FAILED(SHGetFolderPathW(nullptr, CSIDL_LOCAL_APPDATA | CSIDL_FLAG_CREATE, nullptr, 0, local)))
        throw std::runtime_error("Cannot locate the current user's Archipelago settings directory.");
      data_directory = std::filesystem::path(local) / "GtaVcAp";
      settings = data_directory / "connection.ini";
    }
    std::filesystem::create_directories(data_directory);
    // Preserve unacknowledged checks from the previous beside-ASI layout.
    // Copy only recognized state filenames; never overwrite the user's new state.
    if (data_directory != ini.parent_path()) for (const auto& file : std::filesystem::directory_iterator(ini.parent_path())) {
      const auto name = file.path().filename().string();
      if (name.size() == 29 && name.rfind("GtaVcAp.", 0) == 0 && name.substr(24) == ".json" &&
          name.substr(8, 16).find_first_not_of("0123456789abcdef") == std::string::npos && file.is_regular_file())
        std::filesystem::copy_file(file.path(), data_directory / name, std::filesystem::copy_options::skip_existing);
    }
    auto server = Setting(settings, "server", Setting(ini, "server", "127.0.0.1:38281").c_str());
    auto slot = Setting(settings, "slot", Setting(ini, "slot", "").c_str());
    auto password = server == Setting(ini, "server", "127.0.0.1:38281") && slot == Setting(ini, "slot", "") ?
                    Setting(ini, "password", "") : std::string();
    const auto connect = [&] {
      const auto url = ServerUrl(server);
      if (slot.empty()) throw std::runtime_error("Set your slot with /slot NAME, then /connect.");
      disconnect();
      if (!native) native = std::make_unique<NativeSession>(game_, logger_, [](const json& messages) {
        return AP_SendPacket(messages.dump());
      }, slot, password, data_directory, prepare_seed_, console_);
      AP_SetLoggingCallback([](std::string) {}); // never log raw packets or credentials
      AP_SetPacketCallback([&](const std::string& packet) {
        std::lock_guard<std::mutex> lock(events_mutex);
        if (packet.size() > 16 * 1024 * 1024 || bytes + packet.size() > 32 * 1024 * 1024 || events.size() >= 512) {
          overflow = true; return;
        }
        bytes += packet.size();
        events.push_back({-1, packet});
      });
      AP_SetTransportCallback([&](bool open) {
        std::lock_guard<std::mutex> lock(events_mutex);
        if (events.size() >= 512) { overflow = true; return; }
        events.push_back({open ? 1 : 0, {}});
      });
      AP_Init(url.c_str(), "Grand Theft Auto Vice City", slot.c_str(), password.c_str());
      AP_Start();
      logger_("Connecting to " + server + " as " + slot);
    };
    logger_("F8: Archipelago chat and connection settings. /help lists commands.");
    if (!slot.empty()) { try { connect(); } catch (const std::exception& e) { logger_(e.what()); } }
    std::string last_error;
    while (!stop_) {
      std::deque<std::string> commands;
      { std::lock_guard<std::mutex> lock(mutex_); commands.swap(commands_); }
      for (const auto& text : commands) {
        try {
          if (text == "/connect") connect();
          else if (text == "/disconnect") { disconnect(); logger_("Disconnected. Saves remain on this seed."); }
          else if (text == "/help") {
            logger_("/server HOST:PORT, /slot NAME, /password PASSWORD, /connect, /disconnect");
            logger_("/deathlink [on|off|seed], /ready, /received [page]");
            logger_("/items [page] [filter], /locations [page] [filter]");
            logger_("/item_groups [page] [group], /location_groups [page] [group]");
            logger_("!missing [filter], !checked [filter], !hint [item]. !help lists server commands.");
            logger_("Saves select themselves per seed and slot. Installation/removal: AP Launcher's Vice City Setup.");
          } else if (text.rfind("/server ", 0) == 0 || text.rfind("/slot ", 0) == 0 ||
                     text == "/password" || text.rfind("/password ", 0) == 0) {
            const auto space = text.find(' ');
            const auto key = text.substr(1, (space == std::string::npos ? text.size() : space) - 1);
            const auto value = space == std::string::npos ? "" : text.substr(space + 1);
            if (value.find_first_of("\r\n") != std::string::npos || value.size() >= 2048)
              throw std::runtime_error("Invalid setting.");
            if (key == "server") ServerUrl(value);
            disconnect(); native.reset();
            if (key == "server") { if (server != value) password.clear(); server = value; }
            else if (key == "slot") { if (slot != value) password.clear(); slot = value; }
            else password = value;
            // Passwords entered in the overlay stay in memory for this run.
            if (key != "password" && !WritePrivateProfileStringA("archipelago", key.c_str(), value.c_str(), settings.string().c_str()))
              throw std::runtime_error("Cannot write connection settings.");
            logger_(key + " updated. Use /connect.");
          } else if (native) native->Command(text);
          else logger_("Use /server HOST:PORT, /slot NAME and /connect first.");
        } catch (const std::exception& error) { logger_(error.what()); }
      }
      if (overflow) { disconnect(); logger_("Server message limit exceeded. Use /connect to resynchronize."); }
      std::deque<Event> pending;
      { std::lock_guard<std::mutex> lock(events_mutex); pending.swap(events); bytes = 0; }
      try {
        for (const auto& event : pending) {
          if (event.connection >= 0) {
            connected = event.connection != 0;
            if (!connected && !reported_unavailable) {
              logger_("Connection unavailable; APCpp will retry. Check the server, port and ws:// or wss:// scheme.");
              reported_unavailable = true;
            }
            if (connected) reported_unavailable = false;
            if (!connected && native) native->Tick(false);
          } else if (native) {
            const auto packet = json::parse(event.packet);
            if (!packet.is_array()) throw std::runtime_error("Invalid Archipelago packet envelope.");
            for (const auto& message : packet) native->Handle(message);
          }
        }
        if (native) native->Tick(connected);
        last_error.clear();
      } catch (const std::exception& error) {
        if (last_error != error.what()) { last_error = error.what(); logger_(last_error); }
        disconnect();
        game_->ShowNotice(ToastNotice::kHandshakeRefusal, last_error);
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
  } catch (const std::exception& error) { logger_(error.what()); }
  disconnect();
  game_->SetClientConnected(false);
}
}  // namespace gtavc
