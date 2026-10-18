#include "ingame_console.hpp"
#include <algorithm>
#include <map>
#include <cstring>
#include <CPad.h>
#include <CSprite2d.h>
#include "hud_text.hpp"
#include "console_font.hpp"
#include "native_data.hpp"
#include "json.hpp"

namespace gtavc {


IngameConsole* IngameConsole::instance_ = nullptr;
namespace {
std::wstring Wide(const std::string& text) {
  const int count = MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0);
  std::wstring result(count, 0);
  MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), result.data(), count);
  return result;
}
std::string Utf8(const std::wstring& text) {
  const int count = WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
  std::string result(count, 0);
  WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), result.data(), count, nullptr, nullptr);
  return result;
}

void Print(ConsoleFont& font, float y, const std::wstring& text) {
  PrintMixed(font, StretchX(24), StretchY(y), text, CRGBA(235, 225, 245, 255));
}
void PrintLine(ConsoleFont& font, float y, const ConsoleLine& line, int alpha = 255) {
  float x = StretchX(24);
  for (std::size_t first = 0; first < line.text.size();) {
    auto last = first + 1;
    while (last < line.text.size() && line.colors[last] == line.colors[first]) ++last;
    auto text = line.text.substr(first, last - first);
    const auto color = line.colors[first];
    x += PrintMixed(font, x, StretchY(y), text, CRGBA((color >> 16) & 255, (color >> 8) & 255, color & 255, alpha));
    first = last;
  }
}
}
IngameConsole::IngameConsole(std::function<void(std::string)> send) : send_(std::move(send)) {
  const auto data = nlohmann::json::parse(kNativeData);
  for (const auto& entry : data.at("items")) completion_.items.push_back(Wide(entry.at(0).get<std::string>()));
  for (const auto& entry : data.at("locations")) completion_.locations.push_back(Wide(entry.get<std::string>()));
  std::sort(completion_.items.begin(), completion_.items.end());
  std::sort(completion_.locations.begin(), completion_.locations.end());
}
void IngameConsole::ReleaseGraphics() { font_.reset(); }
void IngameConsole::SetCompletionNames(std::vector<std::string> items, std::vector<std::string> locations) {
  std::pair<std::vector<std::wstring>, std::vector<std::wstring>> names;
  for (const auto& item : items) names.first.push_back(Wide(item));
  for (const auto& location : locations) names.second.push_back(Wide(location));
  std::sort(names.first.begin(), names.first.end());
  std::sort(names.second.begin(), names.second.end());
  std::lock_guard<std::mutex> lock(mutex_);
  pending_completion_ = std::move(names);
}
IngameConsole::~IngameConsole() {
  if (window_ && reinterpret_cast<WNDPROC>(GetWindowLongPtrW(window_, GWLP_WNDPROC)) == WindowProc)
    SetWindowLongPtrW(window_, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(previous_));
  if (instance_ == this) instance_ = nullptr;
}
void IngameConsole::Add(const std::string& text) {
  Add(ConsoleMessage{{text, 0xFFFFFF}});
}
void IngameConsole::Add(const ConsoleMessage& message, bool notify) {
  ConsoleLine wide;
  std::size_t remaining = 16384;
  for (const auto& span : message) {
    const auto bytes = std::min(remaining, span.text.size());
    const auto text = Wide(span.text.substr(0, bytes));
    wide.text += text;
    wide.colors.insert(wide.colors.end(), text.size(), span.color);
    remaining -= bytes;
    if (!remaining) break;
  }
  std::lock_guard<std::mutex> lock(mutex_);
  notify = notify && !active_.load();
  wrap_dirty_ = true;
  // Preserve complete message lines for the console's measured screen width.
  // The shorter HUD popup rows must not become permanent history line breaks.
  for (auto& line : WrapConsoleText(wide, static_cast<float>(wide.text.size()))) {
    line.history_id = ++next_line_id_;
    if (notify)
      for (const auto& popup : WrapConsoleText(line)) popups_.Add(popup);
    lines_.push_back(std::move(line));
    if (lines_.size() > 4096) lines_.pop_front();
  }
}
void IngameConsole::Scroll(int rows) {
  const auto maximum = wrapped_lines_.size() > kConsoleHistoryRows ? wrapped_lines_.size() - kConsoleHistoryRows : 0;
  if (rows >= 0) scroll_ = std::min(maximum, scroll_ + static_cast<std::size_t>(rows));
  else scroll_ = scroll_ > static_cast<std::size_t>(-rows) ? scroll_ - static_cast<std::size_t>(-rows) : 0;
}
void IngameConsole::ClearHistory() {
  std::lock_guard<std::mutex> lock(mutex_);
  lines_.clear(); wrapped_lines_.clear(); popups_.Clear(); scroll_ = 0; wrap_dirty_ = true;
}
bool IngameConsole::CopySelection() {
  const auto text = input_.Selected();
  if (SecretConsoleInput(input_.text) || text.empty() || !OpenClipboard(window_)) return false;
  const auto memory = GlobalAlloc(GMEM_MOVEABLE, (text.size() + 1) * sizeof(wchar_t));
  bool copied = false;
  if (memory) {
    if (auto* at = GlobalLock(memory)) {
      std::memcpy(at, text.c_str(), (text.size() + 1) * sizeof(wchar_t));
      GlobalUnlock(memory);
      copied = EmptyClipboard() && SetClipboardData(CF_UNICODETEXT, memory);
    }
    if (!copied) GlobalFree(memory);
  }
  CloseClipboard();
  return copied;
}
void IngameConsole::Key(WPARAM key) {
  pending_surrogate_ = 0;
  const bool ctrl = (GetKeyState(VK_CONTROL) & 0x8000) != 0;
  const bool shift = (GetKeyState(VK_SHIFT) & 0x8000) != 0;
  if (key == VK_TAB) {
    if (input_.cursor != input_.anchor) return;
    completion_.Complete(input_.text, input_.cursor, shift);
    input_.anchor = input_.cursor;
    return;
  }
  if (key != VK_SHIFT && key != VK_LSHIFT && key != VK_RSHIFT) completion_.Reset();
  if (key == VK_ESCAPE) { active_ = false; return; }
  if (key == VK_RETURN) {
    if (!input_.text.empty()) {
      if (input_.text == L"/clear") { ClearHistory(); input_history_.Add(L""); }
      else { send_(Utf8(input_.text)); input_history_.Add(input_.text); }
      input_.Clear(); scroll_ = 0;
    }
  } else if (ctrl && key == 'A') { input_.anchor = 0; input_.cursor = input_.text.size(); }
  else if (ctrl && key == 'C') CopySelection();
  else if (key == VK_UP || key == VK_DOWN) {
    input_history_.Recall(key == VK_UP, input_.text, input_.cursor);
    input_.anchor = input_.cursor;
  } else if (key == VK_BACK || key == VK_DELETE) input_.Erase(key == VK_BACK);
  else if (key == VK_LEFT || key == VK_RIGHT) input_.Move(key == VK_RIGHT, shift);
  else if (key == VK_HOME || key == VK_END) input_.Edge(key == VK_END, shift);
  else if (key == VK_PRIOR) Scroll(12);
  else if (key == VK_NEXT) Scroll(-12);
  else if (key == 'V' && ctrl && OpenClipboard(window_)) {
    const HANDLE data = GetClipboardData(CF_UNICODETEXT);
    if (data) {
      const auto* text = static_cast<const wchar_t*>(GlobalLock(data));
      if (text) {
        const auto bound = std::min<std::size_t>(GlobalSize(data) / sizeof(wchar_t), 2048);
        std::size_t length = 0;
        while (length < bound && text[length]) ++length;
        if (length && length == bound && text[length - 1] >= 0xD800 && text[length - 1] <= 0xDBFF) --length;
        const int bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, static_cast<int>(length),
                                            nullptr, 0, nullptr, nullptr);
        if (bytes) input_.Insert(std::wstring(text, length));
        GlobalUnlock(data);
      }
    }
    CloseClipboard();
  }
}
LRESULT CALLBACK IngameConsole::WindowProc(HWND window, UINT message, WPARAM w, LPARAM l) {
  auto& self = *instance_;
  if (message == WM_KILLFOCUS) {
    self.active_ = false; self.completion_.Reset(); self.pending_surrogate_ = 0; self.wheel_delta_ = 0;
  }
  if (message == WM_KEYDOWN && w == VK_F8) {
    self.completion_.Reset();
    self.pending_surrogate_ = 0;
    if (!(l & (1L << 30))) {
      std::lock_guard<std::mutex> lock(self.mutex_);
      self.active_ = !self.active_;
      if (self.active_) self.popups_.Clear();
    }
    self.BlockControls();
    return 0;
  }
  if (self.active_) {
    if (message == WM_KEYDOWN) { self.Key(w); self.BlockControls(); return 0; }
    if (message == WM_CHAR) {
      if (w >= 32 && w != 127 && w <= 0xFFFF) {
        self.completion_.Reset();
        const auto c = static_cast<wchar_t>(w);
        if (c >= 0xD800 && c <= 0xDBFF) self.pending_surrogate_ = c;
        else {
          if (c >= 0xDC00 && c <= 0xDFFF) {
            if (self.pending_surrogate_) self.input_.Insert(std::wstring{self.pending_surrogate_, c});
          } else self.input_.Insert(std::wstring(1, c));
          self.pending_surrogate_ = 0;
        }
      }
      return 0;
    }
    if (message == WM_MOUSEWHEEL) {
      self.wheel_delta_ += static_cast<short>(HIWORD(w));
      self.Scroll(3 * (self.wheel_delta_ / WHEEL_DELTA));
      self.wheel_delta_ %= WHEEL_DELTA;
      return 0;
    }
    if (message == WM_INPUT) return DefWindowProcW(window, message, w, l);
    if (message == WM_KEYUP || message == WM_SYSKEYDOWN || message == WM_SYSKEYUP || message == WM_SYSCHAR ||
        (message >= WM_MOUSEFIRST && message <= WM_MOUSELAST)) return 0;
  }
  return CallWindowProcW(self.previous_, window, message, w, l);
}
void IngameConsole::BlockControls() {
  if (!active_) return;
  for (int index = 0; index < 2; ++index) {
    auto* pad = CPad::GetPad(index);
    pad->NewState = {}; pad->OldState = {};
    pad->PCTempKeyState = {}; pad->PCTempJoyState = {}; pad->PCTempMouseState = {};
  }
  CPad::NewKeyState = {}; CPad::OldKeyState = {}; CPad::TempKeyState = {};
  CPad::NewMouseControllerState = {}; CPad::OldMouseControllerState = {};
}
void IngameConsole::Draw(bool show_hint, bool connected) {
  if (!window_) {
    HWND window = GetActiveWindow();
    DWORD process = 0;
    const auto thread = GetWindowThreadProcessId(window, &process);
    if (!window || process != GetCurrentProcessId() || thread != GetCurrentThreadId()) return;
    SetLastError(0);
    auto previous = reinterpret_cast<WNDPROC>(SetWindowLongPtrW(window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(&WindowProc)));
    if (!previous) return;
    window_ = window; previous_ = previous; instance_ = this;
  }
  std::lock_guard<std::mutex> lock(mutex_);
  if (pending_completion_) {
    completion_.items = std::move(pending_completion_->first);
    completion_.locations = std::move(pending_completion_->second);
    pending_completion_.reset(); completion_.Reset();
  }
  const auto now = GetTickCount64();
  if (!active_ && !show_hint && popups_.empty()) return;
  const auto saved = CFont::Details;
  CFont::SetJustifyOff(); CFont::SetCentreOff(); CFont::SetRightJustifyOff();
  CFont::SetBackgroundOff(); CFont::SetPropOn(); CFont::SetDropShadowPosition(0);
  CFont::SetFontStyle(FONT_STANDARD);
  CFont::SetScale(StretchX(0.32f), StretchY(0.6f));
  CFont::SetWrapx(StretchX(620));
  const int cell_width = std::max(1, static_cast<int>(StretchX(5.2f)));
  const int font_height = std::max(1, static_cast<int>(StretchY(11.2f)));
  if (!font_ || font_->cell_width != cell_width || font_->height != font_height) {
    font_ = std::make_unique<ConsoleFont>(cell_width, font_height);
    wrap_dirty_ = true;
  }
  // Font APIs belong on this draw thread, never on the network thread.
  std::map<std::wstring, float> widths;
  const auto measure = [&](std::wstring_view glyph) {
    std::wstring text(glyph);
    if (text.front() < 32) text.front() = L' ';
    auto found = widths.find(text);
    if (found != widths.end()) return found->second;
    const auto native = text.size() == 1 ? ViceCityConsoleGlyph(text.front()) : 0;
    float advance;
    if (native) {
      const wchar_t encoded[] = {static_cast<wchar_t>(native), 0};
      advance = CFont::GetStringWidth(encoded, true);
    } else {
      ConsoleTextBitmap bitmap(text, cell_width, font_height);
      advance = static_cast<float>(bitmap.advance);
    }
    widths.emplace(std::move(text), advance);
    return advance;
  };
  if (wrap_dirty_) {
    const auto last_id = wrapped_lines_.empty() ? 0 : wrapped_lines_.back().history_id;
    std::size_t added_rows = 0;
    wrapped_lines_.clear();
    for (const auto& line : lines_)
      for (auto& row : WrapConsoleText(line, StretchX(590), measure)) {
        if (row.history_id > last_id) ++added_rows;
        wrapped_lines_.push_back(std::move(row));
      }
    scroll_ = ConsoleScrollAfterArrival(scroll_, added_rows, wrapped_lines_.size());
    wrap_dirty_ = false;
  }
  if (!active_) {
    if (show_hint) {
      const float x = StretchX(24), y = StretchY(414);
      const float width = PrintMixed(*font_, x, y,
          L"F8  Archipelago chat / connection  |  ", CRGBA(235, 225, 245, 255));
      PrintMixed(*font_, x + width, y,
          connected ? L"AP: Connected" : L"AP: Disconnected",
          connected ? CRGBA(100, 235, 130, 255) : CRGBA(245, 120, 120, 255));
    }
    float y = 20;
    for (const auto& line : popups_.Advance(now, StretchX(590), measure)) {
      const int alpha = ConsolePopupAlpha(line.popup_until, now);
      CSprite2d::DrawRect(CRect(StretchX(14), StretchY(y - 2), StretchX(626), StretchY(y + 16)),
                         CRGBA(10, 12, 30, alpha * 180 / 255));
      PrintLine(*font_, y, line, alpha);
      y += 16;
    }
  } else {
    BlockControls();
    CSprite2d::DrawRect(CRect(StretchX(14), StretchY(28), StretchX(626), StretchY(414)), CRGBA(10, 12, 30, 235));
    Print(*font_, 40, L"ARCHIPELAGO | F8/Esc close | PgUp/PgDn Scroll | type /help for more.");
    scroll_ = std::min(scroll_, wrapped_lines_.size() > kConsoleHistoryRows ? wrapped_lines_.size() - kConsoleHistoryRows : 0);
    const auto end = wrapped_lines_.size() - scroll_;
    const auto start = end > kConsoleHistoryRows ? end - kConsoleHistoryRows : 0;
    for (std::size_t i = start; i < end; ++i) {
      const float y = 68 + static_cast<float>(i - start) * 16;
      if (i > start)
        CSprite2d::DrawRect(CRect(StretchX(24), StretchY(y - 2), StretchX(614), StretchY(y - 1.5f)),
                           CRGBA(130, 135, 165, 65));
      PrintLine(*font_, y, wrapped_lines_[i]);
    }
    std::wstring shown = input_.text;
    const bool secret = SecretConsoleInput(shown);
    if (secret) {
      const auto command_end = shown.find_first_of(L" \t", shown.find_first_not_of(L" \t"));
      const auto argument = command_end == std::wstring::npos ? command_end : shown.find_first_not_of(L" \t", command_end);
      if (argument != std::wstring::npos) std::fill(shown.begin() + argument, shown.end(), L'*');
    }
    const float y = StretchY(396), x = StretchX(24);
    const CRGBA input_color(235, 225, 245, 255);
    const float prompt_width = PrintMixed(*font_, x, y, L"> ", input_color);
    const float available = StretchX(590) - prompt_width;
    const auto glyph_units = [](std::wstring_view text, std::size_t index) -> std::size_t {
      return text[index] >= 0xD800 && text[index] <= 0xDBFF && index + 1 < text.size() &&
          text[index + 1] >= 0xDC00 && text[index + 1] <= 0xDFFF ? 2 : 1;
    };
    const auto fit = [&](std::wstring_view text, float limit) {
      std::size_t end = 0;
      float width = 0;
      while (end < text.size()) {
        const auto units = glyph_units(text, end);
        const float advance = measure(text.substr(end, units));
        if (width + advance > limit) break;
        width += advance;
        end += units;
      }
      return end;
    };
    const auto caret = std::min(input_.cursor, shown.size());
    auto offset = caret;
    float width = 0;
    while (offset) {
      const std::size_t units = offset > 1 && glyph_units(shown, offset - 2) == 2 ? 2 : 1;
      const float advance = measure(std::wstring_view(shown).substr(offset - units, units));
      if (width + advance > available) break;
      width += advance;
      offset -= units;
    }
    float caret_width = PrintMixed(*font_, 0, 0, shown.substr(offset, caret - offset), input_color, false);
    while (caret_width > available && offset < caret) {
      offset += glyph_units(shown, offset);
      caret_width = PrintMixed(*font_, 0, 0, shown.substr(offset, caret - offset), input_color, false);
    }
    const auto visible_end = offset + fit(std::wstring_view(shown).substr(offset), available);
    if (!secret && input_.cursor != input_.anchor) {
      const auto first = std::clamp(std::min(input_.cursor, input_.anchor), offset, visible_end);
      const auto last = std::clamp(std::max(input_.cursor, input_.anchor), offset, visible_end);
      const auto left = PrintMixed(*font_, 0, 0, shown.substr(offset, first - offset), input_color, false);
      const auto width = PrintMixed(*font_, 0, 0, shown.substr(first, last - first), input_color, false);
      CSprite2d::DrawRect(CRect(x + prompt_width + left, y, x + prompt_width + left + width, y + StretchY(12)),
                         CRGBA(90, 110, 180, 180));
    }
    const float typed_width = PrintMixed(*font_, x + prompt_width, y,
        shown.substr(offset, visible_end - offset), input_color);
    auto preview = input_.cursor == input_.anchor ? completion_.Preview(input_.text, input_.cursor) : L"";
    if (visible_end == shown.size() && !preview.empty()) {
      preview.resize(fit(preview, available - typed_width));
      PrintMixed(*font_, x + prompt_width + typed_width, y, preview, CRGBA(235, 225, 245, 112));
    }
    if ((now / 500) % 2 == 0) {
      const float caret_x = x + prompt_width + caret_width;
      CSprite2d::DrawRect(CRect(caret_x, y, caret_x + std::max(1.0f, StretchX(1)), y + StretchY(12)), input_color);
    }
  }
  CFont::Details = saved;
}
}
