// The status panel's text, free of any game headers so the console self-test can
// exercise it without plugin-sdk or the game.
//
// The panel is what the pause menu's ARCHIPELAGO page shows: every fact about
// this seed a player cannot read anywhere else in game. It replaces the status
// key, whose one game-text message had to fit a length bound and left the screen
// on a timer. Here nothing is truncated and nothing expires, so the lists are
// one row per thing rather than comma-joined lines.
//
// Only what this seed configured appears. An unselected lock key is fully
// vanilla and listing it would mislead, and an option that is off has no state
// worth a row.
#pragma once

#include <array>
#include <cstddef>
#include <utility>
#include <string>
#include <vector>

#include "scm_ability_locks.hpp"
#include "scm_content_locks.hpp"
#include "scm_crossings.hpp"
#include "scm_radio.hpp"
#include "scm_toasts.hpp"

namespace gtavc {

// Player-facing names for the abilities, AbilityIndex order. Shared with the
// blocked-attempt toast's own text, which is a sentence per ability rather than
// a name and so lives beside that toast.
constexpr const char* kAbilityNames[kAbilityCount] = {
    "Sprint", "Jump", "Crouch", "Land Vehicles", "Sea Vehicles",
    "Air Vehicles", "Weapon Equip", "Wallet",
};
// Player-facing names for the content classes, ContentIndex order. Plural so
// the release toast reads as a sentence: "Hidden Packages are now available."
constexpr const char* kContentNames[kContentCount] = {
    "Hidden Packages", "Rampages", "Stunt Jumps", "Property Purchases",
    "Robbable Stores",
};
// Player-facing district names, in the apworld district_data.DISTRICTS order the
// unlock block indexes by. The page lists the districts a class is still held in,
// so a wrong name here misnames a place rather than holding the wrong content.
constexpr const char* kDistrictNames[kDistrictCount] = {
    "Ocean Beach", "Washington Beach", "Vice Point", "Starfish Island",
    "Prawn Island", "Leaf Links", "Downtown", "Little Haiti", "Little Havana",
    "Viceport", "Escobar International",
};
// The emergency and side-job activities the seed turns into checks, with how many
// levels each one has, matching data.EMERGENCY_LEVELS: the three emergency
// vehicles count twelve levels, and the taxi and the pizza boy count ten, one per
// ten fares or deliveries.
constexpr int kEmergencyLevels = 12;
constexpr int kSideJobLevels = 10;
// The taxi's own cadence, and only the taxi's: its checks fire on career fares
// at every tenth. The pizza boy has no such number, see the state fields below.
constexpr int kTaxiFaresPerLevel = 10;

// Player-facing names for the radio stations, in the station-byte order the
// unlock globals follow. The MP3 player and the police scanner are not stations
// here, so the list is the nine music stations.
constexpr const char* kRadioStationNames[kRadioStationCount] = {
    "Wildstyle", "Flash FM", "K-Chat", "Fever 105", "V-Rock", "VCPR",
    "Radio Espantoso", "Emotion 98.3", "Wave 103",
};

// What a row's value means, so the drawing can colour it without reading the
// text back: held is what the player is waiting on, open is what they have, and
// plain is a count or a name that is neither.
enum class StatusTone { kPlain, kHeld, kOpen };

// One line of the panel: what it names, and what that thing is doing. A row with
// no value is a line of its own rather than a pair; a row with no LABEL is a
// wrapped line, drawn across the whole column, which is how a list of names
// reads as a sentence instead of taking a row each.
struct StatusRow {
  std::string label;
  std::string value;
  StatusTone tone = StatusTone::kPlain;
  // A row the RECENT block composed, carrying its own colours instead of a tone.
  // A row with segments has no label and no value: the segments ARE its text, and
  // the drawing prints them one after another rather than as a label-value pair.
  // Every other row leaves this empty and draws exactly as it always did, which
  // is what keeps the flattening, the fitting and the column dealing untouched.
  std::vector<ToastSegment> segments;
  // Whether this row belongs with the one above it, which is what keeps the two in
  // one column. A composer knows this where the fitting cannot work it out: a
  // toast row's location line means nothing without the sentence over it.
  bool joined_above = false;
};

// A titled block of rows. The first block carries no heading: it is the seed's
// own summary, and a heading over four lines that name themselves would only
// cost a row.
struct StatusSection {
  std::string heading;
  std::vector<StatusRow> rows;
};

// Everything the panel draws, read from the globals and from the client on the
// frame the panel is drawn. Every "known" flag exists because the panel is
// reachable before the answer is: a player can pause before the client has
// connected, and a game that has never been started has no seed hash.
struct StatusPanelState {
  bool client_connected = false;
  // The seed hash the running game stamped, empty when no game has started.
  std::string seed_hash;
  // Whether the client has sent its counts yet. The client owns them: the mod
  // knows which completion globals it watches but not which of them this seed
  // turned into locations.
  bool counts_known = false;
  int checks_done = 0;
  int checks_total = 0;
  int items_received = 0;
  bool goal_reached = false;
  // The game's own completion percentage, as its stats menu prints it. Negative
  // before a game is running, when the stat reads as nothing.
  int percentage = -1;

  // Whether the lock state below was read at all. The globals only mean anything
  // once a stamped game is running, so a page drawn before that says it does not
  // know rather than reporting a seed that locks nothing.
  bool locks_known = false;
  // Which ability keys this seed selected, and which of them are locked now.
  std::array<int, kAbilityCount> ability_flags{};
  AbilityLocks ability_locked{};
  // Which content keys this seed selected, how many districts of each are still
  // held, and which ones: a count says how far along a split seed is, the names
  // say where the player still cannot collect.
  std::array<int, kContentCount> content_flags{};
  std::array<int, kContentCount> content_districts_held{};
  std::array<bool, kContentCount * kDistrictCount> content_held{};
  // And where each class has no content at all. A district holding none of a
  // class is neither held nor free there, so it is named as neither: saying a
  // class is free somewhere it does not exist sends the player looking for
  // nothing.
  std::array<bool, kContentCount * kDistrictCount> content_absent{};
  // Every crossing off the start island, each with what it is doing: the
  // mainland ways, one entry when Mainland Access opens them all and one per
  // crossing when the seed split them, and Starfish Island last.
  std::vector<std::string> route_labels;
  std::vector<RouteState> route_states;
  // What a waiting route is waiting for, one entry per route and empty for a
  // route that waits for nothing. Only the causeway has one.
  std::vector<std::string> route_needs_labels;

  bool radio_randomized = false;
  std::array<bool, kRadioStationCount> radio_unlocked{};
  bool minimap_shuffled = false;
  bool minimap_unlocked = false;

  // What the game counts for itself, which is the progress toward the checks
  // those classes carry: nothing outside the game knows how close the next one
  // is, since the client only ever sees a location checked or not.
  int packages_collected = 0;
  int packages_total = 0;
  int paramedic_level = 0;
  int vigilante_level = 0;
  int firefighter_level = 0;
  // The taxi and the pizza boy have no level of their own in the game's stats,
  // and the two do not count the same way, so each is read from the variable its
  // own checks fire on rather than from a stat and a shared divisor.
  //
  // The taxi's checks fire on career fares at every tenth, so ten fares are a
  // level. The pizza boy's do not: its mission hands out one pizza per level
  // number, so level N takes N deliveries and a delivery total divides into
  // nothing (level ten lands at 55 deliveries, not 100). What the mission keeps
  // instead is the level it is working on, and a win flag for the last one,
  // which is also why it steps back to nine afterwards so ten can be replayed.
  int taxi_fares = 0;
  int pizza_level_in_progress = 0;
  bool pizza_finished = false;

  // Lines the client composed, because only it knows what this seed's goal asks
  // for and how far each mission strand has come. Empty until a client says.
  std::vector<StatusRow> goal_rows;
  std::vector<StatusRow> strand_rows;

  // The item movements the in-game stack has shown, newest first. The stack is a
  // marquee, so a row seen while driving is gone by the time the player can look
  // at it; this is where it went. Held by the mod rather than asked of the client,
  // since the mod already has every row it drew.
  std::vector<ToastRow> recent_rows;
};

// How many characters a wrapped line may carry. A column is 146 of the
// frontend's own units, and measured off the drawn page a character averages
// about 5.4 of them at the page's design text size, a space no narrower than
// that, so twenty-five characters is about 135 units: a column's width with room
// to spare. It is a count standing in for a width, and nothing depends on it
// being exactly right, because FitPanelLines re-breaks whatever overruns a column
// before the page is laid out. What the budget decides is where a break READS
// best, since a line broken here carries the list's own indent and a line broken
// there starts at the column edge.
constexpr std::size_t kWrappedLineChars = 25;

// A prefixed list of names, wrapped into as many lines as it takes. Every line
// is label-less, so every line is drawn from the column's own left edge: the
// prefix rides inline on the first one and the continuations are indented by as
// many spaces as the prefix has characters, which sets them in from the column
// edge so the list reads as one block. The font is proportional and a space is
// narrower than an average character, so they sit a little left of the names
// above rather than exactly under them. That every line starts at the column
// edge is also what makes the character budget honest, since the budget is
// measured against the width the whole column has.
//
// An empty list produces nothing at all, so a seed with no station of one kind
// has no line about it.
inline std::vector<StatusRow> WrapNameList(const std::string& prefix,
                                           const std::vector<std::string>& names,
                                           StatusTone tone,
                                           std::size_t max_chars) {
  std::vector<StatusRow> rows;
  if (names.empty()) return rows;
  const std::string opening = prefix + ": ";
  std::string line = opening;
  for (std::size_t index = 0; index < names.size(); ++index) {
    const bool last = index + 1 == names.size();
    const std::string piece = names[index] + (last ? "" : ",");
    // The first piece of a line always goes on it, however long it is: a name
    // wider than the column has to be somewhere, and truncating it would hide
    // which station or class it names.
    if (line.size() > opening.size() && line.size() + 1 + piece.size() > max_chars) {
      rows.push_back({"", line, tone});
      line = std::string(opening.size(), ' ');
    } else if (line.size() > opening.size()) {
      line += " ";
    }
    line += piece;
  }
  rows.push_back({"", line, tone});
  return rows;
}

// The summary block: what the mod and the client are doing, and how far along
// this seed is.
inline StatusSection ComposeSummarySection(const StatusPanelState& state) {
  StatusSection section;
  section.rows.push_back({"Client",
                          state.client_connected ? "connected" : "not connected",
                          state.client_connected ? StatusTone::kOpen : StatusTone::kHeld});
  section.rows.push_back(
      {"Seed", state.seed_hash.empty() ? "no game started" : state.seed_hash});
  if (state.counts_known) {
    section.rows.push_back({"Checks", std::to_string(state.checks_done) + "/" +
                                          std::to_string(state.checks_total)});
    section.rows.push_back({"Items", std::to_string(state.items_received)});
  }
  if (state.percentage >= 0) {
    section.rows.push_back({"Completion", std::to_string(state.percentage) + "%"});
  }
  if (state.goal_reached) {
    section.rows.push_back({"Goal", "reached", StatusTone::kOpen});
  }
  return section;
}

// The abilities as two wrapped lists, the locked ones and the ones the player
// has. Wrapped rather than a row each because eight rows of a name and one word
// is most of a column, and which list a name is in says everything a row would.
//
// The block is here for every seed, including one that locks nothing, so that a
// missing block never has to be told apart from a vanilla seed.
inline StatusSection ComposeAbilitySection(const StatusPanelState& state) {
  StatusSection section;
  section.heading = "ABILITIES";
  std::vector<std::string> locked;
  std::vector<std::string> held;
  for (int index = 0; index < kAbilityCount; ++index) {
    if (state.ability_flags[index] == 0) continue;
    (state.ability_locked[index] ? locked : held).push_back(kAbilityNames[index]);
  }
  if (locked.empty() && held.empty()) {
    section.rows.push_back({"", state.locks_known ? "This seed locks no ability."
                                                 : "No game started.",
                            StatusTone::kPlain});
    return section;
  }
  for (const StatusRow& row :
       WrapNameList("Locked", locked, StatusTone::kHeld, kWrappedLineChars)) {
    section.rows.push_back(row);
  }
  for (const StatusRow& row :
       WrapNameList("Yours", held, StatusTone::kOpen, kWrappedLineChars)) {
    section.rows.push_back(row);
  }
  return section;
}

// One block per selected content key: what the class is doing, and for a class
// held in some districts but not others, which districts those are. The names are
// the useful half of that state, because they say where the player still cannot
// collect; a count alone only says how far along the seed is.
inline StatusSection ComposeContentSection(const StatusPanelState& state) {
  StatusSection section;
  section.heading = "CONTENT";
  bool any_configured = false;
  for (int index = 0; index < kContentCount; ++index) {
    any_configured = any_configured || state.content_flags[index] != 0;
  }
  if (!any_configured) {
    // Said rather than left out, for the same reason the abilities block says it.
    section.rows.push_back({"", state.locks_known ? "This seed holds no content."
                                                  : "No game started.",
                            StatusTone::kPlain});
    return section;
  }
  for (int index = 0; index < kContentCount; ++index) {
    if (state.content_flags[index] == 0) continue;
    const int held = state.content_districts_held[index];
    // Counted against the districts that hold any of this class, not against all
    // eleven. There are robbable stores in five districts, so a seed holding
    // every one of them read as five of eleven, which says a little under half
    // when it means all of it.
    //
    // Through the helper rather than counting here, so the page and the header
    // cannot come to disagree about what present means.
    const int present = ContentDistrictsPresent(state.content_absent, index);
    if (held <= 0 || present <= 0) {
      section.rows.push_back({kContentNames[index], "available", StatusTone::kOpen});
      continue;
    }
    if (held >= present) {
      section.rows.push_back({kContentNames[index], "HELD", StatusTone::kHeld});
      continue;
    }
    // Part of the city only: the class is named on its own line and the districts
    // are wrapped under it, since eleven names never fit beside a label.
    //
    // Whichever list is shorter is the one shown, and its prefix says which it
    // is: a class held nearly everywhere is better read as the two districts it
    // is free in than as the nine it is not. Either way it is at most half the
    // city's names.
    section.rows.push_back({kContentNames[index],
                            "HELD " + std::to_string(held) + "/" +
                                std::to_string(present),
                            StatusTone::kHeld});
    const bool name_the_held = held * 2 <= present;
    std::vector<std::string> districts;
    for (int district = 0; district < kDistrictCount; ++district) {
      const std::size_t slot = ContentDistrictSlot(index, district);
      // A district with none of this class is skipped whichever list is being
      // named. It is not free there in any sense the player can act on.
      if (slot < state.content_absent.size() && state.content_absent[slot]) {
        continue;
      }
      const bool district_held = slot < state.content_held.size() &&
                                 state.content_held[slot];
      if (district_held == name_the_held) districts.push_back(kDistrictNames[district]);
    }
    for (const StatusRow& row :
         WrapNameList(name_the_held ? "held in" : "free in", districts,
                      name_the_held ? StatusTone::kHeld : StatusTone::kOpen,
                      kWrappedLineChars)) {
      section.rows.push_back(row);
    }
  }
  return section;
}

// What the seed's goal asks for and how close it is, composed by the client and
// only rendered here: the mod knows the completion globals it watches, not what
// this seed calls done.
inline StatusSection ComposeGoalSection(const StatusPanelState& state) {
  StatusSection section;
  if (state.goal_rows.empty()) return section;
  section.heading = "GOAL";
  section.rows = state.goal_rows;
  return section;
}

// How far each giver's strand has come, from the client: the counts live in the
// unlock globals the mod writes, but the strand names and how many missions each
// one holds are the world's.
//
// A row each, not a wrapped list. A strand is a name and a count, and a name like
// Vercetti Protection fills a line on its own, so wrapping them costs as many
// lines as rows and reads worse. What makes twenty of them fit is the page having
// three columns rather than two.
inline StatusSection ComposeStrandSection(const StatusPanelState& state) {
  StatusSection section;
  if (state.strand_rows.empty()) return section;
  section.heading = "MISSION STRANDS";
  for (const StatusRow& row : state.strand_rows) {
    // "3 of 5" reads as "3/5" in a column this narrow, where the words would be
    // most of the width.
    std::string count = row.value;
    const std::size_t of = count.find(" of ");
    if (of != std::string::npos) {
      count = count.substr(0, of) + "/" + count.substr(of + 4);
    }
    section.rows.push_back({row.label, count, row.tone});
  }
  return section;
}

// The progress the game itself counts toward the checks those classes carry: the
// hidden package tally the HUD shows, the level each emergency vehicle has
// reached, and the taxi and pizza levels, which the game keeps as fares and
// deliveries rather than as levels. Nothing outside the game knows any of it,
// since the client only ever sees a location checked or not.
inline StatusSection ComposeRewardSection(const StatusPanelState& state) {
  StatusSection section;
  section.heading = "THE GAME COUNTS";
  if (state.packages_total > 0) {
    const bool done = state.packages_collected >= state.packages_total;
    section.rows.push_back({"Hidden Packages",
                            std::to_string(state.packages_collected) + "/" +
                                std::to_string(state.packages_total),
                            done ? StatusTone::kOpen : StatusTone::kPlain});
  }
  // Each row shows the level its own checks are placed on. The taxi divides its
  // fares; the pizza boy cannot, so its finished levels are the level it is
  // working on less the one it has not finished, and the win flag stands for the
  // tenth on its own.
  const int taxi_level = state.taxi_fares / kTaxiFaresPerLevel;
  const int pizza_level =
      state.pizza_finished
          ? kSideJobLevels
          : (state.pizza_level_in_progress > 1 ? state.pizza_level_in_progress - 1 : 0);
  const std::pair<const char*, std::pair<int, int>> activities[] = {
      {"Paramedic", {state.paramedic_level, kEmergencyLevels}},
      {"Vigilante", {state.vigilante_level, kEmergencyLevels}},
      {"Firefighter", {state.firefighter_level, kEmergencyLevels}},
      {"Taxi", {taxi_level < kSideJobLevels ? taxi_level : kSideJobLevels,
                kSideJobLevels}},
      {"Pizza", {pizza_level < kSideJobLevels ? pizza_level : kSideJobLevels,
                 kSideJobLevels}},
  };
  for (const auto& [name, progress] : activities) {
    const auto [level, levels] = progress;
    section.rows.push_back(
        {name,
         level > 0 ? std::to_string(level) + "/" + std::to_string(levels) : "none",
         level >= levels ? StatusTone::kOpen
                         : (level > 0 ? StatusTone::kPlain : StatusTone::kPlain)});
  }
  return section;
}

// One row per crossing off the start island, the mainland ways and Starfish
// Island. A route whose item arrived while the second item its route needs is
// missing says so rather than reading as plainly shut, since that is the one
// state a player can act on.
inline StatusSection ComposeRouteSection(const StatusPanelState& state) {
  StatusSection section;
  section.heading = "CROSSINGS";
  const std::size_t count = state.route_labels.size() < state.route_states.size()
                                ? state.route_labels.size()
                                : state.route_states.size();
  for (std::size_t index = 0; index < count; ++index) {
    std::string value = "shut";
    if (state.route_states[index] == RouteState::kOpen) {
      value = "open";
    } else if (state.route_states[index] == RouteState::kWaiting) {
      // The label where the seed sent one. A route waiting with no label named is
      // a config a client one field older sent, so the generic line stands in.
      value = index < state.route_needs_labels.size() &&
                      !state.route_needs_labels[index].empty()
                  ? "needs " + state.route_needs_labels[index]
                  : "needs its island";
    }
    section.rows.push_back({state.route_labels[index], value,
                            state.route_states[index] == RouteState::kOpen
                                ? StatusTone::kOpen
                                : StatusTone::kHeld});
  }
  return section;
}

// One row per station while the radio is randomized, and one for the minimap
// while it is shuffled. Both options hold something the player can see is
// missing without being told why, which is what these rows answer.
inline StatusSection ComposeRadioSection(const StatusPanelState& state) {
  StatusSection section;
  if (!state.radio_randomized) return section;
  section.heading = "RADIO";
  // Wrapped lists rather than a row per station: nine rows of a name and one
  // word is most of a column spent on the least of the seed's state, and the
  // stations have nothing to say beyond which side they are on.
  std::vector<std::string> unlocked;
  std::vector<std::string> locked;
  for (int station = 0; station < kRadioStationCount; ++station) {
    (state.radio_unlocked[station] ? unlocked : locked)
        .push_back(kRadioStationNames[station]);
  }
  for (const StatusRow& row :
       WrapNameList("Yours", unlocked, StatusTone::kOpen, kWrappedLineChars)) {
    section.rows.push_back(row);
  }
  for (const StatusRow& row :
       WrapNameList("Locked", locked, StatusTone::kHeld, kWrappedLineChars)) {
    section.rows.push_back(row);
  }
  return section;
}

inline StatusSection ComposeMinimapSection(const StatusPanelState& state) {
  StatusSection section;
  if (!state.minimap_shuffled) return section;
  section.heading = "MINIMAP";
  section.rows.push_back({"Radar", state.minimap_unlocked ? "shown" : "HIDDEN",
                          state.minimap_unlocked ? StatusTone::kOpen
                                                 : StatusTone::kHeld});
  return section;
}

// How many spaces a recent row's continuation lines are set in by, matching the
// indent the in-game stack gives them so a row reads the same way in both places.
// A count of spaces rather than a width, because the panel composes text and the
// fitting measures it afterwards.
constexpr std::size_t kRecentContinuationSpaces = 2;

// The most lines RECENT may add to the page. The row height comes from the
// TALLEST column and the whole page's text size is fitted to it, so an unbounded
// history would shrink every other block the moment a single item moved. Held
// under a column's own share, so RECENT costs the page nothing it was not already
// laying out. The ring behind it keeps more rows than this: the budget decides how
// many are shown, not how many are remembered.
constexpr std::size_t kRecentMaxLines = 14;

// The item movements the stack has shown, newest first, in the same colours it
// drew them in.
//
// One panel line per line of a row, so a two-line row takes two rows here as
// well: the sentence, then its location set in beneath it. A row's lines are kept
// in their own order, unlike the stack's, because a list read top to bottom wants
// the sentence above its location and the stack only reverses them because it
// climbs.
inline StatusSection ComposeRecentSection(const StatusPanelState& state) {
  StatusSection section;
  if (state.recent_rows.empty()) return section;
  section.heading = "RECENT";
  for (const ToastRow& row : state.recent_rows) {
    // Whole rows only. Half a row is a sentence with no location or a location
    // with no sentence, and the second is worse than leaving the row out.
    if (section.rows.size() + row.lines.size() > kRecentMaxLines) break;
    for (std::size_t index = 0; index < row.lines.size(); ++index) {
      StatusRow panel_row;
      if (index > 0) {
        panel_row.segments.push_back(
            {std::string(kRecentContinuationSpaces, ' '), ToastRole::kConnective});
      }
      for (const ToastSegment& segment : row.lines[index]) {
        panel_row.segments.push_back(segment);
      }
      // A line with nothing on it at all. BuildToastRow drops empty lines, so a row
      // reaching here has none, and this is a guard against a row built some other
      // way rather than a case the stack produces.
      if (panel_row.segments.empty()) continue;
      // Every line after a row's first belongs with the one above it, so the
      // column dealing keeps them together: a location at the head of one column
      // with its sentence at the foot of the last names nothing at all.
      panel_row.joined_above = index > 0;
      section.rows.push_back(panel_row);
    }
  }
  return section;
}

// The whole panel, in reading order. A block with no rows is dropped rather than
// drawn as a heading over nothing: a seed that locks no abilities has no ABILITIES
// block at all, rather than one saying so.
inline std::vector<StatusSection> ComposeStatusPanel(const StatusPanelState& state) {
  std::vector<StatusSection> sections;
  for (const StatusSection& section :
       {ComposeSummarySection(state), ComposeGoalSection(state),
        ComposeStrandSection(state), ComposeAbilitySection(state),
        ComposeContentSection(state), ComposeRewardSection(state),
        ComposeRouteSection(state), ComposeRadioSection(state),
        ComposeMinimapSection(state), ComposeRecentSection(state)}) {
    if (!section.rows.empty()) sections.push_back(section);
  }
  return sections;
}

// What the menu looks like on one frame, as far as the panel cares: everything
// the decision below reads, so the decision itself can be exercised without a
// game. The page and entry numbers are the game's own, passed in rather than
// named here, because this header carries no game headers.
struct PanelMenuState {
  // Whether the pause menu carries the panel's entry at all.
  bool owns_entry = false;
  bool game_loaded = false;
  int page = -1;
  int highlighted_entry = -1;
  int pause_page = -1;
  int host_page = -1;
  // The pause-menu row the panel's entry sits on.
  int panel_entry = -1;
  // Whether the row under the highlight carries the borrowed page as its target,
  // which is true of the panel's own entry and of that page's vanilla entry. The
  // caller leaves highlighted_entry negative for a row outside the page's own
  // table, so nothing here can name a row the game does not have.
  bool highlighted_entry_targets_host = false;
};

// What the panel does with a menu frame: whether the borrowed page should now
// show the panel rather than its own content, whether to draw it this frame, and
// what to write into the borrowed page's parent entry so going back lands on the
// row the player came from.
//
// The arming is a latch rather than a test, because by the time the borrowed page
// is showing, the game has already reset the highlight to its first row: the row
// that opened it is only knowable from the frame before.
struct PanelFrame {
  bool armed = false;
  bool draw = false;
  // Negative when nothing should be written this frame.
  int parent_entry = -1;
};

inline PanelFrame PlanPanelFrame(const PanelMenuState& state, bool armed_was) {
  PanelFrame frame;
  frame.armed = armed_was;
  if (!state.owns_entry) {
    frame.armed = false;
    return frame;
  }
  if (state.page == state.pause_page) {
    frame.armed = state.highlighted_entry == state.panel_entry;
    // Only a row carrying the borrowed page belongs in that page's parent entry.
    // The pause menu's other rows lead elsewhere, and writing one of those would
    // leave the field naming a row that cannot come back from there.
    if (state.highlighted_entry_targets_host && state.highlighted_entry >= 0) {
      frame.parent_entry = state.highlighted_entry;
    }
    return frame;
  }
  frame.draw = frame.armed && state.game_loaded && state.page == state.host_page;
  return frame;
}

// One drawn line of the panel. The blocks are flattened into lines before they
// are laid out, so a block taller than a column continues in the next one instead
// of setting the row height for the whole page: twenty mission strands are a
// column and a half on their own, and keeping them whole shrank everything else
// to fit them.
struct PanelLine {
  std::string label;
  std::string value;
  StatusTone tone = StatusTone::kPlain;
  // A heading is drawn in the heading face; a blank line separates blocks and
  // never opens a column.
  bool heading = false;
  bool blank = false;
  // A value the fitting moved off its label's line, drawn against the column's
  // right edge where it would have sat had it fitted beside the label.
  bool value_alone = false;
  // A line the fitting broke out of the one above it, which is what keeps the two
  // in the same column: a value at the head of one column with its label at the
  // foot of the last names nothing at all.
  bool joined_above = false;
  // A recent row's own coloured text. A line with segments carries no label and no
  // value, so every other line in the panel is unaffected by its presence.
  std::vector<ToastSegment> segments;
};

inline std::vector<PanelLine> FlattenPanel(const std::vector<StatusSection>& sections) {
  std::vector<PanelLine> lines;
  for (const StatusSection& section : sections) {
    if (!lines.empty()) {
      PanelLine blank;
      blank.blank = true;
      lines.push_back(blank);
    }
    if (!section.heading.empty()) {
      PanelLine heading;
      heading.label = section.heading;
      heading.heading = true;
      lines.push_back(heading);
    }
    for (const StatusRow& row : section.rows) {
      PanelLine line;
      line.label = row.label;
      line.value = row.value;
      line.tone = row.tone;
      line.segments = row.segments;
      line.joined_above = row.joined_above;
      lines.push_back(line);
    }
  }
  return lines;
}

// The panel's lines, each one narrowed until it draws on a single line.
//
// The drawing gives every line one row, and the font folds a line that reaches the
// column's edge at its last space, so a line wider than its column lands its tail
// on the row below and prints over it. This is the pass that makes one line per row
// true: a label and a value too wide to share a row are split so the value takes
// the next row on its own, against the column's right edge where it would have sat
// beside the label, and any text still wider than its column is broken at its own
// spaces.
//
// Measured at the design size, which is the largest the page ever draws at, so a
// line that fits here fits at every size the fitting can pick. Headings and
// segmented lines each take a measure of their own, because neither draws in the
// body's face and size: the taller the band the panel is given the larger the whole
// page draws, and a line measured under the wrong one of the three is either folded
// or cut when it need not have been.
inline std::vector<PanelLine> FitPanelLines(const std::vector<PanelLine>& lines,
                                            float column_width, float label_gap,
                                            TextWidth measure,
                                            TextWidth heading_measure,
                                            TextWidth segment_measure) {
  std::vector<PanelLine> fitted;
  fitted.reserve(lines.size());
  // Every piece a line breaks into after the first belongs with the one before it,
  // so the dealing keeps them in one column.
  // A piece past the first belongs with the piece before it. A line that ARRIVED
  // joined stays joined through its first piece as well: the composer knew
  // something the breaking cannot see, which is that this line means nothing
  // without the one above it.
  const auto push = [&fitted](PanelLine line, std::size_t piece) {
    line.joined_above = line.joined_above || piece > 0;
    fitted.push_back(std::move(line));
  };
  for (const PanelLine& line : lines) {
    if (line.blank) {
      fitted.push_back(line);
      continue;
    }
    // A segmented line is cut to its column rather than broken across rows, so it
    // reaches the drawing as exactly one line and the one-line-per-row guarantee
    // holds for it the same way it holds for everything else.
    if (!line.segments.empty()) {
      PanelLine part = line;
      // Its own measure: a segmented line draws smaller than the rows around it,
      // so measuring it at the body size would cut it short of the column.
      part.segments =
          FitSegmentLine(line.segments, column_width, segment_measure);
      fitted.push_back(part);
      continue;
    }
    if (line.heading) {
      std::size_t piece = 0;
      for (const std::string& text :
           BreakToWidth(line.label, column_width, heading_measure)) {
        PanelLine part = line;
        part.label = text;
        push(part, piece++);
      }
      continue;
    }
    if (line.label.empty()) {
      if (line.value.empty()) {
        fitted.push_back(line);
        continue;
      }
      std::size_t piece = 0;
      for (const std::string& text :
           BreakToWidth(line.value, column_width, measure)) {
        PanelLine part = line;
        part.value = text;
        push(part, piece++);
      }
      continue;
    }
    if (!line.value.empty() &&
        measure(line.label) + label_gap + measure(line.value) <= column_width) {
      fitted.push_back(line);
      continue;
    }
    // The label takes the rows it needs, and the value the row after them.
    std::size_t piece = 0;
    for (const std::string& text :
         BreakToWidth(line.label, column_width, measure)) {
      PanelLine part = line;
      part.label = text;
      part.value.clear();
      push(part, piece++);
    }
    if (line.value.empty()) continue;
    for (const std::string& text :
         BreakToWidth(line.value, column_width, measure)) {
      PanelLine part = line;
      part.label.clear();
      part.value = text;
      part.value_alone = true;
      push(part, piece++);
    }
  }
  return fitted;
}

// The panel's lines dealt into columns of even height, in reading order: down one
// column and on to the next. A column never opens with a blank line and never ends
// with a heading, so a block's title always sits above at least one of its own
// lines; and a run of lines the fitting broke out of one line is kept in a single
// column, so a value it moved off its label's row still stands under that label.
//
// That last one holds unless the run is longer than a column's own share, which has
// to break somewhere: the dealing then leaves one line behind and carries the rest
// on, so the only column that can open on a broken-out line is one whose neighbour
// holds a single line. No page any seed composes comes near it, since the longest
// run is a label and its value and a share is many times that.
inline std::vector<std::vector<PanelLine>> PlanPanelColumns(
    const std::vector<PanelLine>& lines, int column_count) {
  std::vector<std::vector<PanelLine>> columns;
  if (column_count < 1) return columns;
  columns.resize(static_cast<std::size_t>(column_count));
  if (lines.empty()) return columns;
  const int total = static_cast<int>(lines.size());
  std::size_t next = 0;
  for (int column = 0; column < column_count && next < lines.size(); ++column) {
    const int columns_left = column_count - column;
    const int remaining = total - static_cast<int>(next);
    const int share = (remaining + columns_left - 1) / columns_left;
    // A blank line at the head of a column is dropped: the column edge already
    // separates it from what came before.
    while (next < lines.size() && lines[next].blank) ++next;
    std::vector<PanelLine>& target = columns[static_cast<std::size_t>(column)];
    while (next < lines.size() &&
           (column + 1 == column_count || static_cast<int>(target.size()) < share)) {
      target.push_back(lines[next]);
      ++next;
    }
    // The fitting can turn one row into several, a label too wide for its column
    // and the value it no longer shares a row with. A column must not open on one
    // of those, so the whole run moves on together. One line is always left behind,
    // since a run longer than the column has to break somewhere.
    while (next < lines.size() && lines[next].joined_above && target.size() > 1) {
      --next;
      target.pop_back();
    }
    // A heading last in a column would title lines that are not there; it moves
    // to the next column with them.
    while (!target.empty() && target.back().heading && next <= lines.size()) {
      --next;
      target.pop_back();
    }
  }
  return columns;
}

// The tallest column, which is what the row height has to fit.
inline int TallestColumn(const std::vector<std::vector<PanelLine>>& columns) {
  int tallest = 0;
  for (const std::vector<PanelLine>& column : columns) {
    const int rows = static_cast<int>(column.size());
    if (rows > tallest) tallest = rows;
  }
  return tallest;
}

// The row height the panel draws at: the design height, or as much less as it
// takes for the tallest column to fit the band the cover leaves. Every seed's
// page therefore fits whole, and only a seed that configured everything is drawn
// tighter than the rest.
inline float FittedRowHeight(int rows, float band_height,
                            float design_row_height) {
  if (rows <= 0) return design_row_height;
  const float fitted = band_height / static_cast<float>(rows);
  return fitted < design_row_height ? fitted : design_row_height;
}

// What the text scales by when the rows had to be drawn tighter than the design.
// A glyph is taller than its row's share of the band otherwise: the seed that
// fills the page would draw its lines into each other. Tying the scale to the row
// height is also what keeps the fitting's own measurements true, since a line
// measured at the design size only ever draws narrower than that.
inline float FittedTextScale(float row_height, float design_row_height) {
  if (design_row_height <= 0.0f) return 1.0f;
  return row_height < design_row_height ? row_height / design_row_height : 1.0f;
}

}  // namespace gtavc
