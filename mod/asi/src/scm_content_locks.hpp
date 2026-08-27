// Pure content-lock planning, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// The content_locks option holds classes of content at new game until their
// items arrive, and split_content_locks decides how wide one item's reach is:
// a whole class, one district, or one class in one district. The game never
// learns which: the reserved globals carry one unlock per class per district,
// an item releases every one it covers, and content is held wherever its
// district unlock is still zero. So there is one rule here for all three
// granularities, and it works offline from a save like the ability locks.
//
// A class the seed does not lock arrives with all eleven of its districts
// already released, stamped by the client at config time, which is why holding
// needs no lock flag: at zero locks nothing is ever held. The per-class lock
// flags remain, read only to decide which classes the status page lists.
//
// Enforcement splits by whether the content has an icon. Three classes are
// pickups and are held here, by sinking them out of reach. The other two, the
// unique stunt jumps and the store robberies, have nothing to hold, so the
// main.scm gates them itself and this header only reports their state for the
// status display.
#pragma once

#include <array>
#include <cstddef>
#include <vector>

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
// Only the flags are read, to decide which classes the status page lists. The
// five per-class unlocks above them are written by item_globals and read by
// nothing here: what is held comes from the district block below.
constexpr int kContentLockFlagBase = 9943;

// The district block, matching apworld scm.py: one unlock global per class per
// district, class-major, so a class and a district give a global by formula.
// Eleven districts in apworld district_data.DISTRICTS order; the main.scm's
// per-site gates index the same block the same way.
constexpr int kDistrictCount = 11;
constexpr int kDistrictUnlockBase = 9967;

constexpr int DistrictUnlockGlobal(int content_index, int district) {
  return kDistrictUnlockBase + content_index * kDistrictCount + district;
}

// What a district unlock holds, matching apworld scm.py. Zero is the absence of
// both: still held. The main.scm's gates ask ">= 1", so released and absent both
// let content through, which is right: a district with none of a class has
// nothing to hold. They are apart for the status page alone.
constexpr int kDistrictReleased = 1;
constexpr int kDistrictAbsent = 2;

// True per class per district while that district of that class is held.
using ContentLocks = std::array<bool, kContentCount * kDistrictCount>;

// True per class per district where that class has NO content at all. Thirteen
// of the fifty-five pairs are true in every seed: Leaf Links holds only packages,
// which is four; the robbable stores are absent from five districts besides Leaf
// Links, being Ocean Beach, Starfish Island, Prawn Island, Viceport and Escobar
// International; and one each for the rampages absent from Prawn Island and the
// stunt jumps absent from Viceport, plus the properties absent from Starfish
// Island and Escobar International. Four and five and one and one and two.
//
// Absence rather than presence so that all-false, which is what a default state
// carries, means nothing is known to be absent. Read the other way a state
// nobody filled in would claim the city holds no content whatever, and report
// every class as available.
using ContentAbsence = std::array<bool, kContentCount * kDistrictCount>;

constexpr std::size_t ContentDistrictSlot(int content_index, int district) {
  return static_cast<std::size_t>(content_index) * kDistrictCount + district;
}

inline ContentLocks PlanContentLocks(
    const std::array<int, kContentCount * kDistrictCount>& district_unlocks) {
  ContentLocks held{};
  for (std::size_t slot = 0; slot < held.size(); ++slot) {
    held[slot] = district_unlocks[slot] == 0;
  }
  return held;
}

// Read from the same block, so the two can never disagree about a pair.
//
// Only the one value means absent. An older seed's stamp wrote released for both
// kinds, so it reads as nothing absent and the page tells the player about
// districts holding nothing, exactly as it did before this existed: the old
// behaviour rather than a wrong one, and the stamp is rewritten on every load,
// so it corrects itself.
inline ContentAbsence PlanContentAbsence(
    const std::array<int, kContentCount * kDistrictCount>& district_unlocks) {
  ContentAbsence absent{};
  for (std::size_t slot = 0; slot < absent.size(); ++slot) {
    absent[slot] = district_unlocks[slot] == kDistrictAbsent;
  }
  return absent;
}

inline bool ContentHeldAnywhere(const ContentLocks& held, int content_index) {
  for (int district = 0; district < kDistrictCount; ++district) {
    if (held[ContentDistrictSlot(content_index, district)]) return true;
  }
  return false;
}

inline int ContentDistrictsHeld(const ContentLocks& held, int content_index) {
  int count = 0;
  for (int district = 0; district < kDistrictCount; ++district) {
    if (held[ContentDistrictSlot(content_index, district)]) ++count;
  }
  return count;
}

// How many districts hold any of this class, which is what a held count has to
// be read against.
inline int ContentDistrictsPresent(const ContentAbsence& absent,
                                   int content_index) {
  int count = 0;
  for (int district = 0; district < kDistrictCount; ++district) {
    if (!absent[ContentDistrictSlot(content_index, district)]) ++count;
  }
  return count;
}

inline bool AnyContentHeld(const ContentLocks& held) {
  for (const bool slot : held) {
    if (slot) return true;
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
// A pickup whose position matched no district entry. Its class is still held or
// released as a whole, which is the safe reading: a pickup the seed never
// described is held while any district of its class is, so a table that misses
// an entry hides that pickup rather than handing out a check the item has not
// released.
constexpr int kDistrictUnknown = -1;

inline bool HeldForDistrict(const ContentLocks& content, int content_index,
                            int district) {
  if (district == kDistrictUnknown) {
    return ContentHeldAnywhere(content, content_index);
  }
  return content[ContentDistrictSlot(content_index, district)];
}

inline bool ShouldHoldPickup(HeldPickupClass held_class, int district,
                             bool vehicle_rampage, const AbilityLocks& ability,
                             const ContentLocks& content) {
  switch (held_class) {
    case HeldPickupClass::kPackage:
      return HeldForDistrict(content, kContentHiddenPackages, district);
    case HeldPickupClass::kRampage:
      return HeldForDistrict(content, kContentRampages, district) ||
             (ability[kAbilityWeaponEquip] && !vehicle_rampage);
    case HeldPickupClass::kProperty:
      return HeldForDistrict(content, kContentPropertyPurchases, district);
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

// What the pickup walk does with one pool entry: leave it where it is, sink it
// out of reach while its class is held, or bring it back.
enum class PickupHoldAction { kLeaveAlone, kLower, kRaise };

// `removed` is the game's own flag for a pickup it has taken away, collected
// and awaiting respawn or retired. Such a pickup is neither visible nor
// collectable, so it needs no holding, and the walk re-evaluates it once the
// game puts it back.
// Which district a pickup is in, from the table the seed sent: entries are
// positions, and a held pickup keeps its x and y, so a sunk one still matches.
// Linear because the table is 150 entries and the pool walk asks once per
// entry per frame; a quantized lookup would be faster and is not needed yet.
struct PickupDistrict {
  float x = 0.0f;
  float y = 0.0f;
  int content_index = 0;
  int district = 0;
};

inline int DistrictForPickup(const std::vector<PickupDistrict>& table,
                             HeldPickupClass held_class, float x, float y) {
  // Within a metre counts as the same pickup; the nearest two of any class sit
  // far further apart than that, so the tolerance only absorbs the float
  // round-trip through JSON.
  constexpr float kMatchDistanceSquared = 1.0f;
  for (const PickupDistrict& entry : table) {
    const float delta_x = x - entry.x;
    const float delta_y = y - entry.y;
    if (delta_x * delta_x + delta_y * delta_y > kMatchDistanceSquared) continue;
    // The class has to agree too: a property icon and a package can stand close
    // together, and holding one by the other's district would be wrong.
    const bool matches =
        (held_class == HeldPickupClass::kPackage &&
         entry.content_index == kContentHiddenPackages) ||
        (held_class == HeldPickupClass::kRampage &&
         entry.content_index == kContentRampages) ||
        (held_class == HeldPickupClass::kProperty &&
         entry.content_index == kContentPropertyPurchases);
    if (matches) return entry.district;
  }
  return kDistrictUnknown;
}

inline PickupHoldAction PlanPickupHold(bool should_hold, float z, bool removed) {
  if (removed) return PickupHoldAction::kLeaveAlone;
  const bool sunk = IsPickupSunk(z);
  if (should_hold && !sunk) return PickupHoldAction::kLower;
  if (!should_hold && sunk) return PickupHoldAction::kRaise;
  return PickupHoldAction::kLeaveAlone;
}

}  // namespace gtavc
