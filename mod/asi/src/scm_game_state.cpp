#include "scm_game_state.hpp"

#include <algorithm>
#include <array>
#include <cstdlib>

#include "game_addresses.hpp"
#include "scm_packages.hpp"

#include <plugin.h>
#include <CHud.h>
#include <CMessages.h>
#include <CModelInfo.h>
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
#include <ePedStates.h>
#include <eWeather.h>
#include <common.h>

namespace gtavc {

// The planner's appearance ids are a copy of the game's own, kept free of
// game headers so the console self-test can exercise the planner. This is
// the one place that sees both, so it holds them together.
static_assert(kAppearanceAutomobile == VEHICLE_APPEARANCE_AUTOMOBILE, "automobile appearance");
static_assert(kAppearanceBike == VEHICLE_APPEARANCE_BIKE, "bike appearance");
static_assert(kAppearanceHeli == VEHICLE_APPEARANCE_HELI, "heli appearance");
static_assert(kAppearanceBoat == VEHICLE_APPEARANCE_BOAT, "boat appearance");
static_assert(kAppearancePlane == VEHICLE_APPEARANCE_PLANE, "plane appearance");

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
constexpr int kRadioRandomizedGlobal = 9380;
constexpr int kRadioUnlockBase = 9381;
constexpr int kRadioResolveBase = 9390;
constexpr int kRadioRequestGlobal = 9399;
// A script-channel request for station 9 selects the MP3 player, which the
// game remaps to the city ambience: the radio-off soundscape. The ambience
// track id equals the off position (10), so the commit's writeback leaves the
// vehicle byte exactly where the enforcer put it, for the off path and the
// station path alike; the correction can never oscillate.
constexpr int kRadioAmbientRequest = 9;
// The minimap contract, matching apworld scm.py: the shuffled flag and the
// Minimap item's unlock global. Both are ASI-facing only; the main.scm never
// reads them, but as reserved globals they persist inside saves, so the
// enforcement keeps working offline from a save.
constexpr int kMinimapShuffledGlobal = 9415;
constexpr int kMinimapUnlockGlobal = 9416;
// The game's pickup pool size, matching plugin-sdk's CPickup (&aPickUps)[336].
constexpr int kPickupPoolSize = 336;
// The enforcement frame on which a still-unmatched layout slot is logged:
// hundreds of frames past the init mission's pickup creation window (which
// also advances per frame), so slots still being placed at the start are
// never reported as missing.
constexpr int kPickupUnmatchedLogFrame = 600;

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
// wanted spike caps at the game maximum; a weather trap carries its eWeather id
// as the param, falling back to the rain state CATSANDDOGS forces. Drunk vision
// uses the Boomshine Saigon drive's own values: full drunk visuals and an
// eight-frame steering lag (the buffer holds ten). The default duration matches
// data.TRAP_DURATION_SECONDS.
constexpr float kSpeedUpTimeScale = 2.0f;
constexpr float kSlowDownTimeScale = 0.35f;
constexpr float kNormalTimeScale = 1.0f;
constexpr int kMaxWantedLevel = 6;
constexpr short kStormyWeather = WEATHER_RAINY;
constexpr unsigned char kDrunkVisualsLevel = 255;
constexpr int kDrunkSteeringDelay = 8;
constexpr int kDefaultTrapSeconds = 30;

// The trap duration in real milliseconds, from the descriptor's seconds param.
unsigned int TrapDurationMs(const ItemEffect& effect) {
  const int seconds = (effect.has_amount && effect.amount > 0) ? effect.amount : kDefaultTrapSeconds;
  return static_cast<unsigned int>(seconds) * 1000u;
}

// Player-facing names for the ability status list, AbilityIndex order.
constexpr const char* kAbilityNames[kAbilityCount] = {
    "Sprint", "Jump", "Crouch", "Land Vehicles", "Sea Vehicles",
    "Air Vehicles", "Weapon Equip", "Wallet",
};
// The blocked-attempt toast per ability. The wallet has no blockable input,
// so it never toasts; the status key and the client window carry its state.
constexpr const char* kAbilityBlockedText[kAbilityCount] = {
    "Sprinting is locked.", "Jumping is locked.", "Crouching is locked.",
    "Land vehicles are locked.", "Sea vehicles are locked.",
    "Air vehicles are locked.", "Weapons are locked.", nullptr,
};
// The key listing every configured ability's locked or unlocked state.
constexpr int kAbilityStatusKey = VK_F6;
// The kill-frenzy skull's model name in the game's object definitions.
constexpr const char* kKillFrenzyModelName = "killfrenzy";

// Whether the foreground window belongs to this game, so a key pressed in
// another application while the player is alt-tabbed is ignored.
bool GameWindowHasFocus() {
  DWORD process_id = 0;
  GetWindowThreadProcessId(GetForegroundWindow(), &process_id);
  return process_id == GetCurrentProcessId();
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
                               const std::vector<PackageLocation>& package_locations,
                               const std::vector<PickupTarget>& pickup_targets) {
  std::lock_guard<std::mutex> lock(mutex_);
  item_globals_ = item_globals;
  item_effects_ = item_effects;
  config_globals_ = config_globals;
  completion_watch_ = completion_watch;
  package_locations_ = package_locations;
  pickup_targets_ = pickup_targets;
  pickup_enforce_frames_ = 0;
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
  // No pad yet (still loading) reads as not controllable, so items wait.
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

void ScmGameState::EnforceMinimap() {
  const MinimapPlan plan = PlanMinimapEnforcement(
      GetGlobal(kMinimapShuffledGlobal) != 0,
      GetGlobal(kMinimapUnlockGlobal) != 0,
      minimap_forcing_hidden_);
  if (plan.action == MinimapAction::kForceHidden) {
    // The DISPLAY_RADAR opcode's backing static: while set, the whole radar
    // disc (map, blips, north marker) stops drawing. Asserted every frame, so
    // a vanilla script showing the radar cannot bring it back early.
    CHud::bScriptDontDisplayRadar = true;
  } else if (plan.action == MinimapAction::kReleaseOnce) {
    // The item arrived: clear the flag once and hand it back to the game, so
    // the vanilla missions that hide the radar keep their hide afterwards.
    CHud::bScriptDontDisplayRadar = false;
  }
  minimap_forcing_hidden_ = plan.forcing;
}

void ScmGameState::ToastAbilityBlocked(int ability) {
  const char* text = kAbilityBlockedText[ability];
  if (text == nullptr) return;
  const unsigned int now = RealTimeMs();
  if (!ShouldShowAbilityToast(now, ability_toast_shown_[ability],
                              ability_toast_last_ms_[ability])) {
    return;
  }
  ability_toast_shown_[ability] = true;
  ability_toast_last_ms_[ability] = now;
  // Queued, not shown here: the frame's own toast drain owns the message
  // strings and their lifetime, so every toast takes one path. The caller
  // already holds the lock, so the queue is touched directly.
  pending_toasts_.push_back(text);
}

void ScmGameState::ToastAbilityStatus(
    const AbilityLocks& locked, const std::array<int, kAbilityCount>& lock_flags) {
  // Only the abilities this seed configured appear; an unselected key is
  // fully vanilla and listing it would only mislead.
  std::string locked_list;
  std::string unlocked_list;
  for (int index = 0; index < kAbilityCount; ++index) {
    if (lock_flags[index] == 0) continue;
    std::string& list = locked[index] ? locked_list : unlocked_list;
    if (!list.empty()) list += ", ";
    list += kAbilityNames[index];
  }
  pending_toasts_.push_back(
      "Locked: " + (locked_list.empty() ? std::string("nothing") : locked_list));
  if (!unlocked_list.empty()) {
    pending_toasts_.push_back("Unlocked: " + unlocked_list);
  }
}

void ScmGameState::EnforceRampageIcons(bool weapon_locked) {
  // Resolve the kill-frenzy skull model by name; the SCM creates every
  // rampage icon from it, so the pool entries carry its id. Only a hit
  // latches: a miss (the model table not populated yet) retries on the next
  // frame rather than disabling the hold for the rest of the session, and
  // the diagnostic is logged once per game.
  if (kill_frenzy_model_ < 0) {
    int model = -1;
    if (CModelInfo::GetModelInfo(kKillFrenzyModelName, &model) != nullptr) {
      kill_frenzy_model_ = model;
    } else {
      if (!kill_frenzy_lookup_logged_ && logger_) {
        logger_("ability locks: kill frenzy model not found yet, rampage icons stay vanilla");
      }
      kill_frenzy_lookup_logged_ = true;
      return;
    }
  }
  for (int index = 0; index < kPickupPoolSize; ++index) {
    CPickup& pickup = CPickups::aPickUps[index];
    if (pickup.bPickupType == 0) continue;
    if (static_cast<int>(pickup.nModelId) != kill_frenzy_model_) continue;
    const RampageIconAction action = PlanRampageIcon(
        weapon_locked,
        IsVehicleRampagePickup(pickup.vecPos.x, pickup.vecPos.y),
        pickup.vecPos.z);
    if (action == RampageIconAction::kLeaveAlone) continue;
    pickup.vecPos.z += (action == RampageIconAction::kLower)
                           ? -kRampageLowerOffset
                           : kRampageLowerOffset;
    // Drop the visible objects the way the game's own remove does; the
    // pickup update recreates them at the moved position on the next frame.
    if (pickup.pObject != nullptr) {
      CObject* object = static_cast<CObject*>(pickup.pObject);
      CWorld::Remove(object);
      delete object;
      pickup.pObject = nullptr;
    }
    if (pickup.pExtraObject != nullptr) {
      CObject* extra_object = static_cast<CObject*>(pickup.pExtraObject);
      CWorld::Remove(extra_object);
      delete extra_object;
      pickup.pExtraObject = nullptr;
    }
  }
}

AbilityLocks ScmGameState::ReadAbilityLocks(
    std::array<int, kAbilityCount>& lock_flags) {
  std::array<int, kAbilityCount> unlocks{};
  for (int index = 0; index < kAbilityCount; ++index) {
    lock_flags[index] = GetGlobal(kAbilityLockFlagBase + index);
    unlocks[index] = GetGlobal(kAbilityUnlockBase + index);
  }
  return PlanAbilityLocks(lock_flags, unlocks);
}

void ScmGameState::ApplyAbilityInputLocks() {
  std::lock_guard<std::mutex> lock(mutex_);
  // The seed hash marks a stamped game; before that ScriptSpace holds no
  // meaningful state, exactly as OnGameFrame requires.
  if (ReadSeedHash().empty()) return;
  std::array<int, kAbilityCount> lock_flags{};
  const AbilityLocks locked = ReadAbilityLocks(lock_flags);
  bool any_flag_set = false;
  for (int index = 0; index < kAbilityCount; ++index) {
    any_flag_set = any_flag_set || lock_flags[index] != 0;
  }
  // No key selected this seed: fully vanilla, the pad is never touched.
  if (!any_flag_set) return;
  CPlayerPed* player = FindPlayerPed();
  if (player == nullptr) return;
  const AbilityInputPlan plan = PlanAbilityInputs(
      locked, !player->m_bInVehicle, PlayerIsControllable(),
      CWorld::Players[0].m_pRemoteVehicle != nullptr);

  CPad* pad = CPad::GetPad(0);
  if (pad != nullptr) {
    // An attempt is the raw press before masking; the toast rate-limits
    // itself per ability. Both pad states zero so no just-pressed or
    // just-released edge survives the mask. The fields are the ones the
    // game's own accessors read: sprint ButtonCross, jump ButtonSquare,
    // crouch ShockButtonL, weapon cycle the two second shoulders.
    if (plan.mask_sprint) {
      if (pad->NewState.ButtonCross != 0) ToastAbilityBlocked(kAbilitySprint);
      pad->NewState.ButtonCross = 0;
      pad->OldState.ButtonCross = 0;
    }
    if (plan.mask_jump) {
      if (pad->NewState.ButtonSquare != 0) ToastAbilityBlocked(kAbilityJump);
      pad->NewState.ButtonSquare = 0;
      pad->OldState.ButtonSquare = 0;
    }
    if (plan.mask_crouch) {
      if (pad->NewState.ShockButtonL != 0) ToastAbilityBlocked(kAbilityCrouch);
      pad->NewState.ShockButtonL = 0;
      pad->OldState.ShockButtonL = 0;
    }
    if (plan.mask_weapon_cycle) {
      if (pad->NewState.LeftShoulder2 != 0 || pad->NewState.RightShoulder2 != 0) {
        ToastAbilityBlocked(kAbilityWeaponEquip);
      }
      pad->NewState.LeftShoulder2 = 0;
      pad->OldState.LeftShoulder2 = 0;
      pad->NewState.RightShoulder2 = 0;
      pad->OldState.RightShoulder2 = 0;
    }
  }

  if (plan.force_unarmed && player->m_nCurrentWeapon != 0) {
    // Slot zero is the bare fists. Holding the weapon there every frame is
    // what blocks drive-by (fists cannot fire from a vehicle) and what
    // undoes the engine's auto-equip when an unarmed player walks over a
    // weapon pickup; the weapon stays owned, just not wielded.
    player->SetCurrentWeapon(0);
  }
}

void ScmGameState::EnforceAbilityLocks() {
  std::array<int, kAbilityCount> lock_flags{};
  const AbilityLocks locked = ReadAbilityLocks(lock_flags);
  bool any_flag_set = false;
  for (int index = 0; index < kAbilityCount; ++index) {
    any_flag_set = any_flag_set || lock_flags[index] != 0;
  }
  // No key selected this seed: fully vanilla, nothing to enforce.
  if (!any_flag_set) return;

  // The status key lists every configured ability, locked or unlocked, on
  // its press edge, and only while this game owns the keyboard, so a press
  // meant for another application never reaches the queue.
  const bool status_key_down = GameWindowHasFocus() &&
      (GetAsyncKeyState(kAbilityStatusKey) & 0x8000) != 0;
  if (status_key_down && !ability_status_key_was_down_) {
    ToastAbilityStatus(locked, lock_flags);
  }
  ability_status_key_was_down_ = status_key_down;

  if (locked[kAbilityWallet]) {
    // Tommy cannot hold money: everything earned or received while the
    // wallet is locked burns, cash items included (deliberate, not a bug).
    // Money is state rather than input, so the pin holds through cutscenes.
    CWorld::Players[0].m_nMoney = 0;
    CWorld::Players[0].m_nDisplayMoney = 0;
  }

  CPlayerPed* player = FindPlayerPed();
  // Everything below reads the world: the pickup pool and the player ped are
  // only meaningful once the world is loaded, as the sibling pool walkers
  // require too.
  if (player == nullptr) return;

  EnforceRampageIcons(locked[kAbilityWeaponEquip]);

  // Cancel a player-initiated entry into a locked vehicle class. The entry
  // runs through the player ped's objective, which only the enter-vehicle
  // press sets; scripts seat the player by warping, which never comes
  // through here, so cutscenes keep working.
  if ((locked[kAbilityLandVehicles] || locked[kAbilitySeaVehicles] ||
       locked[kAbilityAirVehicles]) &&
      PlayerIsControllable() &&
      (player->m_nObjective == OBJECTIVE_ENTER_CAR_AS_DRIVER ||
       player->m_nObjective == OBJECTIVE_ENTER_CAR_AS_PASSENGER) &&
      player->m_pObjectiveVehicle != nullptr) {
    const int blocking = VehicleEntryLockIndex(
        locked, player->m_pObjectiveVehicle->GetVehicleAppearance());
    if (blocking != kAbilityCount) {
      player->ClearObjective();
      const int state = static_cast<int>(player->m_ePedState);
      if (state == STATES_OPEN_DOOR || state == STATES_CARJACK ||
          state == STATES_ENTER_CAR || state == STATES_STEAL_CAR) {
        // Already reaching for the door: unwind the enter sequence the way
        // an interrupted jack does, so the ped returns to a clean stand.
        player->QuitEnteringCar();
      }
      ToastAbilityBlocked(blocking);
    }
  }
}

void ScmGameState::OnBeforeWorldProcess() { ApplyAbilityInputLocks(); }

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
    // Weather applies any time, so it is fired here with no control gate. The
    // param is the eWeather id to force. Forcing pins the weather until it is
    // released, so the release follows immediately: the weather switches now
    // and the game's own hourly cycle blends it away naturally, unlike the
    // weather cheats, which stay pinned.
    const short weather =
        effect.has_amount ? static_cast<short>(effect.amount) : kStormyWeather;
    CWeather::ForceWeatherNow(weather);
    CWeather::ReleaseWeather();
  } else if (effect.type == "trap_drunk") {
    // The Boomshine Saigon drunk drive: full-screen blur, camera sway, and
    // lagged steering. Setting the drunkenness field is enough for the visuals;
    // the game itself drives the blur and sway from it every frame. Clearing
    // the fade flag holds the effect at full strength until the deadline.
    player->m_nDrunkenness = kDrunkVisualsLevel;
    player->m_nFadeDrunkenness = 0;
    CPad* pad = CPad::GetPad(0);
    if (pad != nullptr) pad->SetDrunkInputDelay(kDrunkSteeringDelay);
    drunk_trap_active_ = true;
    drunk_trap_until_ = RealTimeMs() + TrapDurationMs(effect);
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
  if (drunk_trap_active_) {
    if (static_cast<int>(now - drunk_trap_until_) >= 0) {
      // Sober up the way a mission end does: raise the fade flag so the game
      // winds the drunkenness down and clears its own blur when it reaches
      // zero (zeroing the field directly would leave the last blur frame
      // stuck), and restore steering immediately. If a mission end or death
      // already sobered the player, both writes are harmless no-ops.
      CPlayerPed* player = FindPlayerPed();
      if (player != nullptr) player->m_nFadeDrunkenness = 1;
      CPad* pad = CPad::GetPad(0);
      if (pad != nullptr) pad->SetDrunkInputDelay(0);
      drunk_trap_active_ = false;
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

void ScmGameState::EnforcePickupLayout() {
  if (pickup_targets_.empty()) return;
  std::vector<PickupPoolEntry> entries;
  for (int index = 0; index < kPickupPoolSize; ++index) {
    const CPickup& pickup = CPickups::aPickUps[index];
    // Type zero is a dead slot (never created, or script-removed); it stays
    // dead, so a mission's remove_pickup is never resurrected.
    if (pickup.bPickupType == 0) continue;
    entries.push_back({pickup.vecPos.x, pickup.vecPos.y, pickup.vecPos.z,
                       static_cast<int>(pickup.bPickupType),
                       static_cast<int>(pickup.nModelId), index});
  }
  const PickupLayoutPlan plan = PlanPickupLayout(pickup_targets_, entries);
  // A layout slot the pool never offered stays vanilla by design; one
  // diagnostic per config delivery records how many (a reconnect re-arms
  // it), on a frame late enough that the init mission has finished placing
  // the ambient pickups. A report landing inside a mission's brief
  // remove-and-recreate window may count that slot once; log noise only.
  ++pickup_enforce_frames_;
  if (pickup_enforce_frames_ == kPickupUnmatchedLogFrame &&
      plan.unmatched_targets > 0 && logger_) {
    logger_("pickup layout: " + std::to_string(plan.unmatched_targets) + " of " +
            std::to_string(pickup_targets_.size()) +
            " slots not found in the pool, left vanilla");
  }
  for (const PickupRewrite& rewrite : plan.rewrites) {
    CPickup& pickup = CPickups::aPickUps[rewrite.pool_index];
    pickup.nModelId = static_cast<short>(rewrite.model);
    pickup.dwPickupQuantity = static_cast<unsigned int>(rewrite.quantity);
    // The byte after bRemoved holds the ammo-collected bit; cleared so a
    // relocated weapon grants its ammo instead of reading as already drained.
    pickup.bEffects = false;
    // Drop the stale visible objects the way the game's own remove does; the
    // pickup update recreates them from the new model on the next frame. A
    // collected pickup awaiting respawn has no objects and respawns as the
    // new model on its own timer.
    if (pickup.pObject != nullptr) {
      CObject* object = static_cast<CObject*>(pickup.pObject);
      CWorld::Remove(object);
      delete object;
      pickup.pObject = nullptr;
    }
    if (pickup.pExtraObject != nullptr) {
      CObject* extra_object = static_cast<CObject*>(pickup.pExtraObject);
      CWorld::Remove(extra_object);
      delete extra_object;
      pickup.pExtraObject = nullptr;
    }
  }
}

void ScmGameState::DetectCollectedPackages() {
  if (package_locations_.empty()) return;
  // World positions of every collectable pickup still present in the pool.
  std::vector<WorldPoint> present;
  for (int index = 0; index < kPickupPoolSize; ++index) {
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
    // The minimap forcing memory belongs to the game that set it; the next
    // game re-derives it from its own globals on the first frame.
    minimap_forcing_hidden_ = false;
    // Ability toast pacing and the status-key edge belong to the game too;
    // the locks themselves re-derive from the globals every frame.
    ability_toast_shown_.fill(false);
    ability_toast_last_ms_.fill(0);
    ability_status_key_was_down_ = false;
    // The model table belongs to the game that loaded it.
    kill_frenzy_model_ = -1;
    kill_frenzy_lookup_logged_ = false;
    world_was_loaded_ = false;
    // The unmatched-slot diagnostic counts frames per game, so a fresh game
    // gets its own creation window and its own single report.
    pickup_enforce_frames_ = 0;
    return;
  }

  // No item applies until the player is controllable. Before control a script
  // still owns the world (the new-game intro, a cutscene), so a side effect an
  // SCM watcher fires off a fresh unlock global (an area gate opening) would be
  // silently undone by it, and its once-guard would keep it from re-firing.
  // Pending items simply wait: the dirty flag holds until the first
  // controllable frame.
  const bool controllable = PlayerIsControllable();

  // A world that has just come up (a new game, or a save loaded mid-session)
  // carries whatever unlock globals its save file held, which for an item
  // received after that save was made would take the ability back. Re-derive
  // from the received items on the load edge, the invariant that received
  // state never rests on what a save restored.
  const bool world_loaded = FindPlayerPed() != nullptr;
  if (ShouldReDeriveUnlocks(world_loaded, world_was_loaded_, !items_.empty())) {
    items_dirty_ = true;
    if (logger_) logger_("world loaded, re-deriving unlock globals");
  }
  world_was_loaded_ = world_loaded;

  if (items_dirty_ && controllable) {
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
  // persists in the save. Every effect waits for the same control flag as the
  // unlock globals: planning returns nothing while the player is not
  // controllable, the index holds, and the effects land on a later frame.
  if (FindPlayerPed() != nullptr) {
    const int applied = GetGlobal(kAppliedIndexGlobal);
    const EffectPlan plan =
        PlanEffects(items_, item_effects_, applied, controllable);
    for (const ItemEffect& effect : plan.to_apply) ApplyOneShot(effect);
    if (plan.new_applied_index != applied) {
      SetGlobal(kAppliedIndexGlobal, plan.new_applied_index);
      if (logger_) logger_("applied one-shot effects");
    }
  }

  // Hold or revert the timed traps (sped-up or slowed clock, hostile
  // pedestrians, drunk vision) whether or not new items arrived this frame.
  UpdateTimedTraps();

  // Keep every vehicle radio on an unlocked station while the randomize
  // option is on. Reads the config and unlock globals written above, so a
  // save's own persisted state keeps it working offline too.
  EnforceRadioStations();

  // Keep the radar disc hidden while the minimap shuffle is on and the item
  // has not arrived. Same global-driven shape as the radio, so it also works
  // offline from a save.
  EnforceMinimap();

  // Enforce the ability locks from the lock-flag and unlock globals written
  // above. Same global-driven shape, so a save's own persisted state keeps
  // the locks working offline too.
  EnforceAbilityLocks();

  // Keep the ambient pickup pool on the configured layout. Only when the
  // world is loaded, so the pool holds the placed pickups; runs before the
  // package detection, though the two never touch the same pickup types.
  if (FindPlayerPed() != nullptr) EnforcePickupLayout();

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
