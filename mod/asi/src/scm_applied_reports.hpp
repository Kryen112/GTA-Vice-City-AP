// Pure landing detection, free of any game headers so the console self-test can
// exercise it without plugin-sdk or the game: which received items the game has
// now actually acted on, so the client can toast each one at the moment it lands
// rather than at the moment the server announced it.
//
// The toast a player reads is a record of a GRANT, not of a packet. Grants leave
// at the rate scm_grant_pacing.hpp allows, minutes apart on a slot holding
// everything at once, so a row posted on arrival claims an ability the player
// does not have yet. One report per landing is what keeps the two honest, and it
// needs no pacing of its own: a grant is at most one per frame and one per
// interval, and PlanUnlocks sweeps in the same received order this reports in, so
// the rows follow the grants one for one.
//
// A grant releasing more than one row at a time is bounded and expected, not the
// reordering this used to have: several copies of one item ride a single raise to
// their shared count, and a content item's row falls on whichever of its district
// globals the sweep reaches last. Those are usually one consecutive run, since
// they share an arrival key and break ties on global index, but a district global
// an earlier split item also releases keeps the EARLIER key, so a whole-class
// item's fan-out can straddle the sweep and land on the wrap. What that costs is a
// run as long as an item's fan-out, never a run as long as the release.
//
// WHAT LANDED MEANS, per item, and it is an AND across everything the item does:
//   an unlock global      the game holds at or above its target
//   a content item        every district global it releases holds its target
//   a one-shot effect     the saved applied-index has passed its position
//   none of those         landed the moment it arrived, since nothing will
//                         happen for it to wait on
//
// REPORTS GO IN RECEIVED ORDER, which is Archipelago's order, so the stack agrees
// with the client window and every tracker. The walk stops at the first item that
// has not landed rather than skipping it, so a report never precedes one that
// arrived before it.
//
// That stop is a head-of-line hold, and what keeps it short is that PlanUnlocks
// sweeps in the SAME order: a global an early item needs is always swept before
// one only a later item needs, so the item the walk is waiting on is among the
// next few grants. It was not always so, and the cost was measured: sweeping by
// global index instead showed the player nothing for eleven seconds on a
// twenty-item release and then all twenty at once, because the item that arrived
// first was granted last.
//
// TWO WAYS THE HOLD CAN STILL BITE, and only the first is answered here.
//
// A global the config stamp owns is read as landed, because PlanUnlock refuses to
// raise one in either direction, so an item sitting on one would wait forever.
// That is the routine case, since the stamped set overlaps the district globals
// in every seed.
//
// A global something else in the GAME rewrites every frame is not answered, and
// cannot be from here: the value is real, the target is real, and nothing
// distinguishes it from a raise that has not happened yet. The walk would stop at
// its item for the rest of the session.
//
// PlanUnlocks' rotation exists for exactly that global, and what it bounds is
// narrower than it looks: while OTHER raises are pending the stuck one costs one
// slot per pass, but once it is the only raise left every pass is one key long, so
// the wrap hands it the slot every interval. RaiseYieldsToEffect then withholds
// one-shot effects whose received index is ABOVE that global's key indefinitely
// rather than delaying them, since the yield only reaches effects that arrived
// earlier. That predates this and the yield narrows it; it is recorded here
// because this is the file that decides what a landing means and the bound is not
// what a reader would assume.
#pragma once

#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <utility>
#include <vector>

#include "game_state.hpp"
#include "scm_grant_pacing.hpp"

namespace gtavc {

// The received indices to tell the client about, in received order.
struct AppliedReportPlan {
  std::vector<std::int64_t> to_report;
};

// Whether an item that has not landed holds the ones behind it.
//
// The REPORT pass holds, because a row must never precede one for an item that
// arrived earlier. The BASELINE pass does not: it announces nothing at all, so
// order cannot matter to it, and stopping early would leave a landed item
// unmarked for a pass that never comes again, which announces it on the next
// load. That is not hypothetical whenever the landed set is not a received-order
// prefix, which a script clearing one low global or a save taken mid-delivery is
// enough to cause.
enum class AppliedReportOrder {
  kHoldForArrival,
  kEverythingLanded,
};

// Whether one unlock global holds what the item list asks of it.
//
// `observed` is this frame's own read, and this SEARCHES it rather than scanning
// it, because an item releasing eleven districts asks eleven times and the list
// runs to over a hundred globals. So it must be in ascending GLOBAL order with no
// index twice.
//
// PlanUnlocks no longer needs that order, only the distinctness, since it selects
// by comparing keys. Sorting the vector by arrival key for its benefit would
// therefore look harmless and would break this silently: the search would miss a
// global, read its item as landed early, and a baseline pass would mark that item
// as told and never give it its row. The caller builds the vector from a
// std::map keyed by global index, which is what keeps the order without anyone
// having to sort it.
inline bool UnlockGlobalHasLanded(const std::vector<UnlockObservation>& observed,
                                  int global_index) {
  const auto entry = std::lower_bound(
      observed.begin(), observed.end(), global_index,
      [](const UnlockObservation& candidate, int index) {
        return candidate.global_index < index;
      });
  // A global no observation covers is a global nothing raises, so an item
  // touching it waits on nothing.
  if (entry == observed.end() || entry->global_index != global_index) return true;
  // A stamped global belongs to the config stamp in both directions. PlanUnlock
  // returns kNone for one, so no grant will ever raise it, and the stamp rewrites
  // it later in the same frame at a value never below the target. Reading it as
  // landed is what keeps an item on a stamped global from holding every later
  // report behind it forever.
  if (entry->stamped) return true;
  return entry->current >= entry->target;
}

// Which received items have landed and have not been reported yet.
//
// `applied_effect_index` is the saved index the one-shot effects count against,
// so an effect item has landed once the index has passed its position among the
// effect items in received order. `already_reported` is what the caller has
// already told the client about, or silently baselined, and nothing in it is
// reported twice.
inline AppliedReportPlan PlanAppliedReports(
    const std::vector<std::pair<std::int64_t, std::int64_t>>& items,
    const std::map<std::int64_t, int>& item_globals,
    const std::map<std::int64_t, std::vector<int>>& content_district_globals,
    const std::map<std::int64_t, ItemEffect>& item_effects,
    const std::vector<UnlockObservation>& observed, int applied_effect_index,
    const std::set<std::int64_t>& already_reported, AppliedReportOrder order) {
  AppliedReportPlan plan;
  int effect_position = 0;
  for (const auto& [received_index, item_id] : items) {
    bool landed = true;
    // Every map the item appears in is asked, and the answers are ANDed rather
    // than taken from the first one that matches: a content item counts into its
    // class global AND releases eleven districts, and it has landed only when the
    // whole of what it does has happened.
    const auto effect = item_effects.find(item_id);
    if (effect != item_effects.end()) {
      if (effect_position >= applied_effect_index) landed = false;
      // Counted for every effect item whether or not this one is reportable, since
      // the position is what the saved index means.
      ++effect_position;
    }
    // Settled long ago: walk past it before the work that decides whether it
    // landed, since a slot with hundreds of items pays this every frame. After
    // the effect count above, which every effect item owes whatever its state.
    if (already_reported.count(received_index) != 0) continue;
    const auto unlock = item_globals.find(item_id);
    if (unlock != item_globals.end() &&
        !UnlockGlobalHasLanded(observed, unlock->second)) {
      landed = false;
    }
    const auto districts = content_district_globals.find(item_id);
    if (districts != content_district_globals.end()) {
      for (const int global_index : districts->second) {
        if (!UnlockGlobalHasLanded(observed, global_index)) landed = false;
      }
    }
    // Received order is the order the client window and every tracker show, so a
    // pending item holds the ones behind it rather than letting them overtake it.
    // A baseline pass announces nothing, so it marks the rest anyway.
    if (!landed) {
      if (order == AppliedReportOrder::kHoldForArrival) break;
      continue;
    }
    plan.to_report.push_back(received_index);
  }
  return plan;
}

}  // namespace gtavc
