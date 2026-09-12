#include "save_isolation.hpp"
#include <mutex>
#include <cstdio>
#include <cstring>
#include <windows.h>
#ifndef GTAVC_SAVE_ISOLATION_TEST
#include <plugin.h>
#include <CMenuManager.h>
#include <C_PcSave.h>
#include <RenderWare.h>
#endif
#include "game_addresses.hpp"

namespace gtavc {
namespace {
struct Saves {
  std::mutex mutex;
  std::string requested, selected, documents, prefix;
  std::function<void(const std::string&)> log;
  std::function<bool(const std::string&)> can_write;
  char* game_prefix = nullptr;
  bool installed = false;
  bool failed = false;
};
Saves& State() { static Saves state; return state; }

int __cdecl MakePrefix(char* output, const char*, const char* directory, const char*) {
  auto& state = State();
  std::lock_guard<std::mutex> lock(state.mutex);
  state.documents = directory;
  state.game_prefix = output;
  if (state.prefix.empty()) state.prefix = "?:\\GTAVCsf"; // invalid drive, also blocks delete before connection
  // Saving/loading is refused by OpenSave until a server has identified the
  // seed. No career saves are ever renamed, copied, deleted or exposed.
  return std::snprintf(output, 256, "%s", state.prefix.c_str());
}

int __cdecl OpenSave(const char* path, const char* mode) {
  if (!path) return 0;
  const char* name = path;
  for (const char* c = path; *c; ++c) if (*c == '/' || *c == '\\') name = c + 1;
  if (_strnicmp(name, "GTAVCsf", 7) == 0) {
    auto& state = State();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (state.selected.empty() || state.failed ||
        _strnicmp(path, state.prefix.c_str(), state.prefix.size()) != 0) return 0;
    if (mode && std::strpbrk(mode, "wa+") && !state.can_write(state.selected)) return 0;
  }
  // Use the game's CRT FILE*, not the ASI's separate statically linked CRT.
  return plugin::CallAndReturn<int, kGameFopen10, const char*, const char*>(path, mode);
}
bool IsCall(unsigned int site, unsigned int target) {
  return *reinterpret_cast<unsigned char*>(site) == 0xe8 &&
         site + 5 + *reinterpret_cast<int*>(site + 1) == target;
}
}

bool InstallSaveIsolation(std::function<void(const std::string&)> log,
                          std::function<bool(const std::string&)> can_write) {
  auto& state = State();
  state.log = std::move(log);
  state.can_write = std::move(can_write);
  if (plugin::GetGameVersion() != GAME_10EN ||
      !IsCall(kSavePrefixFormatCall10, kGameSprintf10) ||
      !IsCall(kFileOpenCall10, kGameFopen10) ||
      !IsCall(kFileWriteOpenCall10, kGameFopen10)) {
    state.log("Save isolation hook unavailable. Archipelago connection disabled.");
    return false;
  }
  injector::MakeCALL(kSavePrefixFormatCall10, &MakePrefix, true);
  injector::MakeCALL(kFileOpenCall10, &OpenSave, true);
  // This is the fopen call INSIDE OpenFileForWriting, with both path and mode
  // already pushed, so it has the same signature as OpenSave.
  injector::MakeCALL(kFileWriteOpenCall10, &OpenSave, true);
  state.installed = true;
  return true;
}

bool PrepareSaveSeed(const std::string& hash) {
  auto& state = State();
  std::lock_guard<std::mutex> lock(state.mutex);
  if (!state.installed || state.failed) throw std::runtime_error("Automatic save isolation is unavailable.");
  if (!state.requested.empty() && state.requested != hash)
    throw std::runtime_error("Restart Vice City to change seed or slot; the current saves stay isolated.");
  state.requested = hash;
  return state.selected == hash;
}

void TickSaveIsolation() {
  auto& state = State();
  std::unique_lock<std::mutex> lock(state.mutex);
  if (!state.installed || state.failed || !state.game_prefix ||
      state.requested.empty() || !state.selected.empty()) return;
  // SwitchToNewScreen renders and ends its own frames. Calling it inside a
  // drawing callback clears the outer frame's current camera and crashes the
  // next draw (VC 1.0: 0x6664BA). Defer until a frontend/game update instead.
  if (!RwEngineInstance || RwCameraGetCurrentCamera()) return;
  try {
    const auto folder = SeedSaveDirectory(state.documents, state.requested);
    // Refuse junctions/symlinks in the managed subdirectories, including existing
    // save files. A redirected save must never resolve onto a career save.
    for (const auto& path : {folder.parent_path(), folder}) {
      const DWORD attributes = GetFileAttributesW(path.c_str());
      if (attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_REPARSE_POINT))
        throw std::runtime_error("Save isolation refuses linked save directories.");
    }
    std::filesystem::create_directories(folder);
    for (const auto& file : std::filesystem::directory_iterator(folder)) {
      if (GetFileAttributesW(file.path().c_str()) & FILE_ATTRIBUTE_REPARSE_POINT)
        throw std::runtime_error("Save isolation refuses linked save files.");
    }
    state.prefix = (folder / "GTAVCsf").string();
    std::snprintf(state.game_prefix, 256, "%s", state.prefix.c_str());
    state.selected = state.requested;
    lock.unlock(); // scanning and menu transitions reenter the game's file routines
    // The frontend caches slot metadata at startup, before a seed is selected.
    // Changing pages alone does not rescan it; refresh now, even without a game.
    PcSaveHelper.PopulateSlotInfo();
    // Never apply a menu selection from the previous directory.
    if (FrontEndMenuManager.m_bMenuActive) {
      FrontEndMenuManager.SwitchToNewScreen(FrontEndMenuManager.m_bGameNotLoaded ?
                                           MENUPAGE_START_MENU : MENUPAGE_PAUSE_MENU);
    }
    state.log("Automatic saves: " + folder.string());
  } catch (const std::exception& error) {
    if (!lock.owns_lock()) lock.lock();
    state.failed = true;
    lock.unlock();
    state.log(error.what());
  }
}
}
