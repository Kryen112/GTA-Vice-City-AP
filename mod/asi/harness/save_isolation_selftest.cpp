// Exercise the real save adapter with a minimal renderer/menu stand-in.
// The game menu transition ends its own frame; it cannot nest inside drawing.
#include <cassert>
#include <iostream>
#include <fstream>
#include <vector>
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
struct SaveSlots {
  int scans = 0;
  bool slot_visible = false;
  void PopulateSlotInfo();
} PcSaveHelper;
struct Menu {
  bool m_bMenuActive = true, m_bGameNotLoaded = true;
  int transitions = 0;
  void SwitchToNewScreen(int page) {
    assert(camera == nullptr); // reproduces the forbidden nested-frame path
    assert(page == MENUPAGE_START_MENU);
    assert(PcSaveHelper.slot_visible); // refresh before returning to the main menu
    ++transitions;
  }
} FrontEndMenuManager;

#define GTAVC_SAVE_ISOLATION_TEST
#include "../src/save_isolation.cpp"

void SaveSlots::PopulateSlotInfo() {
  assert(camera == nullptr);
  const auto path = gtavc::State().prefix + "1.b";
  // Exercise the real read guard too: scanning must happen after selection and
  // outside the save mutex, because OpenSave acquires it again.
  slot_visible = gtavc::OpenSave(path.c_str(), "rb") == 77 && std::filesystem::exists(path);
  ++scans;
}

int main(int argc, char** argv) {
  assert(argc == 2);
  auto& saves = gtavc::State();
  char prefix[256] = "?:\\GTAVCsf";
  saves.installed = true;
  saves.game_prefix = prefix;
  saves.documents = std::filesystem::absolute(argv[1]).string();
  std::vector<std::string> messages;
  saves.log = [&](const std::string& message) { messages.push_back(message); };
  bool valid_loaded_seed = true;
  saves.can_write = [&](const std::string&) { return valid_loaded_seed; };
  const std::string seed = "0123456789abcdef";
  const auto existing = gtavc::SeedSaveDirectory(saves.documents, seed) / "GTAVCsf1.b";
  std::filesystem::create_directories(existing.parent_path());
  { std::ofstream file(existing); file << "existing save"; }
  assert(!gtavc::PrepareSaveSeed(seed));
  assert(messages.back().find("seed requested") != std::string::npos);
  saves.game_prefix = nullptr;
  saves.documents.clear();
  gtavc::TickSaveIsolation();
  assert(messages.back().find("save-path callback") != std::string::npos);
  const auto waiting_messages = messages.size();
  gtavc::TickSaveIsolation();
  assert(messages.size() == waiting_messages);
  saves.game_prefix = prefix;
  // Simulate the game initializing its prefix before our hook was installed.
  const auto original_directory = std::filesystem::absolute(argv[1]).string();
  std::snprintf(prefix, sizeof(prefix), "%s\\GTAVCsf", original_directory.c_str());
  gtavc::TickSaveIsolation(); // renderer not initialized yet
  assert(saves.documents == original_directory);
  assert(std::string(prefix) == "?:\\GTAVCsf");
  assert(messages.back().find("renderer initialization") != std::string::npos);
  assert(saves.selected.empty());
  RwEngineInstance = &saves;
  camera = &FrontEndMenuManager;
  gtavc::TickSaveIsolation(); // connection arrives during menu drawing
  assert(messages.back().find("rendering to finish") != std::string::npos);
  assert(saves.selected.empty() && FrontEndMenuManager.transitions == 0);
  assert(PcSaveHelper.scans == 0 && !PcSaveHelper.slot_visible);
  assert(std::string(prefix) == "?:\\GTAVCsf");
  assert(gtavc::OpenSave("C:\\Career\\GTAVCsf1.b", "wb") == 0);
  camera = nullptr;
  gtavc::TickSaveIsolation(); // next safe frontend update selects the seed
  assert(gtavc::PrepareSaveSeed(seed) && FrontEndMenuManager.transitions == 1);
  assert(FrontEndMenuManager.m_bGameNotLoaded && PcSaveHelper.scans == 1 && PcSaveHelper.slot_visible);
  std::ifstream file(existing);
  std::string contents;
  std::getline(file, contents);
  assert(contents == "existing save");
  assert(std::filesystem::is_directory(gtavc::SeedSaveDirectory(saves.documents, seed)));
  const auto save = std::string(prefix) + "1.b";
  assert(gtavc::OpenSave(save.c_str(), "wb") == 77);
  valid_loaded_seed = false;
  assert(gtavc::OpenSave(save.c_str(), "wb") == 0);
  assert(gtavc::OpenSave(save.c_str(), "rb") == 77);
  camera = &FrontEndMenuManager;
  gtavc::TickSaveIsolation();
  assert(FrontEndMenuManager.transitions == 1);
  assert(PcSaveHelper.scans == 1); // one refresh per seed selection, not every frame
  std::cout << "Main-menu save refresh, rendering deferral, and write protection passed\n";
}
