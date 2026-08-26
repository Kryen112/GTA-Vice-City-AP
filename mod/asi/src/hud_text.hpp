// Text the mod draws itself, shared by everything that draws any: the frontend's
// virtual screen, the widening the font needs, and the colour every Archipelago
// role draws in.
//
// Two callers, the pause menu's status page and the in-game toast stack. They
// share this rather than each keeping a copy so the virtual-space assumption and
// the tilde neutralisation cannot drift apart between them.
#pragma once

#include <cstddef>
#include <string>

#include "scm_toasts.hpp"

#include <plugin.h>
#include <CFont.h>
#include <CFontDetails.h>
#include <RenderWare.h>

namespace gtavc {

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
