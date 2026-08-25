#include "hud_text.hpp"

#include <cstddef>

namespace gtavc {

float StretchX(float x) {
  return x * static_cast<float>(RsGlobal.maximumWidth) / kVirtualWidth;
}

float StretchY(float y) {
  return y * static_cast<float>(RsGlobal.maximumHeight) / kVirtualHeight;
}

const wchar_t* Widen(const std::string& text) {
  // One past the longest string either caller may hand over, so a string that fits
  // the bound is never truncated here. Anything longer is refused by the measuring
  // rather than answered for in part, which is what keeps a line the fitting
  // accepted a line it actually measured.
  //
  // Deep enough that no string measured or printed inside one frame is rewritten
  // while it is still in use. The font copies during the print rather than keeping
  // the pointer, so this is insurance rather than a requirement.
  constexpr std::size_t kBufferChars = kWidenMaxChars + 1;
  constexpr std::size_t kBufferCount = 256;
  static wchar_t buffers[kBufferCount][kBufferChars];
  static std::size_t next_buffer = 0;
  wchar_t* buffer = buffers[next_buffer];
  next_buffer = (next_buffer + 1) % kBufferCount;
  const std::size_t length =
      text.size() < kBufferChars - 1 ? text.size() : kBufferChars - 1;
  for (std::size_t index = 0; index < length; ++index) {
    const unsigned char character = static_cast<unsigned char>(text[index]);
    // The tilde opens the game's own formatting token. Everything below a space
    // goes with it: a newline or a tab inside a name from the server would be
    // measured as one thing and drawn as another, and the whole point of measuring
    // a line is that what was measured is what draws.
    const bool replace = character == '~' || character < 0x20;
    buffer[index] = replace ? L' ' : static_cast<wchar_t>(character);
  }
  buffer[length] = 0;
  return buffer;
}

CRGBA ToastRoleColor(ToastRole role, int alpha) {
  const unsigned char a = static_cast<unsigned char>(alpha);
  switch (role) {
    case ToastRole::kOwnSlot:
      return CRGBA(238, 0, 238, a);
    case ToastRole::kOtherSlot:
      return CRGBA(238, 232, 205, a);
    case ToastRole::kProgression:
      return CRGBA(159, 121, 238, a);
    case ToastRole::kUseful:
      return CRGBA(79, 148, 205, a);
    case ToastRole::kTrap:
      return CRGBA(237, 123, 110, a);
    case ToastRole::kFiller:
      return CRGBA(9, 203, 203, a);
    case ToastRole::kLocation:
      return CRGBA(50, 205, 50, a);
    case ToastRole::kConnective:
    default:
      return CRGBA(230, 230, 230, a);
  }
}

}  // namespace gtavc
