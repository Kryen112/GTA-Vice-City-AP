// The in-game toast stack's drawing, and the optional file that tunes where it
// draws. The model is in scm_toasts.hpp and carries no game headers; everything
// that needs plugin-sdk is here.
#pragma once

#include <functional>
#include <string>

#include "scm_toasts.hpp"

namespace gtavc {

// What the caller does between the cutting and the drawing: expire what is
// finished and admit what fits. Taken as a callback rather than done here because
// it owns the clock, and it has to run in that gap, since a row is not a fixed
// height until its lines have been cut and the band is measured in line counts.
//
// Handed the capacity rather than working it out, because the DRAWING owns how many
// lines there really are this frame: a tutorial box pushes the top down while it is
// up, and an advance admitting against the full band would start a row's lifetime on
// a line the drawing is about to clip away.
using ToastAdvance = std::function<void(ToastStackState&, std::size_t)>;

// Cuts every line that has not been cut yet to the stack's own width, then draws
// the rows in the order ToastDrawOrder gives them: the first at the anchor, each
// one after it stacked below. Called from the frame's HUD draw, so the caller has
// already decided the stack should be visible at all.
//
// The cut is here and not in the caller because it needs the font, and it must
// happen before anything is drawn: a line wider than the stack folds at CFont's
// wrap edge and lands its tail over the row below, and the fold advance is
// exactly a row height, so the two collide glyph on glyph.
void DrawToastStack(ToastStackState& state, const ToastGeometry& geometry,
                    int alpha, const ToastAdvance& advance);

// The geometry the file beside the running module says to use. An absent,
// unreadable or unparseable file means the compiled-in defaults, silently, because
// a player who never writes one is the normal case and not an error case; a file
// present but missing a key keeps the default for that key alone.
//
// Every value is bounded against the virtual screen before it is returned, so a
// hand-edited file cannot put the stack off the screen. It CAN give the stack a
// band only one line tall, which the model handles rather than the bounds: the
// notices own a band that small, and the admission rule is what keeps a row from
// starting a lifetime it cannot be seen through.
ToastGeometry LoadToastGeometry();

// The file the geometry is read from: the running module's own path with its
// extension replaced, so `GtaVcAp.VC.asi` reads `GtaVcAp.VC.ini` and the two
// cannot drift if the build ever renames its output. Empty when the module cannot
// be named, which the caller reads as defaults. This is also the convention the
// other ASIs in a Vice City folder follow.
std::string ModuleSettingsPath();

}  // namespace gtavc
