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

// The next stop of the retune cycle after `station`: unlocked stations and
// the off position, in the vanilla 0..10 wrap order, with the MP3 player
// skipped. Returns kRadioOff when the off position comes first.
inline int NextAllowedTuning(
    int station, const std::array<bool, kRadioStationCount>& unlocked) {
  for (int step = 1; step <= kRadioOff + 1; ++step) {
    const int candidate = (station + step) % (kRadioOff + 1);
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
  const int wheel_positions = kRadioOff + 1;
  const int distance =
      ((target - station) % wheel_positions + wheel_positions) % wheel_positions;
  return distance == 0 ? wheel_positions : distance;
}

// One frame of retune press shaping. Folds the raw press count read from the
// game into the accumulated logical press total (new raw presses beyond the
// count written last frame are fresh player input; a raw count below it means
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
  const int fresh = raw_presses - written_presses;
  if (fresh > 0) {
    logical_presses += fresh;
  } else if (fresh < 0) {
    logical_presses = raw_presses;
  }
  const int target = AdvanceTuning(station, logical_presses, unlocked);
  plan.logical_presses = logical_presses;
  plan.written_presses = RetunePressesForTarget(station, target);
  plan.write_needed = plan.written_presses != raw_presses;
  return plan;
}

}  // namespace gtavc
