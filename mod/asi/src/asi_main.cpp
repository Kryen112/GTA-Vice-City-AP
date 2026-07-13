// First in-game ASI milestone: prove the plugin loads and that plugin-sdk
// reads and writes SCM globals with Sanny's $N addressing (global $N lives at
// ScriptSpace[N*4]). Deliberately single-file and offline: no socket yet, so
// this run isolates the two in-game unknowns (does the .asi load, does the
// global write reach the script) from the networking, which is already
// verified headless. Pressing the debug key writes the reserved unlock global
// $9000 = 1, which the gated main.scm reads to open "An Old Friend", the same
// gate the CLEO spike proved by hand.
#include <cstdio>
#include <ctime>
#include <string>

#include <windows.h>

#include <plugin.h>
#include <CMessages.h>
#include <CTheScripts.h>

using namespace plugin;

namespace {

// The AP reserved global block starts above the vanilla maximum ($8583).
constexpr int kUnlockAnOldFriend = 9000;
constexpr int kDebugSetKey = VK_F6;

int& GlobalInt(int index) {
  return *reinterpret_cast<int*>(&CTheScripts::ScriptSpace[index * 4]);
}

// The log lives next to gta-vc.exe. A relative path would follow the working
// directory, which a Steam or shortcut launch does not set to the game folder.
std::string LogPath() {
  char executable[MAX_PATH] = {0};
  GetModuleFileNameA(nullptr, executable, MAX_PATH);
  std::string path(executable);
  const std::size_t slash = path.find_last_of("\\/");
  const std::string directory = (slash == std::string::npos) ? "." : path.substr(0, slash);
  return directory + "\\gtavc_ap_asi.log";
}

void Log(const char* format, int value) {
  static FILE* file = nullptr;
  if (file == nullptr) {
    fopen_s(&file, LogPath().c_str(), "w");
    if (file == nullptr) return;
  }
  std::fprintf(file, "GTAVC_AP %ld: ", static_cast<long>(std::time(nullptr)));
  std::fprintf(file, format, value);
  std::fprintf(file, "\n");
  std::fflush(file);
}

}  // namespace

struct AsiMain {
  std::size_t frame = 0;
  bool key_was_down = false;

  AsiMain() {
    Log("loaded (build frame %d)", 0);
    Events::gameProcessEvent += [] { instance.OnGameProcess(); };
  }

  void OnGameProcess() {
    ++frame;
    const bool key_is_down = (GetAsyncKeyState(kDebugSetKey) & 0x8000) != 0;
    if (key_is_down && !key_was_down) {
      GlobalInt(kUnlockAnOldFriend) = 1;
      Log("debug key: wrote global 9000 = %d", GlobalInt(kUnlockAnOldFriend));
      CMessages::AddMessageJumpQ(const_cast<char*>("AP: unlock global 9000 set"), 3000, 0);
    }
    key_was_down = key_is_down;

    if (frame % 200 == 0) {
      Log("heartbeat: global 9000 reads %d", GlobalInt(kUnlockAnOldFriend));
    }
  }

  static AsiMain instance;
};

AsiMain AsiMain::instance;
