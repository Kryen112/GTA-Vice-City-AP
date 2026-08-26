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
// Lives here beside the model, rather than with the patches, so the planner
// and the console self-test both read the one value.
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

// A pool entry to rewrite to the layout's model and ammo.
struct PickupRewrite {
  int pool_index = 0;
  int model = 0;
  int quantity = 0;
};

// One stand the purchase path must price from a type of its own rather than from
// the model showing on it, and the type to answer with.
struct PickupPriceOverride {
  int pool_index = 0;
  int weapon_type = 0;
};

// One frame of layout planning: the rewrites to apply, the price overrides they
// imply, plus how many layout slots found no pool entry at all (left vanilla;
// the caller logs them once).
struct PickupLayoutPlan {
  std::vector<PickupRewrite> rewrites;
  int unmatched_targets = 0;
  // Here rather than in a pass of its own because finding which pool entry
  // stands at a target is the expensive half and the rewrites already do it. A
  // stand appears only while its check is pending: once taken, the real model is
  // back on it and the game's own price for that model is the stand's price
  // again.
  std::vector<PickupPriceOverride> price_overrides;
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
  // Within a quarter unit (Euclidean) counts as the same slot, mirrored from
  // data.PICKUP_MATCH_TOLERANCE, which the mirror checker compares against this.
  //
  // Two measured bounds hold it there, both taken over the decompile by
  // dump_pickups.py rather than written down: the closest pair of slots is 3.67
  // units apart, and the closest same-type pickup that NO table of ours owns is
  // 0.94 units from a slot. The second is the tight one and it used to be 1.91,
  // which is why the tolerance used to be 1.0: the four pickups Rub Out leaves
  // in the estate courtyard brought it down, because the body armour among them
  // has the finale's Tec-9 less than a unit away and both are the street type.
  // The finale holds the whole layout off the pool while it runs, so that pair
  // never actually meets; the tolerance stays under it anyway, so the matcher
  // does not depend on that.
  //
  // A quarter unit is far more than the positions need. They round-trip from the
  // decompile through JSON as decimals and land on the same float the script
  // literal compiled to, so what is being absorbed is the last bits of a float
  // and nothing else.
  constexpr double kMatchDistanceSquared = 0.0625;
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
    // The NEAREST entry within the tolerance, not the first one found. The
    // bounds above mean only the slot's own pickup can be inside a quarter unit
    // of it, so the two choices agree on every table this ships with; taking the
    // nearest is what makes that a property of the positions rather than of the
    // order the pool happens to be walked in.
    const PickupPoolEntry* match = nullptr;
    double match_distance_squared = 0.0;
    for (const PickupPoolEntry& entry : pool_entries) {
      if (entry.pickup_type != target.pickup_type) continue;
      const double delta_x = entry.x - target.x;
      const double delta_y = entry.y - target.y;
      const double delta_z = entry.z - target.z;
      const double distance_squared =
          delta_x * delta_x + delta_y * delta_y + delta_z * delta_z;
      if (distance_squared > kMatchDistanceSquared) continue;
      if (match != nullptr && distance_squared >= match_distance_squared) continue;
      match = &entry;
      match_distance_squared = distance_squared;
    }
    if (match == nullptr) {
      ++plan.unmatched_targets;
      continue;
    }
    if (match->model != wanted_model) {
      plan.rewrites.push_back(
          {match->pool_index, wanted_model, wanted_quantity});
    }
    if (pending && target.price_weapon_type != 0) {
      plan.price_overrides.push_back(
          {match->pool_index, target.price_weapon_type});
    }
  }
  return plan;
}

}  // namespace gtavc
