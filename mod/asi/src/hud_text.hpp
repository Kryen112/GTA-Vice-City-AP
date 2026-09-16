// Text the mod draws itself, shared by everything that draws any: the frontend's
// virtual screen, the widening the font needs, and the colour every Archipelago
// role draws in.
//
// Two callers, the pause menu's status page and the in-game toast stack. They
// share this rather than each keeping a copy so the virtual-space assumption and
// the tilde neutralisation cannot drift apart between them.
#pragma once

#include <algorithm>
#include <cstddef>
#include <deque>
#include <memory>
#include <string>

#include "scm_toasts.hpp"

#include <plugin.h>
#include <CFont.h>
#include <CFontDetails.h>
#include <RenderWare.h>
#include <CSprite2d.h>
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
    // Cached glyphs can be evicted or resized; never leave their raster bound.
    RwRaster* previous_raster = nullptr;
    RwRenderStateGet(rwRENDERSTATETEXTURERASTER, &previous_raster);
    entry->sprite->Draw(CRect(x, y, x + entry->width, y + entry->height), color);
    RwRenderStateSet(rwRENDERSTATETEXTURERASTER, previous_raster);
    return static_cast<float>(entry->advance);
  }
};

float PrintMixed(ConsoleFont& fallback, float x, float y, std::wstring text,
                 const CRGBA& color, bool draw = true);

// The virtual screen the frontend lays out in, which the game stretches to
// whatever resolution is running. The menu table's own positions are in these
// units, so everything the mod draws is too. Defined in the game-free header and
// named here, so the geometry bounds the console self-test drives and the drawing
// that stretches against them cannot disagree about the screen.
constexpr float kVirtualWidth = kVirtualScreenWidth;
constexpr float kVirtualHeight = kVirtualScreenHeight;

float StretchX(float x);
float StretchY(float y);

// Back the other way, for a measurement the game handed back in its own device
// units that has to be compared against a layout written in the virtual ones.
float UnstretchY(float y);

// The text the mod hands the game. CFont takes wide characters and the mod
// composes narrow ones, so each string is widened into storage of the mod's own.
// The font reads the string during the print rather than keeping the pointer
// (unlike the brief-message queue, which is why PostToast owns a ring of its
// own), so the ring here is insurance rather than a requirement.
//
// The tilde opens the game's own formatting token, which the font expands in
// place. Item names, player names and location names come from the server
// verbatim, so the escape is neutralised here rather than trusted to stay short.
// The most characters Widen keeps. A longer string is truncated, so a width
// measured from one is the width of its front and not of the string: every
// measure has to refuse a string this long rather than answer for part of it.
constexpr std::size_t kWidenMaxChars = 255;

const wchar_t* Widen(const std::string& text);

// What each Archipelago role draws in. These are the Harry Potter 2 mod's values
// rather than the ones in NetUtils.py: Archipelago's yellow FAFAD2 and cyan
// 00EEEE are nearly white, which reads on a dark UI and washes out over a bright
// sky, and that mod had already taken every colour down a shade for exactly this
// reason. Its numbers are proven in a shipped game rather than guessed.
//
// The own-slot magenta is the one exact match with Archipelago's own, and it is
// what "You" and "your" draw in, so the role survives the second-person wording.
CRGBA ToastRoleColor(ToastRole role, int alpha);

}  // namespace gtavc
