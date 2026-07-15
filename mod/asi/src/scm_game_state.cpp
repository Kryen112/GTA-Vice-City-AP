#include "scm_game_state.hpp"

#include <algorithm>
#include <cstdlib>

#include <plugin.h>
#include <CMessages.h>
#include <CTheScripts.h>
#include <CWorld.h>
#include <CPlayerPed.h>
#include <CWeaponInfo.h>
#include <CStreaming.h>
#include <common.h>

namespace gtavc {
namespace {
// Fixed part of the reserved layout, matching apworld scm.py: the seed hash
// occupies four globals from $9000, sixteen hex characters packed four per
// global. The applied-index is $9005. The unlock, reward, completion, and
// config-flag globals are dynamic (from the config).
constexpr int kSeedHashBase = 9000;
constexpr int kSeedHashGlobalCount = 4;
constexpr int kSeedHashLength = kSeedHashGlobalCount * 4;
constexpr int kAppliedIndexGlobal = 9005;
// The streaming flag the give-weapon script opcode uses (load as a dependency).
constexpr int kStreamModelDependency = 0x04;
// A weapon pickup grants two magazines: a reloaded weapon plus a spare, floored
// so single-load weapons (shotgun/stubby/sniper, magazine 1) still give a usable
// amount rather than two rounds.
constexpr unsigned int kPickupMagazines = 2;
constexpr unsigned int kMinPickupAmmo = 10;
// The pool the random weapon pickup draws from: standard on-foot guns, not the
// heavy ordnance (those are the package rewards) or melee/throwables.
constexpr eWeaponType kWeaponPool[] = {
    WEAPONTYPE_PISTOL, WEAPONTYPE_PYTHON, WEAPONTYPE_SHOTGUN, WEAPONTYPE_SPAS12_SHOTGUN,
    WEAPONTYPE_STUBBY_SHOTGUN, WEAPONTYPE_TEC9, WEAPONTYPE_UZI, WEAPONTYPE_SILENCED_INGRAM,
    WEAPONTYPE_MP5, WEAPONTYPE_M4, WEAPONTYPE_RUGER, WEAPONTYPE_SNIPERRIFLE, WEAPONTYPE_LASERSCOPE,
};
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
                               const std::map<int, std::int64_t>& completion_watch,
                               const std::map<std::int64_t, ItemEffect>& item_effects,
                               const std::map<int, int>& config_globals) {
  std::lock_guard<std::mutex> lock(mutex_);
  item_globals_ = item_globals;
  item_effects_ = item_effects;
  config_globals_ = config_globals;
  completion_watch_ = completion_watch;
  location_to_global_.clear();
  for (const auto& [global_index, location] : completion_watch_) {
    location_to_global_[location] = global_index;
  }
  if (logger_) logger_("config applied");
}

void ScmGameState::ApplyEffect(const ItemEffect& effect) {
  CPlayerPed* player = FindPlayerPed();
  if (player == nullptr) return;
  if (effect.type == "cash") {
    CWorld::Players[0].m_nMoney += effect.amount;
  } else if (effect.type == "health") {
    player->m_fHealth = static_cast<float>(CWorld::Players[0].m_nMaxHealth);
  } else if (effect.type == "armor") {
    player->m_fArmour = static_cast<float>(CWorld::Players[0].m_nMaxArmour);
  } else if (effect.type == "weapon") {
    // A random weapon pickup: give the gun if its slot is free, add two of its
    // magazines if already held, or top up the different gun occupying the slot,
    // never overwriting a weapon the player already has.
    const int pool_size = sizeof(kWeaponPool) / sizeof(kWeaponPool[0]);
    const eWeaponType weapon = kWeaponPool[std::rand() % pool_size];
    const int slot = player->GetWeaponSlot(weapon);
    if (slot < 0 || slot >= 10) return;
    CWeapon& held = player->m_aWeapons[slot];
    if (held.m_eWeaponType != weapon && held.m_eWeaponType != WEAPONTYPE_UNARMED) {
      const CWeaponInfo* held_info = CWeaponInfo::GetWeaponInfo(held.m_eWeaponType);
      if (held_info != nullptr) {
        held.m_nAmmoTotal += std::max(kMinPickupAmmo, kPickupMagazines * held_info->m_nAmountofAmmunition);
      }
      return;
    }
    const CWeaponInfo* info = CWeaponInfo::GetWeaponInfo(weapon);
    if (info == nullptr) return;
    if (held.m_eWeaponType == WEAPONTYPE_UNARMED) {
      // Giving a new weapon needs its model streamed in first, as the SCM's own
      // give-weapon opcode does; an already-held weapon already has it loaded.
      if (info->m_nModelId >= 0) CStreaming::RequestModel(info->m_nModelId, kStreamModelDependency);
      if (info->m_nModel2Id >= 0) CStreaming::RequestModel(info->m_nModel2Id, kStreamModelDependency);
      CStreaming::LoadAllRequestedModels(false);
    }
    player->GiveWeapon(weapon, std::max(kMinPickupAmmo, kPickupMagazines * info->m_nAmountofAmmunition), false);
  }
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

  // Only touch the game's script memory once a stamped game is actually
  // running. In the frontend menu ScriptSpace holds no meaningful state, and a
  // baseline taken there would be wrong.
  const bool game_active = !cached_seed_hash_.empty();
  if (!game_active) {
    baseline_captured_ = false;
    return;
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

  // Stamp the config flags every frame so the SCM knows which reward groups are
  // shuffled, even after the new-game zeroing clears them.
  for (const auto& [global_index, value] : config_globals_) {
    SetGlobal(global_index, value);
  }

  // Apply one-shot consumables (cash, weapon, health, armour) once, past the
  // saved applied-index. Only when the player exists, so a grant is never lost
  // to a still-loading world; the index counts consumable items in received
  // order and persists in the save.
  if (FindPlayerPed() != nullptr) {
    const int applied = GetGlobal(kAppliedIndexGlobal);
    int consumable_count = 0;
    for (const auto& [received_index, item_id] : items_) {
      const auto effect = item_effects_.find(item_id);
      if (effect == item_effects_.end()) continue;
      if (consumable_count >= applied) ApplyEffect(effect->second);
      ++consumable_count;
    }
    if (consumable_count > applied) {
      SetGlobal(kAppliedIndexGlobal, consumable_count);
      if (logger_) logger_("applied one-shot consumables");
    }
  }

  std::map<int, int> current;
  for (const auto& entry : completion_watch_) {
    current[entry.first] = GetGlobal(entry.first);
  }
  // Snapshot the completion globals as this game starts, so a real completion
  // shows up as a change from a zero baseline. Globals nonzero at the baseline
  // are not declared completion globals and are never reported.
  if (!baseline_captured_) {
    baseline_ = current;
    baseline_captured_ = true;
    if (logger_) logger_("captured completion baseline");
  }
  for (const std::int64_t location :
       DetectCompletedLocations(completion_watch_, baseline_, current, reported_)) {
    outbound_checks_.push_back(location);
  }

  for (const std::string& text : pending_toasts_) {
    CMessages::AddMessageJumpQ(const_cast<char*>(text.c_str()), 4000, 0);
  }
  pending_toasts_.clear();
}

}  // namespace gtavc
