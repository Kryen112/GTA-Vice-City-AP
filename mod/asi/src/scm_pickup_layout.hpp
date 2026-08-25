// Pure ambient-pickup layout planning, free of any game headers so the
// console self-test can exercise it without plugin-sdk or the game.
//
// The randomize_pickups option permutes the ambient world pickups: the world
// ships a target layout (position, pickup type, model, ammo per slot) and the
// plan matches each target to the pickup pool by position and type, returning
// a rewrite for every matched entry whose model differs. Matching on the type
// keeps a script-removed slot dead (its type reads none until the script
// recreates it), and rewriting only on a model difference leaves the game's
// own quantity bookkeeping alone: ammo extraction zeroes a weapon pickup's
// quantity in place, and re-stamping it every frame would refill it.
#pragma once

#include <cstddef>
#include <vector>

#include "game_state.hpp"

namespace gtavc {

// One in-use entry of the game's pickup pool, snapshotted for planning.
struct PickupPoolEntry {
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
  int pickup_type = 0;
  int model = 0;
  int pool_index = 0;
};

// The model an ambient slot shows while its AP check is still to be taken.
// 376 is `bonus` in the game's own data/maps/generic.ide, one mesh at the same
// draw distance and flags as the pickup icons beside it, and on a texture
// dictionary of its own like most of them. It is placed nowhere in Vice City by
// either the map or the script, so a rotating one cannot be mistaken for
// anything vanilla.
//
// Placed nowhere is also what is UNVERIFIED about it. No vanilla site creates
// this model, so nothing exercises what the give path does when one is
// collected, and whether it is resident when a slot wants it is measured
// nowhere either. Both are in-game questions the harness cannot reach, and both
// gate the marker going live rather than gating this constant.
//
// A ped model cannot serve here however much better it would look, because
// special characters have no permanent model id: they are streamed by name into
// one of twenty-one shared slots and released when their mission ends.
constexpr int kPickupCheckMarkerModel = 376;

// The weapon type that model prices as while its check is still to be taken. It
// is a price index and nothing else: CostOfWeapon holds a thousand at 12, 13, 14
// and 34, and this names one of them, so a slot wearing the marker costs a
// thousand dollars without a byte of that table being written and without any
// real weapon's price moving.
//
// Any of the four serves, because on this model's path the type never reaches a
// grant. The arm at 0x0043D910 answers the bonus model without granting, and
// 0x00440D76 sends that answer straight to the charge, stepping over the ammo
// table at 0x00687F68 and both weapon grants. What is left reads the type three
// times and prices with it every time: the affordability check at 0x00440D4A,
// the charge at 0x00440DDA, and the stamp at 0x0043D837 that decides what the
// slot displays.
//
// Lives here beside the model, rather than with the patches, so the planner, the
// pool dump and the console self-test all read the one value.
constexpr int kPickupCheckMarkerWeaponType = 12;
constexpr int kPickupCheckMarkerPriceInDollars = 1000;

// What the vehicle-collect gate compares against a pickup's own model. The game
// loads the police bribe model there, so a bribe is the only pickup a driver can
// take; answering with the pickup's own model makes that comparison agree and
// lets the marker join the same branch.
//
// Only while the player is IN a vehicle, which is a narrowing rather than a
// necessity. The branch has an on-foot half too, and it runs the SAME test as
// the ordinary path: the height difference against zero for its sign, its
// magnitude against two, then the flat squared distance against 1.8, measured
// from the same two places. The sphere test against a vehicle lives in the
// vehicle halves of both paths, not the on-foot ones. So answering
// unconditionally would collect on foot identically, and the gate is kept
// because it makes the patch provably additive: out of a car the answer is the
// game's own, so nothing about walking into a pickup can have changed.
//
// It reaches every slot wearing the marker, which is every pending check and not
// only the three beside ramps. A pending in-shop stand becomes drivable, and
// charges from a car what it charges on foot; so does a pending property icon.
// That only ever widens what can be collected, and money gates no logic, so it
// costs solvability nothing.
inline int VehicleCollectComparisonModel(int pickup_model, int bribe_model,
                                         bool player_in_vehicle) {
  if (player_in_vehicle && pickup_model == kPickupCheckMarkerModel) {
    return pickup_model;
  }
  return bribe_model;
}

// The in-shop pickup type, which charges for what it gives. Its cost comes from a
// field of its model info that means a weapon type only for a weapon model, so
// what a slot showing the AP check marker charges is set by the ASI instead, and
// what it shows is set separately: see kPickupChargedPriceCallSite10 and
// kPickupShownPriceCallSite10, which need patching together for the two to
// agree. These slots wear the marker like any other, and the rest of what an
// in-shop check wants, selling in any state and handing over nothing, the game
// already does for that model.
constexpr int kPickupTypeInShop = 1;

// plugin-sdk's eModelInfoType, by value, because this header takes no game
// headers. The caller static_asserts these against the enum.
constexpr int kModelInfoSimple = 1;
constexpr int kModelInfoTime = 3;
constexpr int kModelInfoWeapon = 4;

// Whether a model info's field at 0x30 is the weapon-type union. CSimpleModelInfo
// overlays a weapon type on its LOD parent there, and the time and weapon kinds
// derive from it, so all three carry it. A vehicle or ped means something else at
// that offset, and a bare clump is not that long, so reading it would be past the
// object.
//
// Pure and tested because leaving the weapon kind out of it is a mistake that
// reads as a working dump: every price column simply says nothing, and the models
// it silently drops are the weapons, which is most of what a shop sells.
inline bool ModelInfoCarriesWeaponType(int model_info_kind) {
  return model_info_kind == kModelInfoSimple ||
         model_info_kind == kModelInfoTime ||
         model_info_kind == kModelInfoWeapon;
}

// plugin-sdk's eObjectType for a script created object, by value, because this
// header takes no game headers. The caller ties it to the enum.
constexpr int kObjectTypeMission = 2;

// Whether an object standing in the world is a shop's stock.
//
// Pure and tested because the rule has two ways to be wrong and both are silent.
// Written on the model info kind alone it misses the body armour, which is a
// simple model rather than a weapon one and is sold beside the guns. Written
// without the pickup flag it also dresses the visible object of an ambient weapon
// pickup, which wears a weapon model info too; that is worse than cosmetic,
// because once dressed the layout planner compares the PICKUP's model, sees the
// marker it already wanted, and emits no correction, so the object stays wrong
// until the check is taken.
inline bool IsShopStockObject(int model_info_kind, int model_id,
                              int body_armour_model, int object_type,
                              bool is_pickup_object) {
  if (is_pickup_object) return false;
  if (object_type != kObjectTypeMission) return false;
  return model_info_kind == kModelInfoWeapon || model_id == body_armour_model;
}

// The models an in-shop pickup's price is fixed for without consulting the model
// info, read out of the game at the addresses game_addresses.hpp pins.
//
// A name the game never resolved leaves 0xFFFF in its slot, not -1, and the game
// reads these unsigned, so an unresolved one matches no model at all. The
// defaults say the same thing: they are what an unresolved slot holds, so a
// default-constructed one of these fixes the price of nothing.
struct PickupFixedPriceModels {
  // What the game leaves in a slot whose name never resolved, read unsigned the
  // way the game reads it. What matters is that no pickup can carry it: a model
  // id is a short, so widening one reaches at most 32767, and this is above that
  // whatever value the game happens to leave. A default one of these therefore
  // fixes the price of nothing.
  static constexpr int kUnresolved = 0xFFFF;
  static_assert(kUnresolved > 32767,
                "an unresolved slot must be outside the range a short model id "
                "can reach, or it would match a real pickup");
  int body_armour = kUnresolved;
  int health = kUnresolved;
  int adrenaline = kUnresolved;
  int body_armour_weapon_type = 0;
  int health_weapon_type = 0;
  int adrenaline_weapon_type = 0;
};

// The weapon type an in-shop pickup's price comes from, in the order the purchase
// path resolves it: three models take a fixed type, a model id of -1 takes zero,
// and everything else takes the field of its model info, which is where the ASI's
// own patch answers for the AP check marker.
//
// Pure so the order is testable, because the order is the whole of it: the fixed
// models are compared before anything reads a model info, so resolving them the
// other way round would price a stand from a field that means nothing for it.
inline int PickupWeaponTypeForPrice(int model_id,
                                    const PickupFixedPriceModels& fixed,
                                    int model_info_weapon_type,
                                    int marker_weapon_type) {
  if (model_id == fixed.body_armour) return fixed.body_armour_weapon_type;
  if (model_id == fixed.health) return fixed.health_weapon_type;
  if (model_id == fixed.adrenaline) return fixed.adrenaline_weapon_type;
  // The path sends only -1 through a table whose one entry zeroes the type, and
  // tries it after the three, so this does too. Any other negative is answered
  // the same way rather than sent on to index a model table with it.
  if (model_id < 0) return 0;
  if (model_id == kPickupCheckMarkerModel) return marker_weapon_type;
  return model_info_weapon_type;
}

// A pool entry to rewrite to the layout's model and ammo.
struct PickupRewrite {
  int pool_index = 0;
  int model = 0;
  int quantity = 0;
};

// One frame of layout planning: the rewrites to apply, plus how many layout
// slots found no pool entry at all (left vanilla; the caller logs them once).
struct PickupLayoutPlan {
  std::vector<PickupRewrite> rewrites;
  int unmatched_targets = 0;
};

// check_pending carries one flag per target, true while that slot's AP check is
// still to be taken. Empty means no slot is a check, which is every seed with
// the class off and the whole of vanilla, so the default keeps the shuffle-only
// callers unchanged. A slot whose check is pending shows the marker instead of
// whatever the layout would give it, and reverts to the layout the frame after
// the check is taken, since the flag is what the caller re-derives per frame.
inline PickupLayoutPlan PlanPickupLayout(
    const std::vector<PickupTarget>& targets,
    const std::vector<PickupPoolEntry>& pool_entries,
    const std::vector<bool>& check_pending = {}) {
  // Within one unit (Euclidean) counts as the same slot. Two bounds keep a
  // match unambiguous: the extractor refuses a table whose slots sit closer
  // than 1.5 units (the nearest vanilla pair is 4.49 apart), and the nearest
  // same-type pickup OUTSIDE the table is 1.91 units from a slot (a mission
  // script places a body armor beside the Prawn Island heart), so the
  // tolerance must stay below that; 1.0 only absorbs float round-tripping.
  constexpr double kMatchDistanceSquared = 1.0;
  PickupLayoutPlan plan;
  for (std::size_t index = 0; index < targets.size(); ++index) {
    const PickupTarget& target = targets[index];
    // The marker carries no ammo: it is not a weapon, and stamping a quantity
    // on it would be a number the game keeps for something it is not holding.
    // Taking the check puts the model back to the layout's, which re-stamps the
    // ammo with it, because the rewrite fires on the model differing.
    const bool pending = index < check_pending.size() && check_pending[index];
    const int wanted_model =
        pending ? kPickupCheckMarkerModel : target.model;
    const int wanted_quantity = pending ? 0 : target.quantity;
    bool matched = false;
    for (const PickupPoolEntry& entry : pool_entries) {
      if (entry.pickup_type != target.pickup_type) continue;
      const double delta_x = entry.x - target.x;
      const double delta_y = entry.y - target.y;
      const double delta_z = entry.z - target.z;
      const double distance_squared =
          delta_x * delta_x + delta_y * delta_y + delta_z * delta_z;
      if (distance_squared > kMatchDistanceSquared) continue;
      matched = true;
      if (entry.model != wanted_model) {
        plan.rewrites.push_back(
            {entry.pool_index, wanted_model, wanted_quantity});
      }
      break;
    }
    if (!matched) ++plan.unmatched_targets;
  }
  return plan;
}

}  // namespace gtavc
