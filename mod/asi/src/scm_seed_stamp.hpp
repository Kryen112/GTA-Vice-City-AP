// Pure seed stamp planning, free of any game headers so the console self-test
// can exercise it without plugin-sdk or the game.
//
// The seed hash sits in the four lowest reserved globals, and it is what makes a
// running game this seed's: the frame handler touches no other script memory
// until it is there, the SCM's own watchers wait on it before latching
// anything, and the handshake presents it so a save from another multiworld is
// refused. Script space is loaded from main.scm and zero-initialized, so an
// empty hash in a running game says the world was just replaced and the frame
// that reads it writes the seed the client named.
//
// The stamp is therefore armed for as long as the session that named the seed is
// up. That session outlives the game: a player
// who starts a new game from the pause menu never handshakes again, and a game
// left unstamped is the worst state the mod has, because it is half a mod.
// main.scm still holds every gate it compiled in and the CLEO watchers still
// wait on the hash, so nothing unlocks, nothing is reported, and no item can
// arrive to open any of it.
//
// It is armed no LONGER than that session, though, because the seed a welcome
// named is only known to be the next game's seed while the client that named it
// is still there. A client that goes away can be replaced by one for another
// multiworld, and a game stamped with the seed before it presents a hash that
// client refuses, with nothing the player can do about it: the refusal asks for
// a new game, and every new game would carry the same stale hash. So a game
// started with no client waits, which is the state the mod already sits in
// before its first welcome and heals on the next one.
#pragma once

namespace gtavc {

// Whether this frame writes the seed hash into the game. `game_hash_empty` is
// the reserved globals reading zero, which only a game whose script space was
// just loaded does; `seed_known` is a welcome having named the hash to write;
// `client_connected` is that welcome's session still being up. A game carrying a
// DIFFERENT seed's hash is not empty, so it is never stamped over: refusing that
// save is the handshake's job.
inline bool ShouldStampSeedHash(bool game_hash_empty, bool seed_known,
                                bool client_connected) {
  return game_hash_empty && seed_known && client_connected;
}

}  // namespace gtavc
