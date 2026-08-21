#include "status_page.hpp"

#include <cstddef>
#include <cstring>
#include <utility>

#include "game_addresses.hpp"

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
// pause menu, and its back entry stands high enough to stay clear of the panel.
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

// The virtual screen the frontend lays out in, which the game stretches to
// whatever resolution is running. The menu table's own positions are in these
// units, so the panel's are too.
constexpr float kVirtualWidth = 640.0f;
constexpr float kVirtualHeight = 448.0f;
// The band the cover leaves alone: the borrowed page's back entry stands at y 320
// and stays the game's own, visible and highlighted and clickable. Everything
// above and below that band is covered, so a brief line long enough to reach
// under the panel cannot show either.
constexpr float kCoverBottom = 310.0f;
constexpr float kBackEntryBottom = 342.0f;

// Where the panel draws, in those units. Two columns: a label starts at the
// column's left edge and its value ends at the column's right edge, and a value
// that would reach the label is moved right of it, so the two can never overlap
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
    18.0f, 156.0f, 146.0f, 84.0f, 13.0f, 0.38f, 0.64f,
};

// The row height the panel draws at: the geometry's own, or as much less as it
// takes for the taller column to fit above the cover's bottom. Every seed's page
// therefore fits whole, and only a seed that configured everything is drawn
// tighter than the rest.
float FittedRowHeight(int tallest_column_rows) {
  const float available = kCoverBottom - kGeometry.top_y;
  if (tallest_column_rows <= 0) return kGeometry.row_height;
  const float fitted = available / static_cast<float>(tallest_column_rows);
  return fitted < kGeometry.row_height ? fitted : kGeometry.row_height;
}

// What the text scales by when the rows had to be drawn tighter than the design.
// A glyph is taller than its row's share of the screen otherwise: the seed that
// fills the page would draw its lines into each other.
float FittedTextScale(float row_height) {
  return row_height < kGeometry.row_height ? row_height / kGeometry.row_height
                                           : 1.0f;
}

float StretchX(float x) {
  return x * static_cast<float>(RsGlobal.maximumWidth) / kVirtualWidth;
}

float StretchY(float y) {
  return y * static_cast<float>(RsGlobal.maximumHeight) / kVirtualHeight;
}

// The text the panel hands the game. CFont takes wide characters and the panel
// composes narrow ones, so each row is widened into storage of the mod's own.
// The font reads the string during the print rather than keeping the pointer
// (unlike the message queue, which is why the toasts own a ring of their own),
// so the ring here is only insurance: one buffer would do, and a ring costs
// nothing.
const wchar_t* Widen(const std::string& text) {
  constexpr std::size_t kBufferChars = 96;
  constexpr std::size_t kBufferCount = 128;
  static wchar_t buffers[kBufferCount][kBufferChars];
  static std::size_t next_buffer = 0;
  wchar_t* buffer = buffers[next_buffer];
  next_buffer = (next_buffer + 1) % kBufferCount;
  const std::size_t length =
      text.size() < kBufferChars - 1 ? text.size() : kBufferChars - 1;
  for (std::size_t index = 0; index < length; ++index) {
    // The tilde opens the game's own formatting token, which the font expands in
    // place. Route labels and the seed hash are the panel's only text from
    // outside the mod, and neither is worth trusting to stay tilde-free.
    const unsigned char character = static_cast<unsigned char>(text[index]);
    buffer[index] = character == '~' ? L' ' : static_cast<wchar_t>(character);
  }
  buffer[length] = 0;
  return buffer;
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

// One column of lines, from its own top downward. A line with no label is a
// wrapped line, drawn from the column's own left edge across its whole width,
// which is what lets a list of names read as a sentence instead of taking a line
// each; a line with both is a label and a value, the value ending at the column's
// right edge unless the pair is wide enough to meet, in which case the value
// starts just right of the label.
void DrawColumn(const std::vector<PanelLine>& lines, float column_x,
                float row_height, int alpha) {
  float y = kGeometry.top_y;
  const float scale = FittedTextScale(row_height);
  const float left = StretchX(column_x);
  const float right_edge = StretchX(column_x + kGeometry.column_width);
  // A line too long for its column folds inside the column rather than running
  // across the gutter into the next one.
  CFont::SetWrapx(right_edge);
  for (const PanelLine& line : lines) {
    if (y > kCoverBottom) return;
    if (line.blank) {
      y += row_height;
      continue;
    }
    if (line.heading) {
      CFont::SetFontStyle(FONT_HEADING);
      CFont::SetScale(StretchX(kGeometry.scale_x * scale * 0.9f),
                      StretchY(kGeometry.scale_y * scale * 0.9f));
      CFont::SetColor(HeadingColor(alpha));
      CFont::PrintString(left, StretchY(y), Widen(line.label));
      y += row_height;
      continue;
    }
    CFont::SetFontStyle(FONT_STANDARD);
    CFont::SetScale(StretchX(kGeometry.scale_x * scale),
                    StretchY(kGeometry.scale_y * scale));
    if (line.label.empty()) {
      CFont::SetColor(ToneColor(line.tone, alpha));
      CFont::PrintString(left, StretchY(y), Widen(line.value));
      y += row_height;
      continue;
    }
    const wchar_t* label = Widen(line.label);
    CFont::SetColor(LabelColor(alpha));
    CFont::PrintString(left, StretchY(y), label);
    if (!line.value.empty()) {
      const wchar_t* value = Widen(line.value);
      const float label_end = left + CFont::GetStringWidth(label, true);
      const float value_x = right_edge - CFont::GetStringWidth(value, true);
      CFont::SetColor(ToneColor(line.tone, alpha));
      CFont::PrintString(value_x > label_end ? value_x : label_end + StretchX(5.0f),
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
  const std::vector<std::vector<PanelLine>> columns =
      PlanPanelColumns(FlattenPanel(sections), kColumnCount);
  const float row_height = FittedRowHeight(TallestColumn(columns));

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
      CRect(0.0f, 0.0f, StretchX(kVirtualWidth), StretchY(kCoverBottom)), cover);
  CSprite2d::DrawRect(
      CRect(0.0f, StretchY(kBackEntryBottom), StretchX(kVirtualWidth),
            StretchY(kVirtualHeight)),
      cover);

  // Left to right, top to bottom, proportional, no wrapping and no shadow: the
  // panel is a list to read rather than a menu to look at. The menu's own drawing
  // sets every one of these per string, so nothing here has to be put back.
  CFont::SetJustifyOff();
  CFont::SetCentreOff();
  CFont::SetRightJustifyOff();
  CFont::SetBackgroundOff();
  CFont::SetPropOn();
  CFont::SetDropShadowPosition(0);

  CFont::SetFontStyle(FONT_HEADING);
  CFont::SetScale(StretchX(0.7f), StretchY(1.2f));
  CFont::SetColor(HeadingColor(alpha));
  CFont::SetCentreOn();
  CFont::SetCentreSize(StretchX(kVirtualWidth));
  CFont::SetWrapx(StretchX(kVirtualWidth));
  CFont::PrintString(StretchX(kVirtualWidth / 2.0f), StretchY(40.0f),
                     Widen(kPanelTitle));
  CFont::SetCentreOff();

  for (std::size_t column = 0; column < columns.size(); ++column) {
    DrawColumn(columns[column],
               kGeometry.first_column_x +
                   kGeometry.column_pitch * static_cast<float>(column),
               row_height, alpha);
  }

  // The panel's own glyphs are flushed before the pointer, so the pointer is
  // drawn over the panel the way it was drawn over the page: a sprite goes down
  // immediately while text waits in the bank, so without this flush the rows
  // would land on top of the pointer.
  CFont::DrawFonts();
  DrawMousePointer();
}

}  // namespace gtavc
