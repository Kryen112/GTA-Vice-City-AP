// Pure finale warp planning, free of any game headers so the console self-test
// can exercise it without plugin-sdk or the game.
//
// The hidden-packages goal is a macguffin hunt, so its last fragment plays the
// story's ending: the client asks for it on every status frame and the mod
// raises the warp flag the script's APFIN watcher polls. The ask waits for the
// player to be controllable, the one deferral point every AP-driven write
// shares, which costs nothing here because none of the watcher's own launch
// conditions can hold before control does.
#pragma once

namespace gtavc {

// Whether this frame raises the finale warp flag. `asked` is the client's
// standing request, repeated for as long as the goal holds so a load or a
// reconnect re-arms it; `controllable` is the game's own player-not-controllable
// flag, read the same way every item application reads it.
inline bool ShouldRaiseFinaleWarp(bool asked, bool controllable) {
  return asked && controllable;
}

}  // namespace gtavc
