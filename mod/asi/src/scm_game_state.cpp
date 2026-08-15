#include "scm_game_state.hpp"

#include <algorithm>
#include <array>
#include <cstdlib>

#include "game_addresses.hpp"
#include "scm_packages.hpp"

#include <plugin.h>
#include <CMessages.h>
#include <CTheScripts.h>
#include <CWorld.h>
#include <CPlayerPed.h>
#include <CWeaponInfo.h>
#include <CStreaming.h>
#include <CPickups.h>
#include <ePickupType.h>
#include <CPad.h>
#include <CTimer.h>
#include <CWanted.h>
#include <CPools.h>
#include <CVehicle.h>
#include <CAutomobile.h>
#include <CPed.h>
#include <CWeather.h>
#include <eModelID.h>
#include <eObjective.h>
#include <eWeather.h>
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
// The radio contract, matching apworld scm.py: the randomized flag, nine
// station unlock globals (engine station id order), nine resolve globals the
// ASI recomputes each frame, and the retune request global the APRADIO
// watcher consumes (encoded station id plus one, so the zero-initialized
// global idles).
constexpr int kRadioRandomizedGlobal = 9379;
constexpr int kRadioUnlockBase = 9380;
constexpr int kRadioResolveBase = 9389;
constexpr int kRadioRequestGlobal = 9398;
// A script-channel request for station 9 selects the MP3 player, which the
// game remaps to the city ambience: the radio-off soundscape. The ambience
// track id equals the off position (10), so the commit's writeback leaves the
// vehicle byte exactly where the enforcer put it, for the off path and the
// station path alike; the correction can never oscillate.
constexpr int kRadioAmbientRequest = 9;

// Whether the vehicle plays the police scanner instead of its station byte,
// mirroring the game's own test: the fixed model set, then the siren flag,
// with the ice cream van and the Hunter explicitly on music.
bool UsesPoliceScanner(CVehicle* vehicle) {
  switch (vehicle->m_nModelIndex) {
    case MODEL_VCNMAV:
    case MODEL_POLMAV:
    case MODEL_COASTG:
    case MODEL_RHINO:
    case MODEL_BARRACKS:
      return true;
    case MODEL_MRWHOOP:
    case MODEL_HUNTER:
      return false;
    default:
      break;
  }
  return vehicle->UsesSiren();
}
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

// Trap tuning. The sped-up and slowed clock imitate ONSPEED and BOOOOOORING; the
// wanted spike caps at the game maximum; stormy weather is the rain state
// CATSANDDOGS forces. The default duration matches data.TRAP_DURATION_SECONDS.
constexpr float kSpeedUpTimeScale = 2.0f;
constexpr float kSlowDownTimeScale = 0.35f;
constexpr float kNormalTimeScale = 1.0f;
constexpr int kMaxWantedLevel = 6;
constexpr short kStormyWeather = WEATHER_RAINY;
constexpr int kDefaultTrapSeconds = 30;

// The trap duration in real milliseconds, from the descriptor's seconds param.
unsigned int TrapDurationMs(const ItemEffect& effect) {
  const int seconds = (effect.has_amount && effect.amount > 0) ? effect.amount : kDefaultTrapSeconds;
  return static_cast<unsigned int>(seconds) * 1000u;
}
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
                               const std::map<int, int>& config_globals,
                               const std::vector<PackageLocation>& package_locations) {
  std::lock_guard<std::mutex> lock(mutex_);
  item_globals_ = item_globals;
  item_effects_ = item_effects;
  config_globals_ = config_globals;
  completion_watch_ = completion_watch;
  package_locations_ = package_locations;
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
  } else if (effect.type == "clear_wanted") {
    // Drop the wanted level to zero, like the LEAVEMEALONE cheat. SetWantedLevel
    // clears the queued crimes and recomputes, so pursuit actually ends, unlike
    // the trap's SetWantedLevelNoDrop, which only ever raises the level.
    if (player->m_pWanted != nullptr) player->m_pWanted->SetWantedLevel(0);
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

bool ScmGameState::PlayerIsControllable() {
  const CPad* pad = CPad::GetPad(0);
  // No pad yet (still loading) reads as not controllable, so a trap waits.
  if (pad == nullptr) return false;
  return pad->DisablePlayerControls == 0;
}

unsigned int ScmGameState::RealTimeMs() {
  return static_cast<unsigned int>(CTimer::m_snTimeInMillisecondsPauseMode);
}

void ScmGameState::ExplodeAllVehicles() {
  CPlayerPed* player = FindPlayerPed();
  CPool<CVehicle, CAutomobile>* pool = CPools::ms_pVehiclePool;
  if (pool == nullptr) return;
  for (int index = 0; index < pool->m_nSize; ++index) {
    CVehicle* vehicle = pool->GetAt(index);
    if (vehicle != nullptr) vehicle->BlowUpCar(player);
  }
}

void ScmGameState::MakePedestriansHostile() {
  CPlayerPed* player = FindPlayerPed();
  CPool<CPed, CPlayerPed>* pool = CPools::ms_pPedPool;
  if (player == nullptr || pool == nullptr) return;
  for (int index = 0; index < pool->m_nSize; ++index) {
    CPed* ped = pool->GetAt(index);
    if (ped == nullptr || ped == player) continue;
    ped->SetObjective(OBJECTIVE_KILL_CHAR_ON_FOOT, static_cast<void*>(player));
  }
}

void ScmGameState::CalmPedestrians() {
  CPlayerPed* player = FindPlayerPed();
  CPool<CPed, CPlayerPed>* pool = CPools::ms_pPedPool;
  if (pool == nullptr) return;
  for (int index = 0; index < pool->m_nSize; ++index) {
    CPed* ped = pool->GetAt(index);
    if (ped == nullptr || ped == player) continue;
    ped->ClearObjective();
  }
}

void ScmGameState::EnforceRadioStations() {
  if (GetGlobal(kRadioRandomizedGlobal) == 0) return;
  std::array<bool, kRadioStationCount> unlocked{};
  bool any_unlocked = false;
  for (int station = 0; station < kRadioStationCount; ++station) {
    unlocked[station] = GetGlobal(kRadioUnlockBase + station) >= 1;
    any_unlocked = any_unlocked || unlocked[station];
  }
  // No station received yet (the resync has not landed): leave the radio
  // alone rather than lock every vehicle onto one arbitrary station.
  if (!any_unlocked) return;
  const std::array<int, kRadioStationCount> resolve = ResolveRadioStations(unlocked);
  for (int station = 0; station < kRadioStationCount; ++station) {
    SetGlobal(kRadioResolveBase + station, resolve[station]);
  }
  CPool<CVehicle, CAutomobile>* pool = CPools::ms_pVehiclePool;
  if (pool == nullptr) return;
  CVehicle* player_vehicle = FindPlayerVehicle();
  for (int index = 0; index < pool->m_nSize; ++index) {
    CVehicle* vehicle = pool->GetAt(index);
    if (vehicle == nullptr || vehicle == player_vehicle) continue;
    // Scanner vehicles play police chatter regardless of the byte; leave
    // them fully alone, matching the option's scanner-untouched promise.
    if (UsesPoliceScanner(vehicle)) continue;
    const int station = vehicle->m_nRadioStation;
    // The off position stays: the radio-less spawns (the RC vehicles) and any
    // radio left off.
    if (station >= kRadioOff) continue;
    const int corrected = CorrectedVehicleStation(station, resolve);
    if (corrected != station) {
      vehicle->m_nRadioStation = static_cast<unsigned char>(corrected);
    }
  }
  if (player_vehicle == nullptr || UsesPoliceScanner(player_vehicle)) {
    retune_logical_presses_ = 0;
    retune_written_presses_ = 0;
    return;
  }
  const int station = player_vehicle->m_nRadioStation;
  if (station < kRadioOff && !(station < kRadioStationCount && unlocked[station])) {
    // A locked station (or the MP3 player) reached the player's vehicle, from
    // an entry the remap missed, the pause-menu selector, or a commit on an
    // executable where press shaping is unavailable. The music manager
    // re-reads the byte only on entry or on a commit, so fixing the byte
    // alone leaves the wrong audio playing; the APRADIO watcher's
    // set_radio_channel switches the live track.
    const int snapped = NextAllowedTuning(station, unlocked);
    player_vehicle->m_nRadioStation = static_cast<unsigned char>(snapped);
    const int request = (snapped == kRadioOff) ? kRadioAmbientRequest : snapped;
    SetGlobal(kRadioRequestGlobal, request + 1);
  }
  // Shape any pending scroll after the snap, from the corrected byte, so the
  // vanilla commit itself lands only on unlocked stations and the scroll
  // preview never names a locked one.
  RewriteRetunePresses(player_vehicle, unlocked);
}

void ScmGameState::RewriteRetunePresses(
    CVehicle* player_vehicle, const std::array<bool, kRadioStationCount>& unlocked) {
  // The press static is pinned for the classic 1.0 executable only; any other
  // build keeps vanilla scrolling and relies on the post-commit correction.
  if (plugin::GetGameVersion() != GAME_10EN) return;
  int* presses = reinterpret_cast<int*>(kRetunePressesAddress10);
  // The byte only changes at the commit, so it is the stable scroll origin.
  const RetunePressPlan plan = PlanRetunePresses(
      *presses, retune_logical_presses_, retune_written_presses_,
      player_vehicle->m_nRadioStation, unlocked);
  if (plan.write_needed) *presses = plan.written_presses;
  retune_logical_presses_ = plan.logical_presses;
  retune_written_presses_ = plan.written_presses;
}

void ScmGameState::ApplyOneShot(const ItemEffect& effect) {
  if (effect.type.rfind("trap_", 0) == 0) {
    ApplyTrap(effect);
  } else {
    ApplyEffect(effect);
  }
}

void ScmGameState::ApplyTrap(const ItemEffect& effect) {
  CPlayerPed* player = FindPlayerPed();
  if (player == nullptr) return;
  if (effect.type == "trap_wanted") {
    // Raise the wanted level by the descriptor's stars, capped at the maximum.
    if (player->m_pWanted != nullptr) {
      const int raised = static_cast<int>(player->m_pWanted->m_nWantedLevel) +
                         (effect.has_amount ? effect.amount : 1);
      player->m_pWanted->SetWantedLevelNoDrop(std::min(kMaxWantedLevel, raised));
    }
  } else if (effect.type == "trap_explode_cars") {
    ExplodeAllVehicles();
  } else if (effect.type == "trap_weather") {
    // Weather applies any time, so it is fired here with no control gate.
    CWeather::ForceWeatherNow(kStormyWeather);
  } else if (effect.type == "trap_hostile_peds") {
    hostile_pedestrians_active_ = true;
    hostile_pedestrians_until_ = RealTimeMs() + TrapDurationMs(effect);
    MakePedestriansHostile();
  } else if (effect.type == "trap_speed_up") {
    time_scale_trap_active_ = true;
    time_scale_trap_factor_ = kSpeedUpTimeScale;
    time_scale_trap_until_ = RealTimeMs() + TrapDurationMs(effect);
    CTimer::ms_fTimeScale = kSpeedUpTimeScale;
  } else if (effect.type == "trap_slow_down") {
    time_scale_trap_active_ = true;
    time_scale_trap_factor_ = kSlowDownTimeScale;
    time_scale_trap_until_ = RealTimeMs() + TrapDurationMs(effect);
    CTimer::ms_fTimeScale = kSlowDownTimeScale;
  }
}

void ScmGameState::UpdateTimedTraps() {
  const unsigned int now = RealTimeMs();
  if (time_scale_trap_active_) {
    // Signed difference so the deadline comparison survives the clock wrapping.
    if (static_cast<int>(now - time_scale_trap_until_) >= 0) {
      CTimer::ms_fTimeScale = kNormalTimeScale;
      time_scale_trap_active_ = false;
    } else {
      // Reassert each frame so the game's own time-scale updates cannot drift it.
      CTimer::ms_fTimeScale = time_scale_trap_factor_;
    }
  }
  if (hostile_pedestrians_active_) {
    if (static_cast<int>(now - hostile_pedestrians_until_) >= 0) {
      CalmPedestrians();
      hostile_pedestrians_active_ = false;
    } else {
      MakePedestriansHostile();
    }
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

void ScmGameState::DetectCollectedPackages() {
  if (package_locations_.empty()) return;
  // World positions of every collectable pickup still present in the pool. The
  // 336 pool size matches plugin-sdk's CPickup (&aPickUps)[336].
  std::vector<WorldPoint> present;
  for (int index = 0; index < 336; ++index) {
    const CPickup& pickup = CPickups::aPickUps[index];
    if (pickup.bPickupType == PICKUP_COLLECTABLE1 && !pickup.bRemoved) {
      present.push_back({pickup.vecPos.x, pickup.vecPos.y, pickup.vecPos.z});
    }
  }
  // The persistent SCM completion global records a package already collected,
  // this session or restored from a save.
  std::set<int> already_collected;
  for (const PackageLocation& package : package_locations_) {
    if (GetGlobal(package.completion_global) != 0) {
      already_collected.insert(package.completion_global);
    }
  }
  for (int completion_global : DetectNewlyCollectedPackages(
           package_locations_, present, package_seen_present_, already_collected)) {
    SetGlobal(completion_global, 1);
  }
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
    // Forget which packages were seen present so a fresh game re-derives from
    // its own pool. Tied to the game boundary, not to config: a bridge
    // reconnect keeps the set intact, so a package collected mid-session is
    // never missed by a clear between its present and gone frames.
    package_seen_present_.clear();
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

  // Apply one-shot effects (consumables and traps) once, past the saved
  // applied-index. Only when the player exists, so a grant is never lost to a
  // still-loading world; the index counts effect items in received order and
  // persists in the save. The chaos traps defer until the player is
  // controllable: planning stops at the first deferred trap so the index never
  // skips it, and it is retried on a later frame.
  if (FindPlayerPed() != nullptr) {
    const int applied = GetGlobal(kAppliedIndexGlobal);
    const EffectPlan plan =
        PlanEffects(items_, item_effects_, applied, PlayerIsControllable());
    for (const ItemEffect& effect : plan.to_apply) ApplyOneShot(effect);
    if (plan.new_applied_index != applied) {
      SetGlobal(kAppliedIndexGlobal, plan.new_applied_index);
      if (logger_) logger_("applied one-shot effects");
    }
  }

  // Hold or revert the timed traps (sped-up or slowed clock, hostile
  // pedestrians) whether or not new items arrived this frame.
  UpdateTimedTraps();

  // Keep every vehicle radio on an unlocked station while the randomize
  // option is on. Reads the config and unlock globals written above, so a
  // save's own persisted state keeps it working offline too.
  EnforceRadioStations();

  // Set each collected hidden package's completion global from the pickup pool,
  // so the poll below reports every package as its own check. Only when the world
  // is loaded, so the pool reflects the placed packages.
  if (FindPlayerPed() != nullptr) DetectCollectedPackages();

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
