// The game's own completion percentage, as its stats menu prints it. Free of
// any game header so the console self-test can exercise it without plugin-sdk.
//
// CStats::GetPercentageProgress returns a hundred times the progress points the
// player has made over the hundred and fifty four the script counts, already
// clamped to a hundred. The stats menu then converts that to an integer with
// the rounding mode set to round-toward-zero, so what a player reads on the
// "Percentage completed" line is the truncated value. The truncation happens
// here, beside the game, so the number the tracker shows is the number the menu
// shows rather than a second rounding of it.
#pragma once

namespace gtavc {

inline int DisplayedPercentage(float raw) {
  // Written as a positive test so a not-a-number reads as zero rather than
  // reaching the cast, where it would be undefined.
  if (!(raw > 0.0f)) return 0;
  if (raw >= 100.0f) return 100;
  return static_cast<int>(raw);
}

}  // namespace gtavc
