#include "status_page.hpp"

#include <cstddef>
#include <cstring>
#include <limits>
#include <utility>

#include "game_addresses.hpp"
#include "hud_text.hpp"

#include <plugin.h>
#include <CFont.h>
#include <CMenuManager.h>
#include <CSprite2d.h>
#include <CText.h>
#include <RenderWare.h>

namespace gtavc {
namespace {

// The page the panel borrows. The briefs page is the cheapest one to cover: its
// content is the last few mission brief lines, it keeps its own entry on the
// pause menu, and it carries one entry of its own, a back row the panel can stand
// at the foot of the screen and leave showing there.
constexpr int kPanelHostPage = MENUPAGE_BRIEFS;
// The pause page entry the panel takes. Quit Game holds it in a vanilla game and
// moves one down, which is why the entry after it must be free.
constexpr int kPanelPauseEntry = 6;
// The GXT key of the panel's entry label. A key is eight bytes and no more, so
// the name is shortened; the installer adds it to every text table it finds.
constexpr char kPanelTextKey[] = "APSTAT";
// The key the vanilla Quit Game entry carries, which is how the pause page is
// recognized as untouched before anything is written to it.
constexpr char kQuitEntryKey[] = "FEP_QUI";
// The heading the panel draws over the borrowed page's own title.
constexpr char kPanelTitle[] = "ARCHIPELAGO";

// The borrowed page's own back entry: the row it is, the key it carries, and
// where the vanilla table stands it up. The panel covers the page above that
// entry and below it, so the further down the entry stands the more of the page
// the rows have, and the entry is lowered to the foot of the screen for exactly
// that. Everything else about it stays the game's own: its action, its input, its
// label, and the menu's own hit test, which reads the position this moves.
constexpr int kBackEntry = 0;
constexpr char kBackEntryKey[] = "FEDS_TB";
constexpr unsigned short kBackEntryVanillaX = 190;
constexpr unsigned short kBackEntryVanillaY = 320;
constexpr unsigned short kBackEntryLoweredY = 406;
// What the entry's own highlight bar covers, either side of the entry's position.
// The bar is the one thing on the borrowed page the panel leaves showing, so the
// cover stops above it and starts again below it. Measured off the drawn page at
// ten units above and twenty-two below, and taken a unit tighter than that in both
// directions so the cover LAPS the bar's own edges rather than meeting them: a
// flat grey bar loses nothing to a unit of cover, where a unit of daylight between
// the two would show the page underneath.
constexpr float kHighlightBarAbove = 9.0f;
constexpr float kHighlightBarBelow = 21.0f;

// Where the panel draws, in those units. A row is a label at the column's left
// edge and a value ending just short of its right edge, and a pair too wide to
// share a row is split before the page is laid out, so the two can never meet
// however long either gets.
struct PanelGeometry {
  float first_column_x;
  float column_pitch;
  float column_width;
  float top_y;
  // The most a row may take. A page with more rows than the cover has room for
  // is drawn tighter rather than cut off.
  float row_height;
  float scale_x;
  float scale_y;
};

// Four columns. A seed with every block filled runs to some eighty lines, and the
// row height comes from the tallest column, so fewer columns would shrink the
// whole page to fit the busiest seed rather than only its own lines.
constexpr int kColumnCount = 4;
constexpr PanelGeometry kGeometry = {
    18.0f, 156.0f, 146.0f, 60.0f, 13.0f, 0.38f, 0.64f,
};
// Where the page's own title sits, above the first row.
constexpr float kTitleY = 28.0f;
// The gap between a label and the value that shares its row, and how far short of
// the column's right edge a value stops. The inset is what keeps a value off the
// wrap edge: a value right-justified onto the edge itself REACHES it, and the font
// answers by folding the value's last word onto the row below.
constexpr float kLabelGap = 5.0f;
constexpr float kValueInset = 2.0f;
// What a heading draws at, against the rows around it.
constexpr float kHeadingScale = 0.9f;
// What a RECENT row draws at. Smaller than the page's own rows on purpose: the
// block is a history to glance over rather than state to read, its lines are the
// longest on the page (a sentence and a location), and at the body size nearly
// every one of them was cut. Smaller text fits more of a location, so the rows say
// more while taking less of the eye.
constexpr float kRecentScale = 0.78f;

// The relations the one-line-per-row guarantee rests on. A line narrowed to its
// column stops short of the wrap edge a gutter further out, and the inset pulls a
// value further inside that again; the last column ends inside the screen, so
// nothing it draws is clipped away; and the entry, wherever it is allowed to stand,
// leaves room for the rows above it and for its own bar below. Asserted here
// because this is where the numbers are, and the console self-test cannot compile
// this file.
static_assert(kGeometry.column_width < kGeometry.column_pitch,
              "a line narrowed to its column must stop short of the wrap edge");
static_assert(kGeometry.first_column_x +
                      kGeometry.column_pitch * (kColumnCount - 1) +
                      kGeometry.column_width <= kVirtualWidth,
              "the last column must end inside the screen");
static_assert(kBackEntryLoweredY - kHighlightBarAbove >
                  kGeometry.top_y + kGeometry.row_height,
              "the lowered entry must leave the rows a band to draw in");
static_assert(kBackEntryVanillaY - kHighlightBarAbove >
                  kGeometry.top_y + kGeometry.row_height,
              "and so must the place the panel falls back on");
static_assert(kBackEntryLoweredY + kHighlightBarBelow <= kVirtualHeight,
              "the lowered entry's own highlight bar must end inside the screen");

// How wide a line draws at the page's design text size, which is what the
// fitting measures against. The size is the design's own rather than the fitted
// one, so the answer does not depend on the fitting it feeds; the fitted size is
// only ever smaller, so a line that fits here fits when it is drawn. The face and
// the size are set here rather than by the caller, because a width measured under
// another face is a wrong answer that looks like a right one.
float DesignTextWidth(const std::string& text) {
  // Past the widening bound the answer would be the width of the string's front
  // rather than of the string, so it is refused instead: the fitting then breaks
  // or cuts until it is asking about something it can measure whole.
  if (text.size() > kWidenMaxChars) return std::numeric_limits<float>::max();
  CFont::SetFontStyle(FONT_STANDARD);
  CFont::SetScale(StretchX(kGeometry.scale_x), StretchY(kGeometry.scale_y));
  return CFont::GetStringWidth(Widen(text), true);
}

// The same, for a RECENT row, which draws smaller than the rows around it. Its own
// measure because the fitting has to ask about the size the line really draws at:
// measured at the body size, a line that fits would be cut short of the column and
// one that does not would be cut when it need not have been.
float DesignRecentWidth(const std::string& text) {
  if (text.size() > kWidenMaxChars) return std::numeric_limits<float>::max();
  CFont::SetFontStyle(FONT_STANDARD);
  CFont::SetScale(StretchX(kGeometry.scale_x * kRecentScale),
                  StretchY(kGeometry.scale_y * kRecentScale));
  return CFont::GetStringWidth(Widen(text), true);
}

// The same, for the face a heading draws in. A heading is short, but the page draws
// larger the taller its band is, so the one line the fitting could not measure
// would be the one line left free to fold.
float DesignHeadingWidth(const std::string& text) {
  if (text.size() > kWidenMaxChars) return std::numeric_limits<float>::max();
  CFont::SetFontStyle(FONT_HEADING);
  CFont::SetScale(StretchX(kGeometry.scale_x * kHeadingScale),
                  StretchY(kGeometry.scale_y * kHeadingScale));
  return CFont::GetStringWidth(Widen(text), true);
}

CRGBA HeadingColor(int alpha) {
  return CRGBA(255, 205, 90, static_cast<unsigned char>(alpha));
}

CRGBA LabelColor(int alpha) {
  return CRGBA(225, 225, 225, static_cast<unsigned char>(alpha));
}

CRGBA ToneColor(StatusTone tone, int alpha) {
  switch (tone) {
    case StatusTone::kHeld:
      return CRGBA(214, 96, 72, static_cast<unsigned char>(alpha));
    case StatusTone::kOpen:
      return CRGBA(122, 199, 130, static_cast<unsigned char>(alpha));
    case StatusTone::kPlain:
    default:
      return LabelColor(alpha);
  }
}

// One column of lines, from its own top downward, one row a line. A line with no
// label is a wrapped line, drawn from the column's own left edge across its whole
// width, which is what lets a list of names read as a sentence instead of taking a
// line each; a line with both is a label and a value, the value ending just short
// of the column's right edge. A pair too wide to share a row never reaches here,
// since the fitting split it before the columns were dealt, which is what lets one
// line take exactly one row.
void DrawColumn(const std::vector<PanelLine>& lines, float column_x,
                float row_height, float bottom, int alpha) {
  float y = kGeometry.top_y;
  const float scale = FittedTextScale(row_height, kGeometry.row_height);
  const float left = StretchX(column_x);
  const float right_edge = StretchX(column_x + kGeometry.column_width);
  const float inset = StretchX(kValueInset);
  // The net under the fitting, which has already narrowed every line to its own
  // column: a gutter's worth of slack past that column, so it catches nothing the
  // fitting accepted and still holds a line to one column where a measured width
  // and the font disagree. The last column stops at the screen instead. A word
  // wider than the whole column reaches neither: the font has nowhere to fold it,
  // so it draws across the gutter, which is the one thing here that is meant to
  // overrun.
  const float wrap_at = column_x + kGeometry.column_pitch;
  CFont::SetWrapx(StretchX(wrap_at < kVirtualWidth ? wrap_at : kVirtualWidth));
  for (const PanelLine& line : lines) {
    if (y > bottom) return;
    if (line.blank) {
      y += row_height;
      continue;
    }
    if (line.heading) {
      CFont::SetFontStyle(FONT_HEADING);
      CFont::SetScale(StretchX(kGeometry.scale_x * scale * kHeadingScale),
                      StretchY(kGeometry.scale_y * scale * kHeadingScale));
      CFont::SetColor(HeadingColor(alpha));
      CFont::PrintString(left, StretchY(y), Widen(line.label));
      y += row_height;
      continue;
    }
    CFont::SetFontStyle(FONT_STANDARD);
    CFont::SetScale(StretchX(kGeometry.scale_x * scale),
                    StretchY(kGeometry.scale_y * scale));
    // A recent row: its own colours, printed one segment after another from the
    // column's left edge. Each segment advances by its own measured width, which
    // is exact for that segment; the width of the whole LINE is never summed from
    // these, since summing per-segment widths drifts. The fitting already cut this
    // line to the column, so nothing here can reach the wrap edge.
    if (!line.segments.empty()) {
      CFont::SetScale(StretchX(kGeometry.scale_x * scale * kRecentScale),
                      StretchY(kGeometry.scale_y * scale * kRecentScale));
      float x = left;
      for (const ToastSegment& segment : line.segments) {
        if (segment.text.empty()) continue;
        const wchar_t* text = Widen(segment.text);
        // Measured before it is printed. CFont::PrintString overwrites a trailing
        // space in the buffer it is handed with a terminator (0x551381), so
        // printing first shortens the string the advance then measures and every
        // segment ending in a space loses it.
        const float advance = CFont::GetStringWidth(text, true);
        CFont::SetColor(ToastRoleColor(segment.role, alpha));
        CFont::PrintString(x, StretchY(y), text);
        x += advance;
      }
      y += row_height;
      // Back to the page's own size for whatever follows in this column.
      CFont::SetScale(StretchX(kGeometry.scale_x * scale),
                      StretchY(kGeometry.scale_y * scale));
      continue;
    }
    if (line.label.empty()) {
      CFont::SetColor(ToneColor(line.tone, alpha));
      const wchar_t* value = Widen(line.value);
      // A value the fitting moved off its label's row keeps the place it would
      // have had beside it, against the column's right edge. One wider than the
      // whole column starts at the left edge instead, so its front is readable
      // rather than its tail.
      float x = left;
      if (line.value_alone) {
        const float value_x =
            right_edge - inset - CFont::GetStringWidth(value, true);
        x = value_x > left ? value_x : left;
      }
      CFont::PrintString(x, StretchY(y), value);
      y += row_height;
      continue;
    }
    const wchar_t* label = Widen(line.label);
    CFont::SetColor(LabelColor(alpha));
    CFont::PrintString(left, StretchY(y), label);
    if (!line.value.empty()) {
      const wchar_t* value = Widen(line.value);
      const float label_end = left + CFont::GetStringWidth(label, true);
      const float value_x = right_edge - inset - CFont::GetStringWidth(value, true);
      // The fitting accepted this pair, so the value's own place is clear of the
      // label; the clamp only ever holds where a measured width and the font
      // disagree by more than the gap.
      CFont::SetColor(ToneColor(line.tone, alpha));
      CFont::PrintString(
          value_x > label_end ? value_x : label_end + StretchX(kLabelGap),
          StretchY(y), value);
    }
    y += row_height;
  }
}

// The frontend's own mouse pointer, put back on top of the cover. The page draw
// lays the pointer down before this hook runs, so the cover hides it; the sprite
// and its size are the menu's own (45 by 38 of the frontend's units, from the
// pointer draw at 0x4A359B), and it draws opaque as the menu draws it, so what
// comes back is the same pointer in the same place rather than something of the
// mod's own. A sprite with no texture would draw as a white block, so a pointer
// the menu has not loaded is left alone.
void DrawMousePointer() {
  if (!FrontEndMenuManager.m_bShowMouse) return;
  if (!FrontEndMenuManager.m_bSpritesLoaded) return;
  const float x = static_cast<float>(FrontEndMenuManager.m_nMousePosX);
  const float y = static_cast<float>(FrontEndMenuManager.m_nMousePosY);
  FrontEndMenuManager.m_aMenuSprites[MENUSPRITE_MOUSE].Draw(
      CRect(x, y, x + StretchX(45.0f), y + StretchY(38.0f)),
      CRGBA(255, 255, 255, 255));
}

}  // namespace

StatusPage::StatusPage(Logger logger) : logger_(std::move(logger)) {}

void StatusPage::Install() {
  if (installed_) return;
  installed_ = true;
  if (plugin::GetGameVersion() != GAME_10EN) {
    // Unreachable in practice: the menu draw event this runs from is pinned to
    // the classic 1.0 executable, so a foreign build never calls it. Checked
    // anyway, because the writes below mean nothing on another build.
    if (logger_) {
      logger_("status page: not the classic 1.0 executable, so there is no entry");
    }
    return;
  }
  const wchar_t* label = TheText.Get(kPanelTextKey);
  // A key the text table does not carry returns the game's own placeholder
  // buffer, which holds an empty string in this build, so the entry would draw as
  // a blank row. The entry still goes in: it works, it just reads as nothing
  // until the installer patches the table.
  const bool text_resolves =
      label != nullptr && label[0] != 0 &&
      label != reinterpret_cast<const wchar_t*>(kMissingTextBuffer10);
  if (!text_resolves && logger_) {
    logger_("status page: the text table carries no panel label, so the entry "
            "reads as a blank row");
  }
  owns_entry_ = ClaimEntry();
  if (logger_) {
    logger_(owns_entry_
                ? "status page: the pause menu carries an Archipelago entry"
                : "status page: the pause menu is not the one this build knows, "
                  "so no entry was added");
  }
  // Only worth doing where the panel can be reached: without the entry the
  // borrowed page is never anything but its own, and lowering its back row would
  // move a vanilla page's own button for nothing.
  if (!owns_entry_) return;
  const bool lowered = LowerBackEntry();
  if (logger_) {
    logger_(lowered ? "status page: the borrowed page's back entry stands at the "
                      "foot of the panel"
                    : "status page: the borrowed page's back entry is not where "
                      "this build puts it, so the panel keeps the shorter band");
  }
}

bool StatusPage::LowerBackEntry() {
  CMenuScreen::CMenuEntry& back =
      aScreens[kPanelHostPage].m_aEntries[kBackEntry];
  // The entry must be the one the game built, standing where the vanilla table
  // stands it. Anything else is another mod's table or this move already made,
  // and neither is ours to write over.
  const bool entry_is_vanilla =
      std::strncmp(back.m_EntryName, kBackEntryKey,
                   sizeof(back.m_EntryName)) == 0 &&
      back.m_nX == kBackEntryVanillaX && back.m_nY == kBackEntryVanillaY;
  if (!entry_is_vanilla) return false;
  // A position the table already carries is left alone by the draw, which only
  // fills in a zero one, so this write stands for the session.
  back.m_nY = kBackEntryLoweredY;
  return true;
}

float StatusPage::BackEntryY() const {
  // Read from the table rather than remembered, so the cover follows the entry
  // wherever it actually stands: a cover that believes it was moved and an entry
  // that was not would hide the back button and show a strip of the page.
  //
  // A position with no band above it is not one to lay a page out against, since
  // the row height comes out of that band and a band of nothing is a row height of
  // nothing. So a position the panel cannot use falls back on the place the vanilla
  // table puts this entry, which the assertions above hold to a band the rows fit
  // in. That covers a position of zero and a foreign one alike, and the panel then
  // draws where it always did rather than not at all.
  const float written =
      static_cast<float>(aScreens[kPanelHostPage].m_aEntries[kBackEntry].m_nY);
  const bool leaves_a_band =
      written - kHighlightBarAbove > kGeometry.top_y + kGeometry.row_height &&
      written + kHighlightBarBelow <= kVirtualHeight;
  return leaves_a_band ? written : static_cast<float>(kBackEntryVanillaY);
}

float StatusPage::CoverBottom() const {
  return BackEntryY() - kHighlightBarAbove;
}

float StatusPage::HighlightBarBottom() const {
  return BackEntryY() + kHighlightBarBelow;
}

bool StatusPage::ClaimEntry() {
  CMenuScreen& pause = aScreens[MENUPAGE_PAUSE_MENU];
  CMenuScreen::CMenuEntry& quit = pause.m_aEntries[kPanelPauseEntry];
  // The pause page must be the one the game built: Quit Game where the vanilla
  // table puts it, the slot below it free, and the page Quit Game opens still
  // pointing back at that entry. Anything else is another mod's table, or this
  // entry already added, and neither is ours to rewrite.
  const bool pause_is_vanilla =
      std::strncmp(quit.m_EntryName, kQuitEntryKey, sizeof(quit.m_EntryName)) == 0 &&
      quit.m_nTargetMenu == MENUPAGE_EXIT &&
      pause.m_aEntries[kPanelPauseEntry + 1].m_EntryName[0] == 0 &&
      aScreens[MENUPAGE_EXIT].m_nParentEntry == kPanelPauseEntry;
  if (!pause_is_vanilla) return false;

  // Quit Game moves down and the panel's entry takes its place, so the panel
  // reads above Quit Game rather than below it. The entry is a copy of the one
  // it displaces, so its action and its alignment are the game's own rather than
  // constants named here; only the label and the page it opens are the panel's.
  pause.m_aEntries[kPanelPauseEntry + 1] = quit;
  std::memset(quit.m_EntryName, 0, sizeof(quit.m_EntryName));
  std::memcpy(quit.m_EntryName, kPanelTextKey, sizeof(kPanelTextKey) - 1);
  quit.m_nTargetMenu = static_cast<char>(kPanelHostPage);
  // The page Quit Game opens highlights the entry that opened it, which is one
  // further down now.
  aScreens[MENUPAGE_EXIT].m_nParentEntry = kPanelPauseEntry + 1;
  // The game derives an entry position of zero from the entry above it and writes
  // the answer back into the table, so a position already written this session
  // would leave Quit Game standing where the panel entry now is. Zeroing every
  // entry below the first hands all of them back to the game.
  for (int index = 1; index < NUM_ENTRIES; ++index) {
    pause.m_aEntries[index].m_nX = 0;
    pause.m_aEntries[index].m_nY = 0;
  }
  return true;
}

PanelMenuState StatusPage::ReadMenu() const {
  PanelMenuState state;
  state.owns_entry = owns_entry_;
  state.game_loaded = !FrontEndMenuManager.m_bGameNotLoaded;
  state.page = FrontEndMenuManager.m_nCurrentMenuPage;
  state.highlighted_entry = FrontEndMenuManager.m_nCurrentMenuEntry;
  state.pause_page = MENUPAGE_PAUSE_MENU;
  state.host_page = kPanelHostPage;
  state.panel_entry = kPanelPauseEntry;
  // A row outside the page's own table is no row at all, so it reads as none:
  // the decision then arms nothing and writes nothing, and no value that could
  // index past the entries ever leaves this function.
  const int entry = state.highlighted_entry;
  if (entry < 0 || entry >= NUM_ENTRIES) {
    state.highlighted_entry = -1;
    return state;
  }
  if (state.page == MENUPAGE_PAUSE_MENU) {
    state.highlighted_entry_targets_host =
        aScreens[MENUPAGE_PAUSE_MENU].m_aEntries[entry].m_nTargetMenu ==
        kPanelHostPage;
  }
  return state;
}

PanelFrame StatusPage::Follow() {
  // The row the player stands on decides what the borrowed page shows when they
  // open it, and where going back puts them. That page's parent entry is the
  // game's own "highlight this row on the way back", so writing the row they came
  // from into it is what the field is for.
  const PanelFrame frame = PlanPanelFrame(ReadMenu(), armed_);
  armed_ = frame.armed;
  if (frame.parent_entry >= 0) {
    aScreens[kPanelHostPage].m_nParentEntry =
        static_cast<char>(frame.parent_entry);
  }
  return frame;
}

void StatusPage::Draw(const std::vector<StatusSection>& sections) const {
  const int alpha = FrontEndMenuManager.FadeIn(255);
  const float cover_bottom = CoverBottom();

  // The borrowed page's own title and brief lines go under an opaque cover before
  // any of the panel goes on top. The font banks its glyphs and the game flushes
  // that bank after this hook returns, so the page's text is flushed here first:
  // a glyph still in the bank would otherwise land on top of the cover, at full
  // strength, however opaque the cover is. Two rects, above and below the
  // borrowed page's back entry, so that entry stays the game's own and nothing
  // else of the page shows anywhere.
  CFont::DrawFonts();
  const CRGBA cover(6, 8, 24, static_cast<unsigned char>(alpha));
  CSprite2d::DrawRect(
      CRect(0.0f, 0.0f, StretchX(kVirtualWidth), StretchY(cover_bottom)), cover);
  CSprite2d::DrawRect(
      CRect(0.0f, StretchY(HighlightBarBottom()), StretchX(kVirtualWidth),
            StretchY(kVirtualHeight)),
      cover);

  // Left to right, top to bottom, proportional, no wrapping and no shadow: the
  // panel is a list to read rather than a menu to look at. The menu's own drawing
  // sets every one of these per string, so nothing here has to be put back. These
  // go in before anything is measured, since a width read under another set of
  // them is a wrong answer that looks like a right one.
  CFont::SetJustifyOff();
  CFont::SetCentreOff();
  CFont::SetRightJustifyOff();
  CFont::SetBackgroundOff();
  CFont::SetPropOn();
  CFont::SetDropShadowPosition(0);

  // Every line narrowed to its column first, so the columns are dealt and the row
  // height fitted against the rows the page really draws rather than the rows it
  // was composed of.
  const std::vector<std::vector<PanelLine>> columns = PlanPanelColumns(
      FitPanelLines(FlattenPanel(sections), StretchX(kGeometry.column_width),
                    StretchX(kLabelGap), DesignTextWidth, DesignHeadingWidth,
                    DesignRecentWidth),
      kColumnCount);
  const float row_height = FittedRowHeight(
      TallestColumn(columns), cover_bottom - kGeometry.top_y, kGeometry.row_height);

  CFont::SetFontStyle(FONT_HEADING);
  CFont::SetScale(StretchX(0.7f), StretchY(1.2f));
  CFont::SetColor(HeadingColor(alpha));
  CFont::SetCentreOn();
  CFont::SetCentreSize(StretchX(kVirtualWidth));
  CFont::SetWrapx(StretchX(kVirtualWidth));
  CFont::PrintString(StretchX(kVirtualWidth / 2.0f), StretchY(kTitleY),
                     Widen(kPanelTitle));
  CFont::SetCentreOff();

  for (std::size_t column = 0; column < columns.size(); ++column) {
    DrawColumn(columns[column],
               kGeometry.first_column_x +
                   kGeometry.column_pitch * static_cast<float>(column),
               row_height, cover_bottom, alpha);
  }

  // The panel's own glyphs are flushed before the pointer, so the pointer is
  // drawn over the panel the way it was drawn over the page: a sprite goes down
  // immediately while text waits in the bank, so without this flush the rows
  // would land on top of the pointer.
  CFont::DrawFonts();
  DrawMousePointer();
}

}  // namespace gtavc
