// Exercise the real save adapter with a minimal renderer/menu stand-in.
// The game menu transition ends its own frame; it cannot nest inside drawing.
#include <cassert>
#include <iostream>
#include "../src/save_isolation.hpp"

constexpr int GAME_10EN = 1, MENUPAGE_START_MENU = 29, MENUPAGE_PAUSE_MENU = 32;
namespace plugin {
int GetGameVersion() { return 0; }
template<class Result, unsigned int, class... Args>
Result CallAndReturn(Args...) { return 77; }
}
namespace injector {
template<class Function> void MakeCALL(unsigned int, Function, bool) {}
}
void* RwEngineInstance = nullptr;
void* camera = nullptr;
void* RwCameraGetCurrentCamera() { return camera; }
struct Menu {
  bool m_bMenuActive = true, m_bGameNotLoaded = true;
  int transitions = 0;
  void SwitchToNewScreen(int page) {
    assert(camera == nullptr); // reproduces the forbidden nested-frame path
    assert(page == MENUPAGE_START_MENU);
    ++transitions;
  }
} FrontEndMenuManager;

#define GTAVC_SAVE_ISOLATION_TEST
#include "../src/save_isolation.cpp"

int main(int argc, char** argv) {
  assert(argc == 2);
  auto& saves = gtavc::State();
  char prefix[256] = "?:\\GTAVCsf";
  saves.installed = true;
  saves.game_prefix = prefix;
  saves.documents = std::filesystem::absolute(argv[1]).string();
  saves.log = [](const std::string&) {};
  bool valid_loaded_seed = true;
  saves.can_write = [&](const std::string&) { return valid_loaded_seed; };
  const std::string seed = "0123456789abcdef";
  assert(!gtavc::PrepareSaveSeed(seed));
  gtavc::TickSaveIsolation(); // renderer not initialized yet
  assert(saves.selected.empty());
  RwEngineInstance = &saves;
  camera = &FrontEndMenuManager;
  gtavc::TickSaveIsolation(); // connection arrives during menu drawing
  assert(saves.selected.empty() && FrontEndMenuManager.transitions == 0);
  assert(std::string(prefix) == "?:\\GTAVCsf");
  assert(gtavc::OpenSave("C:\\Career\\GTAVCsf1.b", "wb") == 0);
  camera = nullptr;
  gtavc::TickSaveIsolation(); // next safe frontend update selects the seed
  assert(gtavc::PrepareSaveSeed(seed) && FrontEndMenuManager.transitions == 1);
  assert(std::filesystem::is_directory(gtavc::SeedSaveDirectory(saves.documents, seed)));
  const auto save = std::string(prefix) + "1.b";
  assert(gtavc::OpenSave(save.c_str(), "wb") == 77);
  valid_loaded_seed = false;
  assert(gtavc::OpenSave(save.c_str(), "wb") == 0);
  assert(gtavc::OpenSave(save.c_str(), "rb") == 77);
  camera = &FrontEndMenuManager;
  gtavc::TickSaveIsolation();
  assert(FrontEndMenuManager.transitions == 1);
  std::cout << "Save isolation defers rendering-time transitions and protects writes\n";
}
