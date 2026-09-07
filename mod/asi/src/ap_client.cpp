#include "ap_client.hpp"

#include <winsock2.h>
#include <windows.h>
#include <memory>
#include <jansson.h>
#include <libwebsockets.h>
#include <glib.h>
extern "C" {
#include "apcc/APCc.h"
}

namespace gtavc {
namespace {
// One ASI instance, serviced by one thread. No game memory is accessed here.
NativeSession* session = nullptr;
GameState* callback_game = nullptr;
Logger callback_logger;
std::string last_error;

void TransportLog(int, const char* line) {
  try { callback_logger(std::string("WebSocket: ") + line); } catch (...) {}
}

void ReportError(const std::string& error) {
  if (error == last_error) return;
  last_error = error;
  callback_logger(error);
  callback_game->ShowNotice(ToastNotice::kHandshakeRefusal, error);
}

void Receive(json_t* packet) {
  try {
    std::unique_ptr<char, decltype(&std::free)> encoded(json_dumps(packet, JSON_COMPACT), &std::free);
    if (!encoded) throw std::runtime_error("Cannot decode Archipelago packet");
    const auto messages = json::parse(encoded.get());
    if (!messages.is_array()) throw std::runtime_error("Invalid Archipelago packet envelope");
    for (const auto& message : messages) {
      if (message.value("cmd", std::string()) == "RoomInfo") last_error.clear();
      session->Handle(message);
    }
  } catch (const std::exception& error) {
    ReportError(error.what());
  }
}

std::string Setting(const std::filesystem::path& ini, const char* key, const char* fallback) {
  char value[2048]{};
  GetPrivateProfileStringA("archipelago", key, fallback, value, sizeof(value), ini.string().c_str());
  return value;
}
}  // namespace

ArchipelagoClient::ArchipelagoClient(GameState* game, Logger logger)
    : game_(game), logger_(std::move(logger)) {}

ArchipelagoClient::~ArchipelagoClient() { Stop(); }

void ArchipelagoClient::Start() {
  if (!thread_.joinable()) thread_ = std::thread(&ArchipelagoClient::Run, this);
}

void ArchipelagoClient::Stop() {
  stop_ = true;
  if (thread_.joinable()) thread_.join();
}

void ArchipelagoClient::Run() {
  callback_game = game_;
  callback_logger = logger_;
  game_->SetClientConnected(false);
  try {
    HMODULE module = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                      reinterpret_cast<LPCWSTR>(&Receive), &module);
    wchar_t module_path[32768]{};
    if (!GetModuleFileNameW(module, module_path, 32768)) throw std::runtime_error("Cannot locate ASI settings");
    auto ini = std::filesystem::path(module_path).replace_extension(L".ini");
    std::string server = Setting(ini, "server", "127.0.0.1:38281");
    const std::string slot = Setting(ini, "slot", "");
    const std::string password = Setting(ini, "password", "");
    if (slot.empty()) throw std::runtime_error("Set your slot in GtaVcAp.VC.ini [archipelago], then restart the game.");
    int tls = -1;
    if (server.rfind("wss://", 0) == 0) { tls = 1; server.erase(0, 6); }
    else if (server.rfind("ws://", 0) == 0) { tls = 0; server.erase(0, 5); }
    if (!server.empty() && server.back() == '/') server.pop_back();
    const auto colon = server.rfind(':');
    if (colon == std::string::npos) throw std::runtime_error("Archipelago server must be host:port");
    const auto host = server.substr(0, colon);
    const auto port_text = server.substr(colon + 1);
    std::size_t consumed = 0;
    const int port = std::stoi(port_text, &consumed);
    if (host.empty() || consumed != port_text.size() || port < 1 || port > 65535)
      throw std::runtime_error("Invalid Archipelago server address");
    auto native = std::make_unique<NativeSession>(game_, logger_, [](const json& messages) {
      const auto encoded = messages.dump();
      json_error_t error{};
      json_t* packet = json_loadb(encoded.data(), encoded.size(), 0, &error);
      if (!packet) return false;
      const bool sent = AP_SendPacket(packet);
      json_decref(packet);
      return sent;
    }, slot, password, ini.parent_path());
    session = native.get();
    lws_set_log_level(LLL_ERR | LLL_WARN, &TransportLog);
    AP_SetPacketCallback(&Receive);
    AP_Init(host.c_str(), port, "Grand Theft Auto Vice City", slot.c_str(), password.c_str());
    if (tls >= 0) AP_SetTLS(tls != 0);
    AP_Start();
    if (!AP_WebsocketSulInit(50)) throw std::runtime_error("Cannot initialize APCc WebSocket service");
    logger_("Connecting to " + server + " as " + slot);
    while (!stop_) {
      AP_WebService();
      const bool connected = AP_GetConnectionStatus() != Disconnected;
      try {
        native->Tick(connected);
      } catch (const std::exception& error) {
        ReportError(error.what());
      }
      // Retry unavailable servers at most once a second, with interruptible shutdown.
      for (int elapsed = 0; !stop_ && elapsed < (connected ? 10 : 1000); elapsed += 10)
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    native->Tick(false);
    AP_Shutdown();
    AP_SetPacketCallback(nullptr);
    session = nullptr;
  } catch (const std::exception& error) {
    if (AP_IsInit()) AP_Shutdown();
    ReportError(error.what());
  }
  AP_SetPacketCallback(nullptr);
  session = nullptr;
  game_->SetClientConnected(false);
}

}  // namespace gtavc
