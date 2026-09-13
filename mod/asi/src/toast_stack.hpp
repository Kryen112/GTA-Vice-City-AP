// The in-game toast stack's drawing. The model is in scm_toasts.hpp and carries
// no game headers; everything
// that needs plugin-sdk is here.
#pragma once

#include <functional>

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

}  // namespace gtavc
