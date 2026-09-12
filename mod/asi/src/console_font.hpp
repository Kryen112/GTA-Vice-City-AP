#pragma once
#include <windows.h>
#include <algorithm>
#include <cstdint>
#include <string>
#include <string_view>

#pragma comment(lib, "gdi32.lib")

namespace gtavc {
// FONT_STANDARD's atlas repurposes ASCII cells for game icons, '~' is a
// formatting delimiter, and '/' has an oversized advance. Use the fallback
// for those characters; the remaining printable ASCII stays native.
// Accents use Vice City's internal encoding, not their Unicode code points.
inline wchar_t ViceCityConsoleGlyph(wchar_t c) {
  if (c >= 32 && c < 127)
    return std::wstring_view(L"/<>@^_{|}~").find(c) == std::wstring_view::npos ? c : 0;
  if (c == L'\u00ba') return 0x5F;
  constexpr std::wstring_view accents =
      L"\u00c0\u00c1\u00c2\u00c4\u00c6\u00c7\u00c8\u00c9\u00ca\u00cb\u00cc\u00cd\u00ce\u00cf\u00d2\u00d3"
      L"\u00d4\u00d6\u00d9\u00da\u00db\u00dc\u00df\u00e0\u00e1\u00e2\u00e4\u00e6\u00e7\u00e8\u00e9\u00ea"
      L"\u00eb\u00ec\u00ed\u00ee\u00ef\u00f2\u00f3\u00f4\u00f6\u00f9\u00fa\u00fb\u00fc\u00d1\u00f1\u00bf\u00a1\u00b4";
  const auto index = accents.find(c);
  return index == std::wstring_view::npos ? 0 : static_cast<wchar_t>(128 + index);
}

// Windows supplies the glyphs; no game formatting tokens or font assets enter
// this path. White-on-black coverage becomes the texture's alpha channel.
struct ConsoleTextBitmap {
  HDC dc = CreateCompatibleDC(nullptr);
  HFONT font = nullptr;
  HBITMAP bitmap = nullptr;
  HGDIOBJ old_font = nullptr, old_bitmap = nullptr;
  std::uint32_t* pixels = nullptr;
  int width = 1, height = 1, advance = 0;

  ConsoleTextBitmap(const std::wstring& text, int cell_width, int font_height) {
    if (!dc || text.empty() || text.size() > 1024 || cell_width < 1 || cell_width > 128 ||
        font_height < 1 || font_height > 256) return;
    font = CreateFontW(-font_height, cell_width, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                       DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                       ANTIALIASED_QUALITY, FIXED_PITCH | FF_MODERN, L"Consolas");
    if (!font) return;
    old_font = SelectObject(dc, font);
    SIZE extent{};
    if (!GetTextExtentPoint32W(dc, text.data(), static_cast<int>(text.size()), &extent) ||
        extent.cx > 8190 || extent.cy > 254) return;
    advance = extent.cx;
    while (width < extent.cx + 2) width *= 2;
    while (height < extent.cy + 2) height *= 2;
    BITMAPINFO info{};
    info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = width;
    info.bmiHeader.biHeight = -height; // top-down, as RenderWare expects
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    bitmap = CreateDIBSection(dc, &info, DIB_RGB_COLORS, &bits, nullptr, 0);
    if (!bitmap || !bits) return;
    old_bitmap = SelectObject(dc, bitmap);
    std::fill_n(static_cast<std::uint32_t*>(bits), width * height, 0);
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, RGB(255, 255, 255));
    const bool drawn = TextOutW(dc, 0, 0, text.data(), static_cast<int>(text.size())) != FALSE;
    GdiFlush(); // finish GDI writes before reading the DIB directly
    if (drawn) pixels = static_cast<std::uint32_t*>(bits);
  }
  ~ConsoleTextBitmap() {
    if (old_bitmap) SelectObject(dc, old_bitmap);
    if (old_font) SelectObject(dc, old_font);
    if (bitmap) DeleteObject(bitmap);
    if (font) DeleteObject(font);
    if (dc) DeleteDC(dc);
  }
  ConsoleTextBitmap(const ConsoleTextBitmap&) = delete;
  ConsoleTextBitmap& operator=(const ConsoleTextBitmap&) = delete;
};
}  // namespace gtavc
