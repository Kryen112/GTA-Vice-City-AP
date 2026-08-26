// Pure DeathLink planning, free of any game headers so the console self-test can
// exercise it without plugin-sdk or the game.
//
// Both directions live here. Outbound: the game's own wasted state is the only
// death, so an arrest is not one, and a death this mod caused is not reported
// back, or two linked slots would kill each other forever. Inbound: a linked
// death waits for the player to be controllable, the single deferral condition
// every AP-driven write shares, and is dropped rather than held when Tommy is
// already dying, since nobody dies twice and a held death would land on him at
// the hospital door.
#pragma once

namespace gtavc {

// What a frame does with a linked death the client forwarded.
enum class DeathLinkAction {
  // Nothing this frame: either none is pending, or the frame cannot deliver one
  // yet and it keeps its place.
  kHold,
  // Kill Tommy now.
  kKill,
  // Forget it: the death it asked for is already happening.
  kDrop,
};

// The window a kill this mod made waits for its own wasted state in, so that one
// death is not reported back to the world it came from. State rather than a
// deadline alone, because the arming and the two ways it ends are the whole echo
// guard and the only thing standing between two linked slots and a death that
// bounces between them forever. `until` is a real-millisecond clock reading and
// means nothing while `armed` is false.
struct DeathLinkEcho {
  bool armed = false;
  unsigned int until = 0;
};

// Whether the window is still holding at `now`. The difference is taken signed
// so the comparison survives the clock wrapping, the form the timed traps use.
inline bool DeathLinkEchoSuppressing(const DeathLinkEcho& echo, unsigned int now) {
  return echo.armed && static_cast<int>(now - echo.until) < 0;
}

// The window a kill arms: it expects the wasted state its own health write is
// about to cause, and gives up on it after `window_ms`.
inline DeathLinkEcho ArmDeathLinkEcho(unsigned int now, unsigned int window_ms) {
  return DeathLinkEcho{true, now + window_ms};
}

// The window after a frame that read the wasted state as `wasted` and read it
// last frame as `was_wasted`.
//
// It lives only until the death it was armed for turns up, so a second death
// moments later is a real one and reports. One condition covers both ways it
// ends: the wasted edge it was waiting for, and the deadline passing for a kill
// that never killed, which is what keeps a kill that did not take from swallowing
// the next real death.
inline DeathLinkEcho AdvanceDeathLinkEcho(const DeathLinkEcho& echo, unsigned int now,
                                          bool wasted, bool was_wasted) {
  if (!DeathLinkEchoSuppressing(echo, now) || (wasted && !was_wasted)) {
    return DeathLinkEcho{};
  }
  return echo;
}

// Whether this frame reports Tommy's death to the multiworld.
//
// `wasted` and `was_wasted` are the game's own wasted state this frame and last,
// so a death reports once on its edge rather than every frame of the fade.
// `echo_suppressed` is a kill this mod made and the wasted state it is waiting
// for; reporting that one would bounce the death back to whoever sent it.
// `client_connected` is the bridge being up, and a death is dropped without one
// rather than queued: it is a thing that happened to a player who was playing,
// and a death delivered minutes late is worse than one missed, which is the
// opposite of a location, whose queue is never dropped because a lost check
// makes the multiworld unbeatable.
inline bool ShouldReportDeath(bool wasted, bool was_wasted, bool echo_suppressed,
                              bool client_connected) {
  return wasted && !was_wasted && !echo_suppressed && client_connected;
}

// What to do with a linked death this frame.
//
// `pending` is a death the client forwarded that no frame has delivered yet.
// `playing` is the game's own player state reading as playing, so Tommy is
// neither dying nor under arrest nor being restarted after a failed mission.
// `player_present` is the player ped existing, so there is something to kill,
// and `controllable` is the flag every item application waits on.
//
// The already-dying test comes first deliberately. A player in the wasted fade
// is not controllable either, so asking about control first would hold the death
// through the fade and spend it on the frame Tommy walks out of the hospital.
//
// Every state but playing drops, arrest included. Each of them is the game taking
// Tommy away and bringing him back, and a death that waited for that would land
// on a player who has just been handed control with nothing on screen to explain
// it. A death missed that way costs a linked player nothing; a death landing
// there costs this one a run.
inline DeathLinkAction PlanDeathLink(bool pending, bool player_present,
                                     bool controllable, bool playing) {
  if (!pending) return DeathLinkAction::kHold;
  if (!playing) return DeathLinkAction::kDrop;
  if (!player_present || !controllable) return DeathLinkAction::kHold;
  return DeathLinkAction::kKill;
}

}  // namespace gtavc
