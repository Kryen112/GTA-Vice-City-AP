// The ASI entry point. Starts the bridge on a background thread (it connects to
// the client's localhost listener with retry) and drives the game-state on the
// game frame, so all SCM memory access stays on the game thread. Received item
// unlocks reach the script and completed checks flow back, both keyed by the
// reserved-globals contract in the client's config. Logs one greppable line per
// event next to gta-vc.exe.
#include <cstdio>
#include <ctime>
#include <mutex>
#include <string>

#include <windows.h>

#include <plugin.h>

#include "bridge.hpp"
#include "game_addresses.hpp"
#include "scm_game_state.hpp"

using namespace plugin;

namespace {

// The pre-world-process hook the ability input locks need: plugin-sdk's
// gameProcessEvent fires after the whole frame, by which time the player ped
// has already read the pad and the next frame rebuilds it, so a mask written
// there reaches nobody. This event fires immediately before CWorld::Process
// instead (see kBeforeWorldProcessCallSite10). The address is tagged for the
// classic 1.0 executable, and plugin-sdk installs a hook only for the build
// it detects, so any other executable simply never patches it.
CdeclEvent<AddressListMulti<gtavc::kBeforeWorldProcessCallSite10, GAME_10EN, H_CALL>,
           PRIORITY_AFTER, ArgPickNone, void()> beforeWorldProcessEvent;

std::mutex g_log_mutex;

std::string LogPath() {
  char executable[MAX_PATH] = {0};
  GetModuleFileNameA(nullptr, executable, MAX_PATH);
  std::string path(executable);
  const std::size_t slash = path.find_last_of("\\/");
  const std::string directory = (slash == std::string::npos) ? "." : path.substr(0, slash);
  return directory + "\\gtavc_ap_asi.log";
}

void LogLine(const std::string& line) {
  std::lock_guard<std::mutex> lock(g_log_mutex);
  static FILE* file = nullptr;
  if (file == nullptr) {
    fopen_s(&file, LogPath().c_str(), "w");
    if (file == nullptr) return;
  }
  std::fprintf(file, "GTAVC_AP %ld: %s\n", static_cast<long>(std::time(nullptr)), line.c_str());
  std::fflush(file);
}

}  // namespace

struct AsiMain {
  gtavc::ScmGameState game;
  gtavc::BridgeClient bridge;

  AsiMain()
      : game([](const std::string& line) { LogLine("game: " + line); }),
        bridge("127.0.0.1", 52300, &game,
               [](const std::string& line) { LogLine("bridge: " + line); }) {
    LogLine("loaded");
    // Register the frame handlers before starting the bridge, so the game
    // thread is priming the seed-hash cache by the time the bridge presents it.
    Events::gameProcessEvent += [] { instance.OnGameProcess(); };
    beforeWorldProcessEvent += [] { instance.OnBeforeWorldProcess(); };
    bridge.Start();
  }

  ~AsiMain() { bridge.Stop(); }

  void OnGameProcess() { game.OnGameFrame(); }

  void OnBeforeWorldProcess() { game.OnBeforeWorldProcess(); }

  static AsiMain instance;
};

AsiMain AsiMain::instance;
