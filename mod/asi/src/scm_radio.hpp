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

}  // namespace gtavc
