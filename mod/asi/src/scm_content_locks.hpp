// Pure content-lock planning, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// The content_locks option holds whole classes of content at new game until
// their items arrive. The reserved globals carry one lock flag and one unlock
// count per content item (apworld scm.py order); a class is held while its
// flag is set and its unlock is zero, so the enforcement works offline from a
// save like the ability locks.
//
// Enforcement splits by whether the content has an icon. Three classes are
// pickups and are held here, by sinking them out of reach. The other two, the
// unique stunt jumps and the store robberies, have nothing to hold, so the
// main.scm gates them itself and this header only reports their state for the
// status display.
#pragma once

#include <array>
#include <cstddef>

#include "scm_ability_locks.hpp"

namespace gtavc {

// The five content items in the reserved-global order, matching apworld
// scm.py CONTENT_KEYS (data.CONTENT_ITEMS). Never reorders: the main.scm
// hard-codes the stunt jump and store offsets into this same block.
enum ContentIndex {
  kContentHiddenPackages = 0,
  kContentRampages,
  kContentStuntJumps,
  kContentPropertyPurchases,
  kContentRobbableStores,
  kContentCount,
};

// The content contract, matching apworld scm.py: one lock-flag global per
// item from the flag base, then one unlock global per item from the unlock
// base, both in ContentIndex order.
constexpr int kContentLockFlagBase = 9437;
constexpr int kContentUnlockBase = 9442;

// True per class while it is held right now.
using ContentLocks = std::array<bool, kContentCount>;

inline ContentLocks PlanContentLocks(
    const std::array<int, kContentCount>& lock_flags,
    const std::array<int, kContentCount>& unlocks) {
  ContentLocks held{};
  for (int index = 0; index < kContentCount; ++index) {
    held[index] = lock_flags[index] != 0 && unlocks[index] == 0;
  }
  return held;
}

inline bool AnyContentHeld(const ContentLocks& held) {
  for (int index = 0; index < kContentCount; ++index) {
    if (held[index]) return true;
  }
  return false;
}

// The pickup types the held classes use, matching plugin-sdk's ePickupType.
// A package is the game's own collectable type; a property icon is either of
// the two property types, since the eight businesses are created locked and
// flipped to for-sale when Shakedown passes and both states must hold.
constexpr int kPickupTypeCollectable = 6;
constexpr int kPickupTypePropertyLocked = 17;
constexpr int kPickupTypePropertyForSale = 18;

// Which held class a pool entry belongs to. Rampage icons are the one class
// identified by model rather than type, because the SCM creates them from the
// kill-frenzy skull; the caller resolves that id by name and passes it here.
enum class HeldPickupClass { kNone, kPackage, kRampage, kProperty };
constexpr std::size_t kHeldPickupClassCount =
    static_cast<std::size_t>(HeldPickupClass::kProperty) + 1;

inline HeldPickupClass ClassifyHeldPickup(int pickup_type, int model,
                                          int kill_frenzy_model) {
  if (kill_frenzy_model >= 0 && model == kill_frenzy_model) {
    return HeldPickupClass::kRampage;
  }
  if (pickup_type == kPickupTypeCollectable) return HeldPickupClass::kPackage;
  if (pickup_type == kPickupTypePropertyLocked ||
      pickup_type == kPickupTypePropertyForSale) {
    return HeldPickupClass::kProperty;
  }
  return HeldPickupClass::kNone;
}

// Whether this entry is held right now, unioning both lock families: either
// lock alone still stops the content, so neither supersedes the other.
//
// A rampage icon answers to two locks. The rampages content key holds every
// icon; the weapon_equip ability key holds only the weapon rampages, because
// the two run-them-down rampages hand no weapon and need a land vehicle
// instead, which is a logic term rather than a hold.
inline bool ShouldHoldPickup(HeldPickupClass held_class, bool vehicle_rampage,
                             const AbilityLocks& ability,
                             const ContentLocks& content) {
  switch (held_class) {
    case HeldPickupClass::kPackage:
      return content[kContentHiddenPackages];
    case HeldPickupClass::kRampage:
      return content[kContentRampages] ||
             (ability[kAbilityWeaponEquip] && !vehicle_rampage);
    case HeldPickupClass::kProperty:
      return content[kContentPropertyPurchases];
    case HeldPickupClass::kNone:
      return false;
  }
  return false;
}

// A held pickup sinks a fixed offset below the world, far outside collection
// range and out of sight; releasing raises it back. Moving the pickup is the
// whole hold: the game copies the pickup's position into its visible objects
// every update, before it dispatches on type, and the collection test compares
// the object's own position, so a sunk pickup takes its icon down with it and
// cannot be touched. The band makes the state self-describing, so a save made
// while sunk heals on load: world pickups sit well above the band, sunk ones
// well below it.
constexpr float kPickupLowerOffset = 2000.0f;
constexpr float kPickupLoweredBand = -900.0f;

inline bool IsPickupSunk(float z) { return z < kPickupLoweredBand; }

// The true world height of an entry that may be sunk. The package detector
// reads positions to decide which package was collected, and a sunk package
// must still read as present at its own coordinate: matching it where it
// really sits would make every held package look collected at once.
inline float UnsunkHeight(float z) {
  return IsPickupSunk(z) ? z + kPickupLowerOffset : z;
}

// One frame of release reporting. Three classes repopulate the world silently
// when their item lands, so the held-to-released edge is the only place a player
// learns why. Two failure modes have to be avoided at once:
//
// Announce on the first frame a game is observed and every loaded save
// re-announces whatever it already had. Wait for the unlock globals to be
// derived before trusting the state and a player whose FIRST item of the game
// is the content item loses the announcement, because the derive and the first
// observation are then the same frame.
//
// So the first observation is taken as the baseline rather than announced, and
// every edge after it speaks. A save whose globals already hold the item reads
// released at that first observation and stays quiet; a save written before the
// item arrived reads held, then releases, and correctly announces.
struct ContentReleasePlan {
  ContentLocks next_was_held{};
  std::array<bool, kContentCount> announce{};
};

inline ContentReleasePlan PlanContentReleases(
    const ContentLocks& held, const std::array<int, kContentCount>& lock_flags,
    const ContentLocks& was_held, bool baseline_ready) {
  ContentReleasePlan plan;
  plan.next_was_held = held;
  if (!baseline_ready) return plan;
  for (int index = 0; index < kContentCount; ++index) {
    plan.announce[index] =
        lock_flags[index] != 0 && was_held[index] && !held[index];
  }
  return plan;
}

enum class PickupHoldAction { kLeaveAlone, kLower, kRaise };

// `removed` is the game's own flag for a pickup it has taken away, collected
// and awaiting respawn or retired. Such a pickup is neither visible nor
// collectable, so it needs no holding, and the walk re-evaluates it once the
// game puts it back.
inline PickupHoldAction PlanPickupHold(bool should_hold, float z, bool removed) {
  if (removed) return PickupHoldAction::kLeaveAlone;
  const bool sunk = IsPickupSunk(z);
  if (should_hold && !sunk) return PickupHoldAction::kLower;
  if (!should_hold && sunk) return PickupHoldAction::kRaise;
  return PickupHoldAction::kLeaveAlone;
}

}  // namespace gtavc
