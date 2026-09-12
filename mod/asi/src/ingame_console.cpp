#include "ingame_console.hpp"
#include <algorithm>
#include <map>
#include <CPad.h>
#include <CSprite2d.h>
#include "hud_text.hpp"
#include "console_font.hpp"

namespace gtavc {
class ConsoleFont {
  struct Entry {
    std::wstring text;
    std::unique_ptr<CSprite2d> sprite;
    int width, height, advance;
  };
  std::deque<Entry> cache_;
 public:
  const int cell_width, height;
  ConsoleFont(int width, int font_height) : cell_width(width), height(font_height) {}
  float Draw(float x, float y, std::wstring text, const CRGBA& color) {
    for (auto& c : text) if (c < 32) c = L' ';
    if (text.empty()) return 0;
    auto entry = std::find_if(cache_.begin(), cache_.end(), [&](const Entry& e) { return e.text == text; });
    if (entry == cache_.end()) {
      ConsoleTextBitmap bitmap(text, cell_width, height);
      if (!bitmap.pixels) return static_cast<float>(bitmap.advance);
      auto* image = RwImageCreate(bitmap.width, bitmap.height, 32);
      if (!image) return static_cast<float>(bitmap.advance);
      if (!RwImageAllocatePixels(image)) { RwImageDestroy(image); return static_cast<float>(bitmap.advance); }
      for (int row = 0; row < bitmap.height; ++row) {
        auto* dest = image->cpPixels + row * image->stride;
        for (int col = 0; col < bitmap.width; ++col) {
          dest[col * 4] = dest[col * 4 + 1] = dest[col * 4 + 2] = 255;
          dest[col * 4 + 3] = static_cast<unsigned char>(bitmap.pixels[row * bitmap.width + col] & 255);
        }
      }
      auto* raster = RwRasterCreate(bitmap.width, bitmap.height, 32, rwRASTERTYPETEXTURE | rwRASTERFORMAT8888);
      const bool uploaded = raster && RwRasterSetFromImage(raster, image);
      RwImageDestroy(image);
      if (!uploaded) { if (raster) RwRasterDestroy(raster); return static_cast<float>(bitmap.advance); }
      auto sprite = std::make_unique<CSprite2d>();
      sprite->m_pTexture = RwTextureCreate(raster);
      if (!sprite->m_pTexture) { RwRasterDestroy(raster); return static_cast<float>(bitmap.advance); }
      // Bound GPU memory even in busy rooms. Glyph coverage is reused across colors.
      if (cache_.size() == 128) cache_.pop_front();
      cache_.push_back({std::move(text), std::move(sprite), bitmap.width, bitmap.height, bitmap.advance});
      entry = std::prev(cache_.end());
    }
    entry->sprite->Draw(CRect(x, y, x + entry->width, y + entry->height), color);
    return static_cast<float>(entry->advance);
  }
};

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
float PrintMixed(ConsoleFont& fallback, float x, float y, std::wstring text, const CRGBA& color) {
  const float start = x;
  for (auto& c : text) if (c < 32) c = L' ';
  for (std::size_t first = 0; first < text.size();) {
    const bool native = ViceCityConsoleGlyph(text[first]) != 0;
    auto last = first + 1;
    while (last < text.size() && (ViceCityConsoleGlyph(text[last]) != 0) == native) ++last;
    auto run = text.substr(first, last - first);
    if (native) {
      for (auto& c : run) c = ViceCityConsoleGlyph(c);
      // Vice City trims trailing spaces while printing, so measure first.
      const float advance = CFont::GetStringWidth(run.c_str(), true);
      CFont::SetColor(color);
      // Space-only runs become empty font-buffer entries, which VC misrenders.
      if (run.find_first_not_of(L' ') != std::wstring::npos) CFont::PrintString(x, y, run.c_str());
      x += advance;
    } else {
      x += fallback.Draw(x, y, run, color);
    }
    first = last;
  }
  return x - start;
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
IngameConsole::IngameConsole(std::function<void(std::string)> send) : send_(std::move(send)) {}
void IngameConsole::ReleaseGraphics() { font_.reset(); }
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
  wrap_dirty_ = true;
  // Preserve complete message lines for the console's measured screen width.
  // The shorter HUD popup rows must not become permanent history line breaks.
  for (auto& line : WrapConsoleText(wide, static_cast<float>(wide.text.size()))) {
    line.history_id = ++next_line_id_;
    if (notify)
      for (const auto& popup : WrapConsoleText(line)) popups_.Add(popup);
    lines_.push_back(std::move(line));
    if (lines_.size() > 300) lines_.pop_front();
  }
}
void IngameConsole::Key(WPARAM key) {
  if (key == VK_TAB) {
    completion_.Complete(input_, cursor_, (GetKeyState(VK_SHIFT) & 0x8000) != 0);
    return;
  }
  if (key != VK_SHIFT && key != VK_LSHIFT && key != VK_RSHIFT) completion_.Reset();
  if (key == VK_ESCAPE) { active_ = false; return; }
  if (key == VK_RETURN) {
    if (!input_.empty()) {
      send_(Utf8(input_));
      std::fill(input_.begin(), input_.end(), 0);
      input_.clear(); cursor_ = 0; scroll_ = 0;
    }
  } else if (key == VK_BACK && cursor_) input_.erase(--cursor_, 1);
  else if (key == VK_DELETE && cursor_ < input_.size()) input_.erase(cursor_, 1);
  else if (key == VK_LEFT && cursor_) --cursor_;
  else if (key == VK_RIGHT && cursor_ < input_.size()) ++cursor_;
  else if (key == VK_HOME) cursor_ = 0;
  else if (key == VK_END) cursor_ = input_.size();
  else if (key == VK_PRIOR) scroll_ = std::min(wrapped_lines_.size() > 18 ? wrapped_lines_.size() - 18 : 0, scroll_ + 12);
  else if (key == VK_NEXT) scroll_ = scroll_ > 12 ? scroll_ - 12 : 0;
  else if (key == 'V' && (GetKeyState(VK_CONTROL) & 0x8000) && OpenClipboard(window_)) {
    const HANDLE data = GetClipboardData(CF_UNICODETEXT);
    if (data) {
      const auto* text = static_cast<const wchar_t*>(GlobalLock(data));
      if (text) {
        const auto bound = std::min<std::size_t>(GlobalSize(data) / sizeof(wchar_t), 2048);
        for (std::size_t i = 0; i < bound && text[i] && input_.size() < 1024; ++i)
          if (text[i] >= 32) input_.insert(cursor_++, 1, text[i]);
        GlobalUnlock(data);
      }
    }
    CloseClipboard();
  }
}
LRESULT CALLBACK IngameConsole::WindowProc(HWND window, UINT message, WPARAM w, LPARAM l) {
  auto& self = *instance_;
  if (message == WM_KILLFOCUS) { self.active_ = false; self.completion_.Reset(); }
  if (message == WM_KEYDOWN && w == VK_F8) {
    self.completion_.Reset();
    if (!(l & (1L << 30))) self.active_ = !self.active_;
    self.BlockControls();
    return 0;
  }
  if (self.active_) {
    if (message == WM_KEYDOWN) { self.Key(w); self.BlockControls(); return 0; }
    if (message == WM_CHAR) {
      if (w >= 32 && w != 127 && self.input_.size() < 1024) {
        self.completion_.Reset();
        self.input_.insert(self.cursor_++, 1, static_cast<wchar_t>(w));
      }
      return 0;
    }
    if (message == WM_KEYUP || message == WM_MOUSEWHEEL ||
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
void IngameConsole::Draw(bool show_hint) {
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
    if (show_hint) Print(*font_, 414, L"F8  Archipelago chat / connection");
    float y = 20;
    for (const auto& line : popups_.Advance(now, StretchX(590), measure)) {
      const int alpha = ConsolePopupAlpha(line.popup_until, now);
      CSprite2d::DrawRect(CRect(StretchX(14), StretchY(y - 2), StretchX(626), StretchY(y + 16)),
                         CRGBA(10, 12, 30, alpha * 180 / 255));
      PrintLine(*font_, y, line, alpha);
      y += 16;
    }
  } else {
    popups_.Pause(now);
    BlockControls();
    CSprite2d::DrawRect(CRect(StretchX(14), StretchY(28), StretchX(626), StretchY(414)), CRGBA(10, 12, 30, 235));
    Print(*font_, 40, L"ARCHIPELAGO | F8/Esc close | PgUp/PgDn Scroll | type /help for more.");
    scroll_ = std::min(scroll_, wrapped_lines_.size() > 18 ? wrapped_lines_.size() - 18 : 0);
    const auto end = wrapped_lines_.size() - scroll_;
    const auto start = end > 18 ? end - 18 : 0;
    for (std::size_t i = start; i < end; ++i) {
      const float y = 68 + static_cast<float>(i - start) * 16;
      if (i > start)
        CSprite2d::DrawRect(CRect(StretchX(24), StretchY(y - 2), StretchX(614), StretchY(y - 1.5f)),
                           CRGBA(130, 135, 165, 65));
      PrintLine(*font_, y, wrapped_lines_[i]);
    }
    std::wstring shown = input_;
    if (shown.rfind(L"/password", 0) == 0) shown = L"/password " + std::wstring(shown.size() > 10 ? shown.size() - 10 : 0, L'*');
    const auto offset = cursor_ > 72 ? cursor_ - 72 : 0;
    shown = shown.substr(std::min(offset, shown.size()), 80);
    shown.insert(std::min(cursor_ - offset, shown.size()), L"|");
    shown = L"> " + shown;
    const auto input_rows = WrapConsoleText({shown, std::vector<std::uint32_t>(shown.size(), 0xEBE1F5)},
                                           StretchX(590), measure);
    for (std::size_t i = 0; i < std::min<std::size_t>(2, input_rows.size()); ++i)
      PrintLine(*font_, 378 + static_cast<float>(i) * 16, input_rows[i]);
  }
  CFont::Details = saved;
}
}
