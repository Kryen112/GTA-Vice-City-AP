// The ASI entry point. Starts the bridge on a background thread (it connects to
// the client's localhost listener with retry), drives the game-state on the
// game frame, so all SCM memory access stays on the game thread, and draws the
// pause menu's status page from the menu's own draw event. Received item
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
#include "status_page.hpp"

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
  gtavc::StatusPage status_page;
  gtavc::BridgeClient bridge;

  AsiMain()
      : game([](const std::string& line) { LogLine("game: " + line); }),
        status_page([](const std::string& line) { LogLine("page: " + line); }),
        bridge("127.0.0.1", 52300, &game,
               [](const std::string& line) { LogLine("bridge: " + line); }) {
    LogLine("loaded");
    // Register the frame handlers before starting the bridge, so the game
    // thread is priming the seed-hash cache by the time the bridge presents it.
    Events::gameProcessEvent += [] { instance.OnGameProcess(); };
    // The world being replaced, which is what tells the world-scoped state it is
    // naming objects that no longer exist. It takes BOTH events, because each
    // covers a path the other does not: starting a game runs the initialise path,
    // and a load runs the restart path, which a load from the frontend reaches
    // after the initialise one. Handling it twice is free, since the handler does
    // nothing when there is nothing to forget. An in-game restart with no load
    // may reach neither, which costs only a stale swap reference, and those are
    // refused by the pool reference and the model they must still be wearing.
    //
    // No frame condition says it. The frame keeps running with the pause menu
    // open, and the player ped survives death, arrest and a cutscene, so nothing
    // a frame can see separates the frame before a load from the frame after.
    Events::initGameEvent += [] { instance.OnGameStarted(); };
    Events::restartGameEvent += [] { instance.OnGameStarted(); };
    beforeWorldProcessEvent += [] { instance.OnBeforeWorldProcess(); };
    // The panel has its own event, plugin-sdk's menu draw, which fires after the
    // menu itself has drawn and only while the menu is up. The in-game pause menu
    // is drawn inside a game frame, later in the same frame as the game process
    // hook above, which is why the panel cannot ride on that one; the frontend is
    // the case drawn with no game frame at all.
    Events::menuDrawingEvent += [] { instance.OnMenuDraw(); };
    bridge.Start();
  }

  ~AsiMain() { bridge.Stop(); }

  void OnGameProcess() { game.OnGameFrame(); }
  void OnGameStarted() { game.OnGameStarted(); }

  void OnBeforeWorldProcess() { game.OnBeforeWorldProcess(); }

  void OnMenuDraw() {
    // The claim runs here rather than in the constructor: the menu table is the
    // game's, and the text table it checks is not loaded when an ASI is loaded.
    // It acts once and returns immediately afterwards.
    status_page.Install();
    // Every menu frame, because the row the player stands on is what tells the
    // borrowed page whether the panel's entry opened it. The same answer says
    // whether the panel draws, so the menu is read once.
    if (!status_page.Follow().draw) return;
    status_page.Draw(gtavc::ComposeStatusPanel(game.BuildStatusPanelState()));
  }

  static AsiMain instance;
};

AsiMain AsiMain::instance;
