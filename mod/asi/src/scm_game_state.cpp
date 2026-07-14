#include "scm_game_state.hpp"

#include <plugin.h>
#include <CMessages.h>
#include <CTheScripts.h>

namespace gtavc {
namespace {
// Fixed part of the reserved layout, matching apworld scm.py: the seed hash
// occupies four globals from $9000, sixteen hex characters packed four per
// global. The unlock and completion globals are dynamic (from the config).
constexpr int kSeedHashBase = 9000;
constexpr int kSeedHashGlobalCount = 4;
constexpr int kSeedHashLength = kSeedHashGlobalCount * 4;
}  // namespace

ScmGameState::ScmGameState(Logger logger) : logger_(std::move(logger)) {}

int ScmGameState::GetGlobal(int index) {
  return *reinterpret_cast<int*>(&CTheScripts::ScriptSpace[index * 4]);
}

void ScmGameState::SetGlobal(int index, int value) {
  *reinterpret_cast<int*>(&CTheScripts::ScriptSpace[index * 4]) = value;
}

std::string ScmGameState::ReadSeedHash() {
  char characters[kSeedHashLength + 1] = {0};
  for (int slot = 0; slot < kSeedHashGlobalCount; ++slot) {
    const int packed = GetGlobal(kSeedHashBase + slot);
    for (int byte = 0; byte < 4; ++byte) {
      characters[slot * 4 + byte] = static_cast<char>((packed >> (byte * 8)) & 0xFF);
    }
  }
  const std::string hash(characters);
  // A blank block means no game has stamped a hash yet.
  return hash.find_first_not_of('\0') == std::string::npos ? std::string() : hash;
}

void ScmGameState::WriteSeedHash(const std::string& hash) {
  for (int slot = 0; slot < kSeedHashGlobalCount; ++slot) {
    int packed = 0;
    for (int byte = 0; byte < 4; ++byte) {
      const int index = slot * 4 + byte;
      const int character = (index < static_cast<int>(hash.size())) ? static_cast<unsigned char>(hash[index]) : 0;
      packed |= character << (byte * 8);
    }
    SetGlobal(kSeedHashBase + slot, packed);
  }
}

void ScmGameState::ApplyConfig(const std::map<std::int64_t, int>& item_globals,
                               const std::map<int, std::int64_t>& completion_watch) {
  std::lock_guard<std::mutex> lock(mutex_);
  item_globals_ = item_globals;
  completion_watch_ = completion_watch;
  location_to_global_.clear();
  for (const auto& [global_index, location] : completion_watch_) {
    location_to_global_[location] = global_index;
  }
  if (logger_) logger_("config applied");
}

std::string ScmGameState::SeedHash() {
  std::lock_guard<std::mutex> lock(mutex_);
  return cached_seed_hash_;
}

void ScmGameState::StampSeedHash(const std::string& expected) {
  std::lock_guard<std::mutex> lock(mutex_);
  pending_stamp_ = expected;
  stamp_pending_ = true;
}

void ScmGameState::ApplyItems(const std::vector<std::pair<std::int64_t, std::int64_t>>& items) {
  std::lock_guard<std::mutex> lock(mutex_);
  items_ = items;
  items_dirty_ = true;
}

void ScmGameState::MarkChecked(const std::vector<std::int64_t>& locations) {
  std::lock_guard<std::mutex> lock(mutex_);
  for (const std::int64_t location : locations) {
    const auto it = location_to_global_.find(location);
    if (it != location_to_global_.end()) reported_.insert(it->second);
  }
}

void ScmGameState::ShowToast(const std::string& text) {
  std::lock_guard<std::mutex> lock(mutex_);
  pending_toasts_.push_back(text);
}

std::vector<std::int64_t> ScmGameState::TakeNewChecks() {
  std::lock_guard<std::mutex> lock(mutex_);
  std::vector<std::int64_t> drained;
  drained.swap(outbound_checks_);
  return drained;
}

bool ScmGameState::TakeGoalReached() {
  // The goal is derived client-side from the finale location check, so the ASI
  // never reports it separately.
  return false;
}

void ScmGameState::OnGameFrame() {
  std::lock_guard<std::mutex> lock(mutex_);

  cached_seed_hash_ = ReadSeedHash();
  if (stamp_pending_) {
    if (cached_seed_hash_.empty() && !pending_stamp_.empty()) {
      WriteSeedHash(pending_stamp_);
      cached_seed_hash_ = pending_stamp_;
      if (logger_) logger_("stamped seed hash on new game");
    }
    stamp_pending_ = false;
  }

  if (items_dirty_) {
    // Re-derive every unlock global from the full item list: zero each distinct
    // unlock global, then tally received copies per global.
    std::map<int, int> counts;
    for (const auto& [item_id, global_index] : item_globals_) counts[global_index] = 0;
    for (const auto& [received_index, item_id] : items_) {
      const auto it = item_globals_.find(item_id);
      if (it != item_globals_.end()) ++counts[it->second];
    }
    for (const auto& [global_index, count] : counts) SetGlobal(global_index, count);
    items_dirty_ = false;
    if (logger_) logger_("applied items to unlock globals");
  }

  for (const auto& [global_index, location] : completion_watch_) {
    if (reported_.count(global_index)) continue;
    if (GetGlobal(global_index) != 0) {
      outbound_checks_.push_back(location);
      reported_.insert(global_index);
    }
  }

  for (const std::string& text : pending_toasts_) {
    CMessages::AddMessageJumpQ(const_cast<char*>(text.c_str()), 4000, 0);
  }
  pending_toasts_.clear();
}

}  // namespace gtavc
