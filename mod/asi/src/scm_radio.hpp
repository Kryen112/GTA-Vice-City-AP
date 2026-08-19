// Pure radio-station planning, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// With the randomize option on, only unlocked stations play. Vice City keys
// the radio off one byte per vehicle: 0..8 are the music stations, 9 the MP3
// player, 10 the off position (police vehicles ignore the byte and play the
// scanner). Vehicles spawn on a random station, the music manager reads the
// byte on entry and on a retune commit, and the retune cycle walks 0..10 with
// wraparound. Enforcement remaps every vehicle's byte through the resolve map
// below, and when the player's own vehicle lands on a locked station snaps it
// to the next stop of the cycle, off included so the radio can always be
// silenced. The MP3 player is excluded throughout.
#pragma once

#include <array>

namespace gtavc {

constexpr int kRadioStationCount = 9;
constexpr int kRadioUserTrack = 9;
constexpr int kRadioOff = 10;
// The wheel the retune commit wraps over: the nine stations, the MP3 player,
// and the off position.
constexpr int kRadioWheelPositions = kRadioOff + 1;

// station -> itself when unlocked, else the next unlocked station scanning
// upward with wraparound; identity when nothing is unlocked (the caller skips
// enforcement then). This is also the map the SCM's scripted
// set_radio_channel sites read: a forced station plays if unlocked, otherwise
// the next unlocked one.
inline std::array<int, kRadioStationCount> ResolveRadioStations(
    const std::array<bool, kRadioStationCount>& unlocked) {
  std::array<int, kRadioStationCount> resolve{};
  for (int station = 0; station < kRadioStationCount; ++station) {
    resolve[station] = station;
    for (int step = 0; step < kRadioStationCount; ++step) {
      const int candidate = (station + step) % kRadioStationCount;
      if (unlocked[candidate]) {
        resolve[station] = candidate;
        break;
      }
    }
  }
  return resolve;
}

// The station a parked or NPC vehicle's byte should read: the resolve map for
// a music station; a rolled MP3 player re-resolves from Wildstyle. The caller
// leaves the off position (and above) untouched.
inline int CorrectedVehicleStation(
    int station, const std::array<int, kRadioStationCount>& resolve) {
  return resolve[station < kRadioStationCount ? station : 0];
}

// The wheel position `presses` presses past `station`, in the vanilla
// eleven-position order.
inline int WheelPosition(int station, int presses) {
  return ((station + presses) % kRadioWheelPositions + kRadioWheelPositions) %
         kRadioWheelPositions;
}

// The next stop of the retune cycle after `station`: unlocked stations and
// the off position, in the vanilla 0..10 wrap order, with the MP3 player
// skipped. Returns kRadioOff when the off position comes first.
inline int NextAllowedTuning(
    int station, const std::array<bool, kRadioStationCount>& unlocked) {
  for (int step = 1; step <= kRadioWheelPositions; ++step) {
    const int candidate = WheelPosition(station, step);
    if (candidate == kRadioUserTrack) continue;
    if (candidate == kRadioOff) return kRadioOff;
    if (unlocked[candidate]) return candidate;
  }
  return kRadioOff;
}

// Where `presses` retune presses land from `station` when every press means
// one stop of the allowed cycle. Reduced modulo the cycle length (the
// unlocked stations plus the off position) so scroll-wheel bursts stay cheap
// and a full lap comes back around.
inline int AdvanceTuning(int station, int presses,
                         const std::array<bool, kRadioStationCount>& unlocked) {
  if (presses <= 0) return station;
  int cycle_length = 1;
  for (const bool station_unlocked : unlocked) {
    if (station_unlocked) ++cycle_length;
  }
  int remaining = ((presses - 1) % cycle_length) + 1;
  int position = station;
  while (remaining-- > 0) position = NextAllowedTuning(position, unlocked);
  return position;
}

// The raw press count that makes the vanilla retune commit land on `target`
// from `station`: the distance around the eleven-position wheel, a full lap
// when the target is the station itself (the commit's wrap arithmetic brings
// a lap back to the same station). The commit is a plain add-and-wrap with no
// user-track special case, so the distance is exact whether or not MP3 files
// exist.
inline int RetunePressesForTarget(int station, int target) {
  const int distance = ((target - station) % kRadioWheelPositions +
                        kRadioWheelPositions) % kRadioWheelPositions;
  return distance == 0 ? kRadioWheelPositions : distance;
}

// How many of the raw press counts strictly between `walked_from` and
// `walked_to` the game stepped on its own. With no MP3 folder installed the
// game skips the MP3 slot for the player: while a retune is pending, both the
// retune preview and the station-name display step the press count themselves
// whenever the pending wheel position lands there. A count that moved PAST that
// position therefore carries a press the player never made. Both ends of the
// interval stay out of the count, so a count resting ON the slot, which is what
// an installed MP3 folder leaves behind since then the game steps nothing, is
// left as the player's own.
//
// Closed form rather than a walk: the counts whose wheel position is the slot
// repeat once per lap, so the first one past `walked_from` fixes them all. The
// raw count comes out of game memory, and this way one stale value cannot cost
// a long loop inside a per-frame hook.
inline int UserTrackSkippedPresses(int station, int walked_from,
                                   int walked_to) {
  const int after = walked_from + 1;
  const int first = after + WheelPosition(kRadioUserTrack - station - after, 0);
  if (first >= walked_to) return 0;
  return (walked_to - 1 - first) / kRadioWheelPositions + 1;
}

// One frame of retune press shaping. Folds the raw press count read from the
// game into the accumulated logical press total (new raw presses beyond the
// count written last frame are fresh player input, minus the ones the game
// stepped itself to skip the MP3 slot; a raw count below the written one means
// a commit and a fresh scroll landed in one frame), then yields the raw count
// to write back so the vanilla commit lands on the allowed cycle. A raw count
// of zero or below means no scroll is pending and clears the accumulator.
struct RetunePressPlan {
  int logical_presses = 0;
  int written_presses = 0;
  bool write_needed = false;
};

inline RetunePressPlan PlanRetunePresses(
    int raw_presses, int logical_presses, int written_presses, int station,
    const std::array<bool, kRadioStationCount>& unlocked) {
  RetunePressPlan plan;
  if (raw_presses <= 0) return plan;
  if (raw_presses < written_presses) {
    logical_presses = 0;
    written_presses = 0;
  }
  logical_presses += raw_presses - written_presses -
                     UserTrackSkippedPresses(station, written_presses,
                                             raw_presses);
  const int target = AdvanceTuning(station, logical_presses, unlocked);
  plan.logical_presses = logical_presses;
  plan.written_presses = RetunePressesForTarget(station, target);
  plan.write_needed = plan.written_presses != raw_presses;
  return plan;
}

}  // namespace gtavc
