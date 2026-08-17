// Pure ability-lock planning, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// The ability_locks option locks abilities at new game until their items
// arrive. The reserved globals carry one lock flag and one unlock count per
// ability item (apworld scm.py order); an ability is locked while its flag is
// set and its unlock is zero, so the enforcement works offline from a save
// like the minimap.
//
// The decisions planned here are the input masks (which never apply while a
// script owns the player), which vehicle class a locked entry attempt
// belongs to, which rampages the weapon lock covers, when a blocked attempt
// may toast, and when the unlock globals need re-deriving. The wallet is
// deliberately absent: money is state rather than input, so the frame handler
// pins the balance itself.
#pragma once

#include <array>

namespace gtavc {

// The eight ability items in the reserved-global order, matching apworld
// scm.py ABILITY_KEYS (data.ABILITY_ITEMS). Never reorders.
enum AbilityIndex {
  kAbilitySprint = 0,
  kAbilityJump,
  kAbilityCrouch,
  kAbilityLandVehicles,
  kAbilitySeaVehicles,
  kAbilityAirVehicles,
  kAbilityWeaponEquip,
  kAbilityWallet,
  kAbilityCount,
};

// The ability contract, matching apworld scm.py: one lock-flag global per
// item from the flag base, then one unlock global per item from the unlock
// base, both in AbilityIndex order.
constexpr int kAbilityLockFlagBase = 9421;
constexpr int kAbilityUnlockBase = 9429;

// True per ability while it is locked right now.
using AbilityLocks = std::array<bool, kAbilityCount>;

inline AbilityLocks PlanAbilityLocks(
    const std::array<int, kAbilityCount>& lock_flags,
    const std::array<int, kAbilityCount>& unlocks) {
  AbilityLocks locked{};
  for (int index = 0; index < kAbilityCount; ++index) {
    locked[index] = lock_flags[index] != 0 && unlocks[index] == 0;
  }
  return locked;
}

inline bool AnyAbilityLocked(const AbilityLocks& locked) {
  for (int index = 0; index < kAbilityCount; ++index) {
    if (locked[index]) return true;
  }
  return false;
}

// The masks and holds one frame of input enforcement applies. The masks are
// state-aware because the game reads the same pad fields for different
// actions on foot and in a vehicle, verified against its own accessors: the
// two second shoulders are weapon cycling on foot but the look-behind pair
// in a car (GetLookBehindForCar reads both), and the left shock button is
// crouch on foot but the horn in a car (GetHorn reads it). Masking in a
// vehicle would therefore take away driving controls that are not the locked
// ability, so nothing masks there. Drive-by needs no mask of its own: the
// weapon hold keeps the current weapon on the bare fists, and fists cannot
// fire from a vehicle, so the fire button stays free for the things that are
// not Tommy's weapons (a Hunter's cannon, the Demolition Man bomb trigger).
// The weapon hold also undoes the engine's auto-equip when an unarmed player
// walks over a weapon pickup. The wallet is not input, so it is not here; the
// frame handler pins the balance directly.
struct AbilityInputPlan {
  bool mask_sprint = false;
  bool mask_jump = false;
  bool mask_crouch = false;
  bool mask_weapon_cycle = false;
  bool force_unarmed = false;
};

inline AbilityInputPlan PlanAbilityInputs(const AbilityLocks& locked,
                                          bool on_foot, bool controllable,
                                          bool remote_control) {
  AbilityInputPlan plan;
  // Input constrains the player's hands only; a script that owns the world
  // (cutscene, mission screen) keeps full control of the ped.
  if (!controllable) return plan;
  // While the pad drives a remote-control vehicle the player ped stands
  // still, so it reads as on foot while the same buttons are the RC
  // throttle. The locks are about Tommy's body, so they all stand down: the
  // RC side events and the Demolition Man bomb run untouched.
  if (remote_control) return plan;
  plan.force_unarmed = locked[kAbilityWeaponEquip];
  if (on_foot) {
    plan.mask_sprint = locked[kAbilitySprint];
    plan.mask_jump = locked[kAbilityJump];
    plan.mask_crouch = locked[kAbilityCrouch];
    plan.mask_weapon_cycle = locked[kAbilityWeaponEquip];
  }
  return plan;
}

// Vehicle appearance ids, matching CVehicle::GetVehicleAppearance: the
// game's own looks-like classification, which is what entry should key on
// (the engine types helicopters as automobiles and the Skimmer as a boat,
// but their appearances read heli and plane).
enum VehicleAppearance {
  kAppearanceAutomobile = 1,
  kAppearanceBike,
  kAppearanceHeli,
  kAppearanceBoat,
  kAppearancePlane,
};

// The ability that blocks entering a vehicle of this appearance right now,
// or kAbilityCount when entry is allowed.
inline int VehicleEntryLockIndex(const AbilityLocks& locked, int appearance) {
  switch (appearance) {
    case kAppearanceAutomobile:
    case kAppearanceBike:
      return locked[kAbilityLandVehicles] ? kAbilityLandVehicles : kAbilityCount;
    case kAppearanceBoat:
      return locked[kAbilitySeaVehicles] ? kAbilitySeaVehicles : kAbilityCount;
    case kAppearanceHeli:
    case kAppearancePlane:
      return locked[kAbilityAirVehicles] ? kAbilityAirVehicles : kAbilityCount;
    default:
      return kAbilityCount;
  }
}

// The two run-them-down rampages, the RAMPAGE controller blocks whose $1518
// carries no weapon, keyed by their kill-frenzy pickup coordinates (the
// apworld splits the same pair by index). Their icons stay collectible under
// the weapon lock; every other kill-frenzy icon is held out of reach until
// Weapon Equip arrives.
constexpr float kVehicleRampagePickups[][2] = {
    {-679.66f, -419.712f},
    {468.656f, -1608.79f},
};

inline bool IsVehicleRampagePickup(float x, float y) {
  // Within one unit counts as the same icon; the rampage spots sit hundreds
  // of units apart, so the tolerance only absorbs float round-tripping.
  constexpr float kMatchDistanceSquared = 1.0f;
  for (const auto& coords : kVehicleRampagePickups) {
    const float delta_x = x - coords[0];
    const float delta_y = y - coords[1];
    if (delta_x * delta_x + delta_y * delta_y <= kMatchDistanceSquared) return true;
  }
  return false;
}

// Holding an icon out of reach lives in scm_content_locks.hpp, which unions
// this weapon-rampage split with the rampages content key: either lock alone
// still stops the icon.

// Whether a world that has just come up should re-derive the unlock globals
// from the received items. A save carries whatever unlock globals it was
// written with, so an item received after that save was made would otherwise
// stay missing until a reconnect, taking an ability (or an area, a station,
// the minimap) back. Only the not-loaded to loaded edge triggers it, and only
// with items in hand: re-deriving from an empty list would write every unlock
// global to zero, wiping the state the save legitimately holds while the
// first delivery is still in flight.
inline bool ShouldReDeriveUnlocks(bool world_loaded, bool world_was_loaded,
                                  bool has_items) {
  return world_loaded && !world_was_loaded && has_items;
}

// A blocked attempt toasts once, then holds its tongue for the cooldown, so
// a held sprint key or a mashed enter key cannot flood the message queue.
constexpr unsigned int kAbilityToastCooldownMs = 10000;

inline bool ShouldShowAbilityToast(unsigned int now_ms, bool ever_shown,
                                   unsigned int last_shown_ms) {
  if (!ever_shown) return true;
  // Signed difference so the comparison survives the clock wrapping.
  return static_cast<int>(now_ms - last_shown_ms) >=
         static_cast<int>(kAbilityToastCooldownMs);
}

}  // namespace gtavc
