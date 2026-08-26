#include "toast_stack.hpp"

#include <algorithm>
#include <cstddef>
#include <fstream>
#include <limits>
#include <string>
#include <vector>

#include "hud_text.hpp"

#include <CHud.h>
#include <CRect.h>

#include <windows.h>

namespace gtavc {
namespace {

// How wide a string draws in the stack's own face and scale. A plain function
// because the fitting takes one, which is also what lets the console self-test
// hand in a measure of its own; the face, the scale and the proportional flag are
// the caller's, set once before anything is measured or printed and not touched
// again, since a width read under another set of them is a wrong answer that
// looks like a right one.
float MeasureToastLine(const std::string& text) {
  // A string past the widening bound would measure only its front, which is a
  // width the line does not have, and the fitting would then accept a line it
  // never measured whole. Reported as unbounded instead, so the fitting keeps
  // trimming until it is measuring the whole thing.
  if (text.size() > kWidenMaxChars) return std::numeric_limits<float>::max();
  return CFont::GetStringWidth(Widen(text), true);
}

// The vanilla help box, read out of the executable. The box is the one thing that
// shares the top left corner with the stack, and the game puts a tutorial hint in
// it.
//
// Where it starts and where it wraps: 0x55B577 adds 0x697C48 (34) to 0x697B28
// (200), scales the sum, subtracts 0x697C10 (4) and hands that to CFont::SetWrapx,
// so the text runs from x 34 to x 234 less the box's own inset. It draws at
// 0x697C44 (0.52) by 0x697C40 (1.1), set at 0x55B51F.
constexpr float kHelpBoxX = 34.0f;
constexpr float kHelpBoxWrapAt = 234.0f;
constexpr float kHelpBoxY = 28.0f;
constexpr float kHelpBoxInset = 4.0f;
constexpr float kHelpBoxScaleX = 0.52f;
constexpr float kHelpBoxScaleY = 1.1f;
// The gap the stack leaves under the box, so the two read as separate things
// rather than one block. The mod's own number, not the game's.
constexpr float kHelpBoxGap = 6.0f;

// Where the stack may start this frame. Normally the anchor; while the game is
// showing a help message, below that box instead.
//
// The box's bottom is the GAME's answer, not a computed one: CFont::GetTextRect
// (0x550720) walks the string at the current font state and returns the rectangle
// the text occupies, wrapping included, which is what the box is drawn around. An
// earlier version multiplied a guessed line height by a line count, and the whole
// drop distance rested on that guess.
//
// Sets CFont state and does NOT put it back. Safe because the caller snapshots
// CFont::Details before calling this and restores it on the way out, and because
// everything set here is set again by the stack's own drawing afterwards.
float ToastTopThisFrame(const ToastGeometry& geometry) {
  if (!CHud::IsHelpMessageBeingDisplayed()) return geometry.anchor_y;
  // An array of the game's own, so it is never absent; an empty one is a box with
  // nothing in it, which needs no room.
  const wchar_t* message = CHud::m_HelpMessageToPrint;
  if (message[0] == 0) return geometry.anchor_y;
  // The box's own face, scale and wrap edge: an extent measured under any other set
  // of them is a different box.
  CFont::SetFontStyle(FONT_STANDARD);
  CFont::SetPropOn();
  CFont::SetCentreOff();
  CFont::SetRightJustifyOff();
  CFont::SetJustifyOff();
  CFont::SetBackgroundOff();
  CFont::SetScale(StretchX(kHelpBoxScaleX), StretchY(kHelpBoxScaleY));
  CFont::SetWrapx(StretchX(kHelpBoxWrapAt) - kHelpBoxInset);
  CRect rect(0.0f, 0.0f, 0.0f, 0.0f);
  CFont::GetTextRect(&rect, StretchX(kHelpBoxX), StretchY(kHelpBoxY), message);
  // The FAR edge, which this engine's CRect calls `top`, not `bottom`. Decoded off
  // the non-centred write at 0x550BD5, where the fields land as left(+0),
  // bottom(+4), right(+8), top(+0xC):
  //
  //   bottom = y                      the edge the text starts at
  //   top    = y + lines * advance    the edge it ends at, advance being
  //                                   0x6971CC (32) * scale_y * 0x6971D0 (0.5)
  //                                   plus 0x6971D4 (2), twice over at the end
  //
  // So the names read as though the screen counted upward and the box's own bottom
  // is `top`. Reading `bottom` returned the box's TOP, which is why the stack sat
  // over the hint instead of under it. Taken as the larger of the two so the naming
  // cannot bite again.
  const float far_edge = rect.top > rect.bottom ? rect.top : rect.bottom;
  // Back into the units the geometry is written in, plus the box's own inset
  // between its last line and its edge.
  const float bottom = UnstretchY(far_edge) + kHelpBoxInset;
  return ToastTopBelowBox(geometry, bottom, kHelpBoxGap);
}

}  // namespace

std::string ModuleSettingsPath() {
  // The module this code is in, found from an address inside it rather than from
  // the process, so it is the .asi's own file and not whatever launched the game.
  // An unnamed module means no file, which the caller reads as defaults.
  HMODULE module = nullptr;
  if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                             GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                         reinterpret_cast<LPCSTR>(&ModuleSettingsPath),
                         &module) == 0) {
    return std::string();
  }
  char path[MAX_PATH] = {};
  const DWORD written = GetModuleFileNameA(module, path, MAX_PATH);
  if (written == 0 || written >= MAX_PATH) return std::string();
  return SettingsPathForModule(std::string(path, written));
}

ToastGeometry LoadToastGeometry() {
  const std::string path = ModuleSettingsPath();
  if (path.empty()) return ToastGeometry();
  std::ifstream file(path);
  if (!file) return ToastGeometry();
  std::vector<std::string> lines;
  std::string line;
  // Bounded, so a file that is not one cannot be read into memory whole. Far more
  // lines than the handful of settings this section has.
  constexpr std::size_t kMaxSettingLines = 512;
  while (lines.size() < kMaxSettingLines && std::getline(file, line)) {
    lines.push_back(line);
  }
  return ParseToastGeometry(lines);
}

void DrawToastStack(ToastStackState& state, const ToastGeometry& geometry,
                    int alpha, const ToastAdvance& advance) {
  // Nothing at all to do, and nothing that could become something: the advance
  // only ever moves rows out of the queue, so an empty stack with an empty queue
  // stays empty and the font state is left untouched.
  if (state.waiting.empty() && state.visible.empty() &&
      ToastNoticeLines(state) == 0) {
    return;
  }

  // Everything CFont holds is restored on the way out. This hook returns into the
  // frame's own 2D pass, which keeps printing afterwards (the fade overlay, the
  // brief message, the garage text), and not every one of those printers sets
  // every field it depends on. A narrow wrap edge or a drop shadow left behind
  // would land on somebody else's text.
  const CFontDetails saved = CFont::Details;

  // Where the stack starts this frame, which is not always the anchor: a tutorial
  // box owns the top left corner while it is up, and the stack drops below it for
  // exactly as long as that lasts.
  //
  // FIRST, before the stack's own font state below. Measuring the box needs the
  // BOX's face, scale and wrap edge, and this leaves them behind; running it after
  // the setup left every toast measured, cut and printed at the help box's size
  // against the box's own narrow wrap edge, and the cut was then remembered.
  const float top_y = ToastTopThisFrame(geometry);
  const std::size_t line_capacity = ToastLineCapacityFrom(geometry, top_y);

  // Left to right, proportional, shadowed, no centring: the stack is a list to
  // read over a moving world, so contrast comes from the shadow the way the
  // vanilla brief message gets it. Set before anything is measured, since the
  // measuring below has to see the same face and scale the printing will.
  CFont::SetFontStyle(FONT_STANDARD);
  CFont::SetJustifyOff();
  CFont::SetCentreOff();
  CFont::SetRightJustifyOff();
  CFont::SetBackgroundOff();
  CFont::SetPropOn();
  CFont::SetDropShadowPosition(1);
  // Black behind the text at the text's own alpha, which is what the vanilla brief
  // message does for the same problem (0x55AEA8 lays 0,0,0 at 0x80 behind
  // #E1E1E1).
  CFont::SetDropColor(CRGBA(0, 0, 0, static_cast<unsigned char>(alpha)));
  CFont::SetScale(StretchX(geometry.scale_x), StretchY(geometry.scale_y));

  const float wrap_at =
      std::min(geometry.anchor_x + geometry.width, kVirtualWidth);
  const float right_edge = StretchX(wrap_at);
  // The wrap edge is the stack's own, as a backstop only: every line was cut to
  // fit before it was drawn, so nothing should reach it. A line that did would
  // fold here rather than run across the screen.
  CFont::SetWrapx(right_edge);

  // Cut whatever has not been cut, against the width each line actually draws in
  // rather than the virtual one, since that is what the font measures in. A row's
  // first line starts at the anchor; every line after it is set in and has that
  // much less room, and a line cut to the wrong one of the two lands a whole
  // indent past the wrap edge and folds onto the row below. Done once per row, not
  // once per frame: FitToastStack records what it has done.
  const float first_width = right_edge - StretchX(geometry.anchor_x);
  const float continuation_width =
      right_edge - StretchX(geometry.anchor_x + geometry.continuation_indent);
  FitToastStack(state, first_width, continuation_width,
                line_capacity, &MeasureToastLine);

  // Then the advance, which is the caller's: it owns the clock and the band's own
  // capacity. After the cutting, because a row's line count is not final until its
  // lines are cut and the band is measured in line counts; before the draw order
  // is taken, because the advance admits and expires rows and every pointer into
  // the visible list would otherwise be one it had already moved.
  if (advance) advance(state, line_capacity);

  const std::vector<const ToastRow*> rows = ToastDrawOrder(state);
  if (rows.empty()) {
    CFont::Details = saved;
    return;
  }

  // Downward from the top, newest row first, so a new row always appears in the
  // same place and the older ones move down under it. A row's own lines read
  // downward too, which is now the same direction the stack runs in, so nothing is
  // reversed: an item row is one line, and only a broken notice has more than one.
  float y = top_y;
  for (const ToastRow* row : rows) {
    if (row == nullptr) continue;
    for (std::size_t index = 0; index < row->lines.size(); ++index) {
      if (y > geometry.floor_y) {
        CFont::Details = saved;
        return;
      }
      const std::vector<ToastSegment>& line = row->lines[index];
      // Only a row's first line starts at the anchor's own x; the rest are set in,
      // which is how a broken notice reads as one block.
      float x = StretchX(geometry.anchor_x +
                         (index == 0 ? 0.0f : geometry.continuation_indent));
      for (const ToastSegment& segment : line) {
        if (segment.text.empty()) continue;
        const wchar_t* text = Widen(segment.text);
        // MEASURED BEFORE IT IS PRINTED, and the order is the whole point:
        // CFont::PrintString overwrites a TRAILING SPACE in the buffer it is
        // handed with a terminator (0x551381, guarded on the character being a
        // space and the next one being the terminator). Printing first therefore
        // shortens the very string the advance is about to measure, and every
        // segment ending in a space loses it: "You found your" ran straight into
        // the item name. GetStringWidth itself is innocent, since `sentence` true
        // walks past spaces (0x5506F4).
        const float advance = CFont::GetStringWidth(text, true);
        CFont::SetColor(ToastRoleColor(segment.role, alpha));
        CFont::PrintString(x, StretchY(y), text);
        // Each segment starts where the last one ended, in the face and scale this
        // line draws in. Per segment ONLY to advance: whether the LINE fits was
        // decided from its whole text above, never from a sum of these, since
        // summing drifts and spreads the words apart.
        x += advance;
      }
      y += geometry.line_height;
    }
  }
  CFont::Details = saved;
}

}  // namespace gtavc
