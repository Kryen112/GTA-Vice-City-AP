// The toast stack's whole model, and the text fitting every thing the mod draws
// itself shares, free of any game headers so the console self-test can exercise
// all of it without plugin-sdk or the game. The pause menu's status page measures
// and cuts through the same helpers, which is what keeps one definition of how
// wide a line is and what a cut line looks like.
//
// A toast is one row the mod draws itself, above the radar, in the band the
// vanilla HUD leaves free on the left edge. The game's own brief-message channel
// queues eight and DRAWS ONE, so posting a row per line held the screen for a
// multiple of a message's time and dropped everything past the eighth. Nothing
// here goes through that channel.
//
// The mechanism that makes a burst readable is that a row's clock starts when the
// row BECOMES VISIBLE, not when it arrived. So the band is always as full as it
// can be, every row gets its whole lifetime on screen, and a backlog drains at
// the band's own rate instead of waiting behind arrival times that have already
// passed. Nothing is dropped short of kToastQueueMax, which is a runaway
// backstop far above any release rather than a policy.
#pragma once

#include <array>
#include <cstddef>
#include <cstdlib>
#include <string>
#include <utility>
#include <vector>

namespace gtavc {

// What a segment of a row's text is, which decides the colour it draws in. These
// are Archipelago's own roles, so a row reads the same way here as it does in the
// client window and in every tracker.
enum class ToastRole {
  kConnective,
  kOwnSlot,
  kOtherSlot,
  kProgression,
  kUseful,
  kTrap,
  kFiller,
  kLocation,
};

// One run of text in one role. A row is a list of these rather than a string,
// because the whole point of the palette is that the item and the player name
// carry different colours inside one sentence.
struct ToastSegment {
  std::string text;
  ToastRole role = ToastRole::kConnective;
};

// The most segments one row may carry, borrowed from the Harry Potter 2 mod's own
// bound. The richest row here is eight: "You sent ", the item, " to ", the player,
// then "(", the location, ")" on the second line.
constexpr std::size_t kToastMaxSegments = 10;
// The most lines one row may carry. Two in practice, the sentence and the
// location beneath it, and the bound is what keeps one row from taking the band.
constexpr std::size_t kToastMaxLines = 4;

// One row: its lines of segments, top to bottom. A row with no lines is not a
// row, which is how an inactive notice is spelled.
struct ToastRow {
  std::vector<std::vector<ToastSegment>> lines;

  bool empty() const { return lines.empty(); }
  // How much of the band this row takes. Measured in lines rather than rows
  // because a two-line row costs twice a one-line row, and the band is a height.
  std::size_t line_count() const { return lines.size(); }
};

// A row on screen, with the moment its lifetime started.
struct LiveToast {
  ToastRow row;
  unsigned int shown_at_ms = 0;
  // Whether the row's lines have been cut to the band's width yet. The cut needs
  // the font, and the font only exists on the draw, so it happens on the first
  // frame the row is visible and never again: a row is cut once, not measured
  // every frame it is up.
  bool fitted = false;
};

// A row on its way into the stack: not shown yet, and not cut to the band yet.
// The clock is stamped when it is admitted, which is the whole mechanism.
inline LiveToast QueuedToast(const ToastRow& row) {
  LiveToast queued;
  queued.row = row;
  return queued;
}

// The rows that hold their place until something clears them, each addressed by
// what it is about so a repeat replaces rather than stacks. Both explain a state
// the player has to act on rather than reporting an event, so neither expires.
enum class ToastNotice {
  // Why nothing in this seed will work: the client refused the running game.
  kHandshakeRefusal,
  // The bridge is down, so checks are going nowhere.
  kBridgeDown,
};
constexpr std::size_t kToastNoticeCount = 2;

inline std::size_t ToastNoticeSlot(ToastNotice notice) {
  return static_cast<std::size_t>(notice);
}

// How long a row holds the screen once it is visible. One number for every row:
// the colour already says what kind of row it is, and a single lifetime makes the
// band's drain rate one division rather than a function of what happens to be in
// it.
constexpr unsigned int kToastLifetimeMs = 4000;

// The most rows the queue holds. The queue is meant to be unbounded, so this is a
// runaway backstop rather than a policy: a release of every item in a large
// multiworld is hundreds of rows, and the bound is far above that. Reaching it
// means something is generating rows that are not item movements.
constexpr std::size_t kToastQueueMax = 4096;

// How many rows the pause page's RECENT block keeps. A page column holds some
// twenty lines and a row is usually two of them, so this fills about one column
// and leaves the rest of the page to the seed's own state.
constexpr std::size_t kRecentToastMax = 12;

// The whole stack between frames. The caller owns one and hands it to Advance
// every frame.
struct ToastStackState {
  // The notices, indexed by ToastNotice. An empty row is an inactive notice.
  std::array<ToastRow, kToastNoticeCount> notices{};
  // And whether each has been cut to the band, for the same reason a rotating row
  // carries the flag. Cleared whenever a notice is set or cleared, so replacing
  // one re-cuts the new text rather than trusting the last one's measurement.
  std::array<bool, kToastNoticeCount> notices_fitted{};
  // The rotating rows, oldest first. Drawn above the notices.
  std::vector<LiveToast> visible;
  // What has not been shown yet, in arrival order. The same type as a visible row
  // so a queued row carries the record of having been cut to the band: the cutting
  // has to happen before the admission reads a line count, and a queue of hundreds
  // must not be re-measured on every frame it waits.
  std::vector<LiveToast> waiting;
};

// The frontend's own virtual screen, which everything the mod draws is laid out
// in. Named here rather than beside the drawing because the geometry bounds are
// measured against it and the console self-test has to reach them; hud_text
// re-exports these under their drawing names.
constexpr float kVirtualScreenWidth = 640.0f;
constexpr float kVirtualScreenHeight = 448.0f;

// Where the stack draws, in the frontend's own 640x448 units. Defaults are the
// measured band: the anchor sits just above the radar's top edge at y 256, the
// ceiling clears the help box, and the width holds a sentence with a location
// without wrapping. An optional ini beside the module may override any of them,
// which is why this is a struct of values rather than a set of constants.
struct ToastGeometry {
  float anchor_x = 18.0f;
  // Where the LOWEST line draws. Rows stack upward from here.
  float anchor_y = 250.0f;
  // How wide a line may draw before the font folds it.
  float width = 340.0f;
  // The highest a line may draw, which is what bounds the band.
  float ceiling_y = 100.0f;
  float line_height = 17.0f;
  float scale_x = 0.55f;
  float scale_y = 0.9f;
  // How far a row's second and later lines are set in from the first, so the
  // location reads as belonging to the sentence above it.
  float continuation_indent = 10.0f;
  unsigned int lifetime_ms = kToastLifetimeMs;
};

// How many lines the band holds. The lowest line draws at anchor_y and each one
// above it a line_height higher, so the topmost usable line is the last one at or
// below the ceiling. A geometry whose band is shorter than one line still holds
// one: a stack that can draw nothing would swallow the handshake refusal, which
// is the one row that must always be readable.
inline std::size_t ToastLineCapacity(const ToastGeometry& geometry) {
  if (geometry.line_height <= 0.0f) return 1;
  const float band = geometry.anchor_y - geometry.ceiling_y;
  if (band < 0.0f) return 1;
  const std::size_t lines =
      static_cast<std::size_t>(band / geometry.line_height) + 1;
  return lines < 1 ? 1 : lines;
}

// How many lines the notices are holding, which comes off the band before the
// rotating rows get any of it.
inline std::size_t ToastNoticeLines(const ToastStackState& state) {
  std::size_t lines = 0;
  for (const ToastRow& notice : state.notices) lines += notice.line_count();
  return lines;
}

// Whether a visible row's time is up. The subtraction is signed so the answer
// stays right across the millisecond counter's wrap.
inline bool ToastExpired(const LiveToast& live, unsigned int now_ms,
                         unsigned int lifetime_ms) {
  return static_cast<int>(now_ms - live.shown_at_ms) >=
         static_cast<int>(lifetime_ms);
}

// Expire what is finished and admit what fits, in that order, so a row leaving
// this frame frees its lines for a row entering the same frame. Rows are admitted
// whole: a two-line row waits for two free lines rather than showing half of
// itself.
//
// Admission stops at the first row that does not fit rather than skipping it for
// a shorter one behind it, because arrival order is the only order these rows
// have and reordering them would make the stack a worse record than the queue.
inline void AdvanceToastStack(ToastStackState& state, unsigned int now_ms,
                              std::size_t line_capacity,
                              unsigned int lifetime_ms) {
  std::vector<LiveToast> kept;
  kept.reserve(state.visible.size());
  for (const LiveToast& live : state.visible) {
    if (!ToastExpired(live, now_ms, lifetime_ms)) kept.push_back(live);
  }
  state.visible.swap(kept);

  const std::size_t notice_lines = ToastNoticeLines(state);
  // The notices never give their lines back, so what is left is what rotates.
  // Floored at NOTHING and not at one line: reserving a line the band does not
  // have would admit a row the drawing then clips at the ceiling, and a row that
  // started its clock and was never drawn is exactly the silent loss this whole
  // design exists to avoid. A band too small for both is a band the notices own,
  // which is the right answer when they are what explains why nothing works.
  const std::size_t rotating_capacity =
      line_capacity > notice_lines ? line_capacity - notice_lines : 0;

  std::size_t used = 0;
  for (const LiveToast& live : state.visible) used += live.row.line_count();

  // A notice can arrive under rows already up, and it takes its lines off the band
  // whether or not they were free. The oldest rows go, from the front, because
  // they are the ones that have been read: dropping a row that has held the screen
  // is not the silent loss the admission rule guards against, and leaving them
  // would push the top of the stack past the ceiling where the drawing would clip
  // it away unseen for the rest of its lifetime.
  while (used > rotating_capacity && !state.visible.empty()) {
    used -= state.visible.front().row.line_count();
    // Back onto the head of the queue rather than dropped. A row can be evicted
    // after a single frame on screen, which is not "it has been read", and the one
    // rule this whole design rests on is that nothing is lost. It keeps its cut,
    // so re-admitting it measures nothing again, and its clock restarts when it is
    // visible again, which is what the clock has always meant.
    state.waiting.insert(state.waiting.begin(), state.visible.front());
    state.visible.erase(state.visible.begin());
  }

  std::size_t admitted = 0;
  for (const LiveToast& queued : state.waiting) {
    const ToastRow& row = queued.row;
    const std::size_t cost = row.line_count();
    if (cost == 0) {
      ++admitted;
      continue;
    }
    if (used + cost > rotating_capacity) {
      // A row taller than the whole rotating band would otherwise sit at the head
      // forever, showing nothing and blocking every row behind it. So when the
      // band is empty and still cannot hold it, it is admitted with its LEADING
      // lines only, which is its sentence: the drawing lays a row's lines out
      // upward from its last, so a row that overran would show its location with
      // the sentence clipped off the top, and an orphan location names nothing.
      // Cutting it here decides which half survives instead of leaving that to
      // where the ceiling happens to fall.
      //
      // Only reachable through a hand-edited geometry: the measured band holds
      // nine lines and a row may carry four.
      if (!state.visible.empty() || rotating_capacity == 0) break;
      LiveToast trimmed = queued;
      trimmed.row.lines.resize(rotating_capacity);
      trimmed.shown_at_ms = now_ms;
      state.visible.push_back(trimmed);
      used += rotating_capacity;
      ++admitted;
      break;
    }
    LiveToast admit = queued;
    admit.shown_at_ms = now_ms;
    state.visible.push_back(admit);
    used += cost;
    ++admitted;
  }
  state.waiting.erase(state.waiting.begin(),
                      state.waiting.begin() + static_cast<std::ptrdiff_t>(admitted));
}

// One line's text, joined. The width of a LINE is measured from this rather than
// summed from its segments: a per-segment measure is exact for that segment but
// summing them drifts and spreads the words apart, so the fitting asks about the
// line it actually draws. The drawing still measures per segment, but only to
// advance from one to the next, never to decide whether the line fits.
inline std::string ToastLineText(const std::vector<ToastSegment>& line) {
  std::string text;
  for (const ToastSegment& segment : line) text += segment.text;
  return text;
}

// How wide a string draws, in whatever unit the caller measures in. The pause
// page hands in the font's own measure at its design size and the in-game stack
// hands in one at its own scale; the console self-test hands in one of its own,
// so the fitting runs without a font at all.
using TextWidth = float (*)(const std::string&);

// What marks a line the fitting had to cut. A row is a sentence the client
// composed and the mod cannot re-break it at a sensible place without knowing
// which segment is the item and which the location, so an over-wide one is cut
// rather than folded, and this says so.
//
// CUT and not wrapped, deliberately, and this is the load-bearing reason: CFont
// folds a line that reaches its wrap edge at the line's last space, and the fold
// advance IS a row height, so a folded line lands its tail glyph-on-glyph over
// the row below it. The pause page learned that the hard way. A cut line is
// always one line, which is also what keeps ToastRow::line_count honest against
// the band the admission bound is measured in.
constexpr const char* kToastEllipsis = "...";

// One segmented line narrowed until it draws inside its column.
//
// Cut rather than broken: a label or a value is text the panel composed and can
// re-break at its own spaces, but a segmented line's break points are inside
// coloured runs and a fold would put half an item name in the next row. So the
// tail is trimmed a character at a time, dropping a whole segment when it runs
// out, and the ellipsis lands in whatever segment survives, drawing in that
// segment's own colour.
//
// The trim measures once per character removed, which only happens on a line that
// actually overruns. That is why FitToastStack below cuts a row ONCE and records
// it: the pause page is drawn on a paused frame and can afford the walk every
// time, but the in-game stack is drawn on every frame a game is up and cannot.
inline std::vector<ToastSegment> FitSegmentLine(
    const std::vector<ToastSegment>& segments, float column_width,
    TextWidth measure) {
  std::vector<ToastSegment> fitted = segments;
  if (measure(ToastLineText(fitted)) <= column_width) return fitted;
  while (!fitted.empty()) {
    if (fitted.back().text.empty()) {
      fitted.pop_back();
      continue;
    }
    fitted.back().text.pop_back();
    if (measure(ToastLineText(fitted) + kToastEllipsis) <= column_width) {
      fitted.back().text += kToastEllipsis;
      return fitted;
    }
  }
  return fitted;
}

// The pieces a line's text breaks into, each narrow enough for its column: the
// text itself where it already fits, and as many pieces as it takes where it does
// not, broken at its own spaces.
//
// A continuation is set in under the line it continues. A wrapped list's own
// continuations already carry leading spaces, so a piece broken out of one keeps
// them; the line the list's prefix rides on carries none, so its continuations are
// set in as far as that prefix runs, which is where the composer's own wrapping
// puts them. A word wider than a column is a piece of its own: it has no space to
// break at, so the font cannot fold it either, and it draws across the gutter
// rather than being hidden.
inline std::vector<std::string> BreakToWidth(const std::string& text, float width,
                                             TextWidth measure) {
  std::vector<std::string> pieces;
  const std::size_t opening = text.find_first_not_of(' ');
  if (measure(text) <= width || opening == std::string::npos) {
    pieces.push_back(text);
    return pieces;
  }
  const std::string opening_indent(opening, ' ');
  std::string continuation = opening_indent;
  if (opening == 0) {
    // A prefix is a name, a colon and a space, which is the one shape the
    // composer's own wrapping indents under.
    const std::size_t colon = text.find(':');
    if (colon != std::string::npos && colon + 1 < text.size() &&
        text[colon + 1] == ' ') {
      const std::string prefix(colon + 2, ' ');
      // An indent worth half a column leaves too little of the column for the
      // words it sets in, so a colon that late in a line is not a prefix worth
      // following.
      if (measure(prefix) * 2.0f < width) continuation = prefix;
    }
  }
  std::string current;
  std::size_t index = opening;
  while (index < text.size()) {
    const std::size_t space = text.find(' ', index);
    const std::size_t length =
        space == std::string::npos ? std::string::npos : space - index;
    const std::string word = text.substr(index, length);
    index = space == std::string::npos ? text.size() : space + 1;
    if (word.empty()) continue;
    // The first word of a piece always goes on it, however wide it is, and only
    // the first piece opens where the line itself opened.
    if (current.empty()) {
      current = (pieces.empty() ? opening_indent : continuation) + word;
      continue;
    }
    const std::string grown = current + " " + word;
    if (measure(grown) > width) {
      pieces.push_back(current);
      current = continuation + word;
      continue;
    }
    current = grown;
  }
  if (!current.empty()) pieces.push_back(current);
  return pieces;
}

// A single-role row of one line, which is what a notice is.
inline ToastRow PlainToastRow(const std::string& text, ToastRole role) {
  ToastRow row;
  if (text.empty()) return row;
  row.lines.push_back({{text, role}});
  return row;
}

// Every line of one row cut to the width that line actually draws in. A row's
// first line starts at the anchor and the rest are set in, so they have LESS room
// than the first, and one width for both is a line cut to just inside the band and
// then drawn a whole indent past its edge. FitSegmentLine stops as soon as the
// text plus the ellipsis fits, so a cut line sits within a character of whatever
// width it was given: fitting a continuation line to the first line's width does
// not usually overrun, it always does.
inline void FitToastRow(ToastRow& row, float first_width,
                        float continuation_width, TextWidth measure) {
  for (std::size_t index = 0; index < row.lines.size(); ++index) {
    row.lines[index] = FitSegmentLine(
        row.lines[index], index == 0 ? first_width : continuation_width, measure);
  }
}

// A row broken across lines rather than cut, for text where losing the tail loses
// the point. The handshake refusal names the reason nothing in the seed will work,
// and a reason cut to nothing explains nothing, so a notice is broken where an
// item row is cut: an item row's tail is a location, and the sentence in front of
// it still says what moved.
//
// Bounded by kToastMaxLines, and whatever will not fit in them is cut, so a notice
// can never take the band however long its text.
inline void BreakToastRow(ToastRow& row, float first_width,
                          float continuation_width, TextWidth measure) {
  std::vector<std::vector<ToastSegment>> broken;
  for (const std::vector<ToastSegment>& line : row.lines) {
    // The role of the line's own first segment: a notice is one role throughout,
    // which is what makes breaking its text and keeping its colour meaningful.
    const ToastRole role =
        line.empty() ? ToastRole::kConnective : line.front().role;
    std::string remaining = ToastLineText(line);
    // One piece at a time, each measured against the width of the line it will
    // actually land on. Breaking the whole text against ONE width fills every
    // piece to that width, and the pieces bound for the indented lines then have
    // to be cut back, which puts an ellipsis in the middle of a notice and loses
    // the words the breaking existed to keep.
    while (!remaining.empty() && broken.size() < kToastMaxLines) {
      const float width = broken.empty() ? first_width : continuation_width;
      const std::vector<std::string> pieces =
          BreakToWidth(remaining, width, measure);
      if (pieces.empty()) break;
      broken.push_back({{pieces.front(), role}});
      // What the first piece did not take. Measured off the piece rather than
      // re-joined, so a break that consumed a space does not leave one behind.
      const std::size_t taken = pieces.front().size();
      remaining = taken >= remaining.size() ? std::string()
                                            : remaining.substr(taken);
      const std::size_t first = remaining.find_first_not_of(' ');
      remaining = first == std::string::npos ? std::string()
                                             : remaining.substr(first);
    }
  }
  row.lines.swap(broken);
  // A last cut against each line's own width. Nothing should need it, since every
  // piece was broken to the width it draws in; it catches a word longer than a
  // whole line, which has nowhere to break and would otherwise reach the wrap edge.
  for (std::size_t index = 0; index < row.lines.size(); ++index) {
    row.lines[index] = FitSegmentLine(
        row.lines[index], index == 0 ? first_width : continuation_width, measure);
  }
}

// Cut whatever has not been cut yet, and record that it has been. Runs on the
// draw, because measuring needs the font; runs before the drawing rather than
// inside it, so the drawing never has to ask how wide anything is and a line it
// is handed can be trusted to fit the band.
//
// This is what stops CFont folding a line at its wrap edge and landing the tail
// glyph-on-glyph over the row below. Without it a long location name, or the
// handshake refusal, prints over its neighbour for as long as it is up.
inline void FitToastStack(ToastStackState& state, float first_width,
                          float continuation_width, std::size_t line_capacity,
                          TextWidth measure) {
  for (std::size_t index = 0; index < kToastNoticeCount; ++index) {
    if (state.notices_fitted[index] || state.notices[index].empty()) continue;
    BreakToastRow(state.notices[index], first_width, continuation_width, measure);
    state.notices_fitted[index] = true;
  }
  for (LiveToast& live : state.visible) {
    if (live.fitted) continue;
    FitToastRow(live.row, first_width, continuation_width, measure);
    live.fitted = true;
  }
  // The queue too, and before the advance rather than after it. A row's line count
  // is what the band is measured in, and breaking a notice CHANGES that count, so
  // every count the admission reads has to be final before it reads any of them.
  // Only as far into the queue as the advance could possibly reach. A row is at
  // least one line, so at most line_capacity of them can be admitted on any frame,
  // and cutting the rest would put a per-character trim walk for every row of a
  // whole-multiworld release into the single frame it lands on. The rest are cut
  // on the frames they come within reach.
  std::size_t cut = 0;
  for (LiveToast& queued : state.waiting) {
    if (cut >= line_capacity) break;
    if (queued.fitted) continue;
    FitToastRow(queued.row, first_width, continuation_width, measure);
    queued.fitted = true;
    ++cut;
  }
}

// The rows to draw, anchor first and upward from there: the notices sit lowest,
// because they are the ones that must be readable whatever else is arriving, then
// the rotating rows newest first. Pointers rather than copies, since the drawing
// runs every frame and the state outlives it.
inline std::vector<const ToastRow*> ToastDrawOrder(const ToastStackState& state) {
  std::vector<const ToastRow*> rows;
  rows.reserve(kToastNoticeCount + state.visible.size());
  for (const ToastRow& notice : state.notices) {
    if (!notice.empty()) rows.push_back(&notice);
  }
  for (std::size_t index = state.visible.size(); index > 0; --index) {
    rows.push_back(&state.visible[index - 1].row);
  }
  return rows;
}

// The role a colour name on the wire means. The client sends names and the mod
// owns the table, so a colour that reads badly in game is one edit here. An
// unknown name is a connective, which draws readably rather than not at all.
inline ToastRole ToastRoleFromName(const std::string& name) {
  if (name == "own_slot") return ToastRole::kOwnSlot;
  if (name == "other_slot") return ToastRole::kOtherSlot;
  if (name == "progression") return ToastRole::kProgression;
  if (name == "useful") return ToastRole::kUseful;
  if (name == "trap") return ToastRole::kTrap;
  if (name == "filler") return ToastRole::kFiller;
  if (name == "location") return ToastRole::kLocation;
  return ToastRole::kConnective;
}

// The role name that breaks a row onto its next line. It carries no text, so it
// is a layout marker rather than a segment, and the row builder below turns it
// into one.
constexpr const char* kToastNewlineName = "newline";

// The optional file that tunes where the stack draws, parsed here rather than
// beside the reading so the console self-test can drive every case: the bounds,
// the malformed lines, the comment forms and the values a hand edit can produce.
// Only opening the file needs anything the game has.
//
// The section keeps the file open to other sections a later change may want
// without this one having to know about them.
constexpr const char* kToastSettingsSection = "[toasts]";

// The bounds a hand-edited value is held to. A stack drawn off the screen would
// take the handshake refusal with it, so the file may move the stack but not lose
// it.
constexpr float kToastMinScale = 0.2f;
constexpr float kToastMaxScale = 2.0f;
constexpr float kToastMinLineHeight = 6.0f;
constexpr float kToastMinWidth = 60.0f;
constexpr unsigned int kToastMinLifetimeMs = 500;
constexpr unsigned int kToastMaxLifetimeMs = 60000;

inline float ClampToastValue(float value, float low, float high) {
  return value < low ? low : (value > high ? high : value);
}

inline void TrimToastText(std::string& text) {
  const std::size_t first = text.find_first_not_of(" \t\r\n");
  if (first == std::string::npos) {
    text.clear();
    return;
  }
  const std::size_t last = text.find_last_not_of(" \t\r\n");
  text = text.substr(first, last - first + 1);
}

// One `key = value` line, or nothing. Whitespace either side of both is dropped
// and anything from a semicolon or a hash onward is a comment, which is what an
// ini file means by those in every reader a player is likely to have seen.
inline bool ParseToastSetting(const std::string& raw, std::string& key,
                              std::string& value) {
  std::string line = raw;
  const std::size_t comment = line.find_first_of(";#");
  if (comment != std::string::npos) line.erase(comment);
  const std::size_t equals = line.find('=');
  if (equals == std::string::npos) return false;
  key = line.substr(0, equals);
  value = line.substr(equals + 1);
  TrimToastText(key);
  TrimToastText(value);
  return !key.empty() && !value.empty();
}

// A value only where the whole of it is a finite number. A parse that stopped
// early means the line is not the number the file meant, so the default is kept
// rather than a prefix taken: "3 4" and "wide" both leave the setting alone.
//
// The finiteness test is not decoration. Every comparison against a NaN is false,
// so a NaN would pass every bound below unchanged, and a NaN band then makes the
// line count a cast from a NaN, which is undefined and in practice enormous: the
// whole queue admitted at once onto a stack whose ceiling test can never be true.
inline bool ParseToastFloat(const std::string& text, float& out) {
  char* end = nullptr;
  const double parsed = std::strtod(text.c_str(), &end);
  if (end == nullptr || *end != 0) return false;
  // Its own negation, which only a NaN is.
  if (!(parsed == parsed)) return false;
  if (parsed > 1e30 || parsed < -1e30) return false;
  out = static_cast<float>(parsed);
  return true;
}

inline bool ParseToastUnsigned(const std::string& text, unsigned int& out) {
  float parsed = 0.0f;
  if (!ParseToastFloat(text, parsed)) return false;
  if (parsed < 0.0f) return false;
  out = static_cast<unsigned int>(parsed);
  return true;
}

// Everything the file may say, applied over the defaults it was handed.
inline void ApplyToastSetting(ToastGeometry& geometry, const std::string& key,
                              const std::string& value) {
  float number = 0.0f;
  if (key == "anchor_x" && ParseToastFloat(value, number)) {
    geometry.anchor_x = number;
  } else if (key == "anchor_y" && ParseToastFloat(value, number)) {
    geometry.anchor_y = number;
  } else if (key == "width" && ParseToastFloat(value, number)) {
    geometry.width = number;
  } else if (key == "ceiling_y" && ParseToastFloat(value, number)) {
    geometry.ceiling_y = number;
  } else if (key == "line_height" && ParseToastFloat(value, number)) {
    geometry.line_height = number;
  } else if (key == "scale_x" && ParseToastFloat(value, number)) {
    geometry.scale_x = number;
  } else if (key == "scale_y" && ParseToastFloat(value, number)) {
    geometry.scale_y = number;
  } else if (key == "continuation_indent" && ParseToastFloat(value, number)) {
    geometry.continuation_indent = number;
  } else {
    unsigned int milliseconds = 0;
    if (key == "lifetime_ms" && ParseToastUnsigned(value, milliseconds)) {
      geometry.lifetime_ms = milliseconds;
    }
  }
}

// The read geometry held to something drawable. The anchor and the ceiling are
// ordered rather than each clamped alone, so a file that swapped them draws a
// band of one line at the anchor instead of an inverted one.
inline ToastGeometry BoundToastGeometry(ToastGeometry geometry) {
  geometry.anchor_x = ClampToastValue(geometry.anchor_x, 0.0f,
                                     kVirtualScreenWidth - kToastMinWidth);
  geometry.anchor_y =
      ClampToastValue(geometry.anchor_y, 0.0f, kVirtualScreenHeight - 1.0f);
  geometry.ceiling_y = ClampToastValue(geometry.ceiling_y, 0.0f, geometry.anchor_y);
  geometry.width = ClampToastValue(geometry.width, kToastMinWidth,
                                   kVirtualScreenWidth - geometry.anchor_x);
  geometry.line_height = ClampToastValue(geometry.line_height, kToastMinLineHeight,
                                         kVirtualScreenHeight);
  geometry.scale_x =
      ClampToastValue(geometry.scale_x, kToastMinScale, kToastMaxScale);
  geometry.scale_y =
      ClampToastValue(geometry.scale_y, kToastMinScale, kToastMaxScale);
  geometry.continuation_indent =
      ClampToastValue(geometry.continuation_indent, 0.0f, geometry.width / 2.0f);
  if (geometry.lifetime_ms < kToastMinLifetimeMs) {
    geometry.lifetime_ms = kToastMinLifetimeMs;
  }
  if (geometry.lifetime_ms > kToastMaxLifetimeMs) {
    geometry.lifetime_ms = kToastMaxLifetimeMs;
  }
  return geometry;
}

// The settings file a module reads: its own path with the extension replaced, so
// `GtaVcAp.VC.asi` reads `GtaVcAp.VC.ini`. Derived rather than named, so the two
// cannot drift if the build renames its output, and it is the convention the other
// ASIs in a Vice City folder already follow.
//
// A path whose last component carries no dot gets the extension appended rather
// than nothing, and a dot in a DIRECTORY name is not an extension, so the result is
// always a file beside the module. Pure string work, here rather than beside the
// module handle so the console self-test can drive both of those cases.
inline std::string SettingsPathForModule(const std::string& module_path) {
  if (module_path.empty()) return std::string();
  std::string path = module_path;
  const std::size_t separator = path.find_last_of("\\/");
  const std::size_t dot = path.find_last_of('.');
  if (dot != std::string::npos &&
      (separator == std::string::npos || dot > separator)) {
    path.erase(dot);
  }
  return path + ".ini";
}

// A whole file, as its lines. Settings outside the stack's own section are
// ignored, so another section cannot reach these keys by accident.
inline ToastGeometry ParseToastGeometry(const std::vector<std::string>& lines) {
  ToastGeometry geometry;
  bool in_section = false;
  for (const std::string& raw : lines) {
    std::string trimmed = raw;
    TrimToastText(trimmed);
    if (trimmed.empty()) continue;
    if (trimmed.front() == '[') {
      in_section = trimmed == kToastSettingsSection;
      continue;
    }
    if (!in_section) continue;
    std::string key;
    std::string value;
    if (ParseToastSetting(trimmed, key, value)) {
      ApplyToastSetting(geometry, key, value);
    }
  }
  return BoundToastGeometry(geometry);
}

// A flat wire segment list built into a row, splitting on the newline marker.
// Bounded on both counts: a row past kToastMaxSegments stops taking segments and
// one past kToastMaxLines stops taking lines, so a malformed frame costs a
// truncated row rather than the band.
//
// Empty lines are dropped rather than kept, so a trailing or doubled newline
// marker does not spend a line of the band on nothing.
inline ToastRow BuildToastRow(
    const std::vector<std::pair<std::string, std::string>>& segments) {
  ToastRow row;
  std::vector<ToastSegment> line;
  std::size_t taken = 0;
  const auto flush = [&row, &line]() {
    if (line.empty()) return;
    if (row.lines.size() < kToastMaxLines) row.lines.push_back(line);
    line.clear();
  };
  for (const auto& [text, color] : segments) {
    if (color == kToastNewlineName) {
      flush();
      continue;
    }
    if (text.empty()) continue;
    if (taken >= kToastMaxSegments) break;
    ++taken;
    line.push_back({text, ToastRoleFromName(color)});
  }
  flush();
  return row;
}

}  // namespace gtavc
