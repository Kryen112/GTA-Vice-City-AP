#include "toast_stack.hpp"

#include <algorithm>
#include <cstddef>
#include <fstream>
#include <limits>
#include <string>
#include <vector>

#include "hud_text.hpp"

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
                ToastLineCapacity(geometry), &MeasureToastLine);

  // Then the advance, which is the caller's: it owns the clock and the band's own
  // capacity. After the cutting, because a row's line count is not final until its
  // lines are cut and the band is measured in line counts; before the draw order
  // is taken, because the advance admits and expires rows and every pointer into
  // the visible list would otherwise be one it had already moved.
  if (advance) advance(state);

  const std::vector<const ToastRow*> rows = ToastDrawOrder(state);
  if (rows.empty()) {
    CFont::Details = saved;
    return;
  }

  // Upward from the anchor. A row's own lines read downward, so a two-line row
  // takes its lines in reverse as the stack climbs: the row's last line sits
  // lowest and its first line above it, which is what puts the sentence over its
  // own location rather than under the next row's.
  float y = geometry.anchor_y;
  for (const ToastRow* row : rows) {
    if (row == nullptr) continue;
    for (std::size_t index = row->lines.size(); index > 0; --index) {
      if (y < geometry.ceiling_y) {
        CFont::Details = saved;
        return;
      }
      const std::vector<ToastSegment>& line = row->lines[index - 1];
      // Only the row's first line starts at the anchor's own x; the rest are set
      // in, so a location reads as belonging to the sentence above it.
      float x = StretchX(geometry.anchor_x +
                         (index == 1 ? 0.0f : geometry.continuation_indent));
      for (const ToastSegment& segment : line) {
        if (segment.text.empty()) continue;
        const wchar_t* text = Widen(segment.text);
        CFont::SetColor(ToastRoleColor(segment.role, alpha));
        CFont::PrintString(x, StretchY(y), text);
        // Each segment starts where the last one ended, measured in the face and
        // scale this line draws in. Per segment ONLY to advance: whether the LINE
        // fits was decided from its whole text above, never from a sum of these,
        // since summing drifts and spreads the words apart.
        x += CFont::GetStringWidth(text, true);
      }
      y -= geometry.line_height;
    }
  }
  CFont::Details = saved;
}

}  // namespace gtavc
