// The ASI entry point. Connects directly to Archipelago through APCpp on a
// background thread and drives the game-state on the
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
#include <CCamera.h>
#include <CDraw.h>
#include <CFont.h>
#include <CHud.h>
#include <CPad.h>
#include <CMenuManager.h>

#include "ap_client.hpp"
#include "game_addresses.hpp"
#include "scm_game_state.hpp"
#include "status_page.hpp"
#include "ingame_console.hpp"
#include "save_isolation.hpp"

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

CdeclEvent<AddressListMulti<gtavc::kMainMapBlipsCallSite10, GAME_10EN, H_CALL>,
           PRIORITY_BEFORE, ArgPickNone, void()> mainMapBlipsEvent;

// Frontend idle processes the menu before beginning the RenderWare camera.
// Save-directory changes may refresh the menu and must run at this boundary.
ThiscallEvent<AddressListMulti<gtavc::kFrontendMenuProcessCall10, GAME_10EN, H_CALL>,
              PRIORITY_BEFORE, ArgPickNone, void(CMenuManager*)> frontendProcessEvent;

// Follow navigation only after both pages of a transition have drawn and the
// current page has been restored. The heading hook also sees the outgoing page
// with the incoming page's selection, which incorrectly disarms the stats page.
ThiscallEvent<AddressListMulti<gtavc::kFrontendMenuDrawCall10, GAME_10EN, H_CALL,
    gtavc::kFrontendMenuTransitionDrawFirstCall10, GAME_10EN, H_CALL,
    gtavc::kFrontendMenuTransitionDrawSecondCall10, GAME_10EN, H_CALL>,
    PRIORITY_AFTER, ArgPickNone, void(CMenuManager*, int)> frontendDrawEvent;

CdeclEvent<AddressListMulti<gtavc::kPickupsUpdateCall10, GAME_10EN, H_CALL>,
           PRIORITY_AFTER, ArgPickNone, void()> afterPickupsEvent;

// CPad::UpdatePads references from plugin-sdk's meta.CPad.h (VC 1.0).
CdeclEvent<AddressListMulti<0x490476, GAME_10EN, H_CALL, 0x4A4412, GAME_10EN, H_CALL,
    0x4A5C7E, GAME_10EN, H_CALL, 0x4A669F, GAME_10EN, H_CALL, 0x4AB0A0, GAME_10EN, H_CALL,
    0x54460C, GAME_10EN, H_CALL, 0x5FFFD9, GAME_10EN, H_CALL, 0x60018F, GAME_10EN, H_CALL,
    0x61D9F4, GAME_10EN, H_CALL, 0x61DBB6, GAME_10EN, H_CALL, 0x61DD47, GAME_10EN, H_CALL>,
    PRIORITY_AFTER, ArgPickNone, void()> afterPadsEvent;

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
  gtavc::IngameConsole console;
  gtavc::ArchipelagoClient bridge;
  bool client_ready = false;

  AsiMain()
      : game([](const std::string& line) { LogLine("game: " + line); }),
        status_page([](const std::string& line) { LogLine("page: " + line); }),
        console([this](std::string text) { bridge.Command(std::move(text)); }),
        bridge(&game,
               [this](const std::string& line) { LogLine("APCpp: " + line); console.Add(line); },
               &gtavc::PrepareSaveSeed, {}, [this](const gtavc::ConsoleMessage& message, bool notify) {
                 std::string text;
                 for (const auto& span : message) text += span.text;
                 LogLine("APCpp: " + text);
                 console.Add(message, notify);
               }) {
    LogLine("loaded");
    // Register the frame handlers before starting the bridge, so the game
    // thread is priming the seed-hash cache by the time the bridge presents it.
    Events::gameProcessEvent += [] { instance.OnGameProcess(); };
    frontendProcessEvent += [] { instance.OnClientUpdate(); };
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
    // Draw over the complete menu, including in the frontend without a game.
    frontendDrawEvent += [] { instance.OnMenuDraw(); };
    // The toast stack rides plugin-sdk's HUD draw, which hooks the CHud::Draw call
    // in the frame's own 2D pass (VC 10EN 0x4A64D0). It fires after the game's own
    // HUD and before the font buffer is flushed at 0x4A64F8, so rows printed from
    // it reach the screen in the same frame and land on top of the HUD rather than
    // under it.
    //
    // Not the game process hook, which runs earlier in the frame and where a print
    // would be flushed before the HUD drew over it; and not the pre-world hook,
    // which is before any drawing at all.
    Events::drawHudEvent += [] { instance.OnDrawHud(); };
    mainMapBlipsEvent += [] { instance.game.DrawCheckMarkers(); };
    // Hook the SDK's complete set of UpdatePads call sites, including frontend
    // and save menus, before scripts or menus can consume console keystrokes.
    plugin::Events::shutdownRwEvent += [] { instance.bridge.Stop(); instance.console.ReleaseGraphics(); };
    afterPadsEvent += [] { instance.console.BlockControls(); };
    afterPickupsEvent += [] { instance.game.OnPickupsUpdated(); };
    client_ready = gtavc::InstallSaveIsolation(
        [this](const std::string& line) { LogLine(line); console.Add(line); },
        [this](const std::string& hash) { return game.CanSaveSeed(hash); });
  }

  ~AsiMain() { bridge.Stop(); }

  void OnClientUpdate() {
    if (client_ready) bridge.Start();
    gtavc::TickSaveIsolation();
  }

  void OnGameProcess() {
    OnClientUpdate();
    game.OnGameFrame();
  }
  void OnGameStarted() { game.OnGameStarted(); }

  void OnBeforeWorldProcess() { game.OnBeforeWorldProcess(); console.BlockControls(); }

  void OnDrawHud() {
    console.Draw();
    // The game decides when its HUD is worth drawing and the stack follows that,
    // because the reasons are the same: a cutscene, a fade and a script that hid
    // the HUD are all frames the player is not being asked to read anything on.
    // The rows keep their remaining time either way, since the stack only advances
    // when it is drawn.
    if (!CHud::m_Wants_To_Draw_Hud) return;
    // And not over a fade. The HUD draw runs whatever the fade is doing, so a row
    // would otherwise print over a black screen or the load blur.
    if (CDraw::FadeValue != 0 || TheCamera.m_bFading) return;
    game.DrawCheckMarkers();
    game.DrawToasts();
  }

  void OnMenuDraw() {
    if (!FrontEndMenuManager.m_bSpritesLoaded) return;
    // The claim runs here rather than in the constructor: the menu table is the
    // game's, and the text table it checks is not loaded when an ASI is loaded.
    // It acts once and returns immediately afterwards.
    status_page.Install();
    // Every menu frame, because the row the player stands on is what tells the
    // borrowed page whether the panel's entry opened it. The same answer says
    // whether the panel draws, so the menu is read once.
    if (status_page.Follow().draw) status_page.Draw(game.BuildStatusPanelState());
    console.Draw(FrontEndMenuManager.m_bGameNotLoaded &&
                 FrontEndMenuManager.m_nCurrentMenuPage == MENUPAGE_START_MENU);
    // The menu already flushed its text before this callback.
    CFont::DrawFonts();
  }

  static AsiMain instance;
};

AsiMain AsiMain::instance;
