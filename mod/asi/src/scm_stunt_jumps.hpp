// Pure stunt jump table recovery, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// The game holds its unique stunt jumps only as an array the jump manager
// builds on the heap at game start, so these read that array out of a block of
// live memory. Nothing offline carries the same positions: neither the SCM nor
// the executable defines them.
//
// The table is an array of world positions at a constant stride, thirty-something
// of them, spread right across Vice City. The search is built on those three
// properties. The heap holds many other arrays of positions, most of them one
// model's bounding volumes, which sit around that model's own origin and reach a
// few dozen units in total; a run has to cover the city to qualify.
//
// Every test that could reject a real jump belongs to the run rather than to a
// record, so one unusual jump can never split the array or shift the search onto
// the wrong field of it.
//
// The record layout is known, from the manager's own, stable across this game
// lineage: two bounding boxes, the landing camera, then the reward.
//
//     0x00  6 floats  start box, two opposite corners
//     0x18  6 floats  landing box, two opposite corners
//     0x30  3 floats  camera position
//     0x3C  int       reward
//     0x40  2 bytes   done, found
//
// It ranks one candidate above another and never rejects, so a build laying a
// record out differently still yields its table.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <unordered_map>
#include <vector>

namespace gtavc {

// The floats one record carries, on the known layout: two boxes then the camera.
constexpr std::size_t kStuntJumpFloats = 15;
// The bytes one record reads, floats and the reward behind them.
constexpr std::size_t kStuntJumpRecordBytes =
    kStuntJumpFloats * sizeof(float) + sizeof(int);
// Vice City spans about two thousand units from the middle in each direction;
// the radar covers exactly that. A little over is allowed so a position just
// outside the map still reads as a place rather than as noise.
constexpr float kStuntJumpWorldLimit = 2100.0f;
// Ground height ranges wide, and the camera sits above the jump.
constexpr float kStuntJumpMinimumHeight = -200.0f;
constexpr float kStuntJumpMaximumHeight = 1500.0f;
// A position this close to the origin is a model's own space rather than a place
// in the city, since Vice City's origin is open water between the islands. A run
// is judged on how many of its positions are out here, never one record alone.
constexpr float kStuntJumpOriginExclusion = 40.0f;
// How much of a run must lie away from the origin before it can be the table.
constexpr float kStuntJumpMinimumAwayFromOrigin = 0.75f;
// How far apart a run's positions must reach. The real table covers the city,
// thousands of units; an array of model bounds covers tens.
constexpr float kStuntJumpMinimumSpan = 800.0f;
// The record stride considered. The floor is the bytes a record occupies, since
// a shorter stride would mean records overlapping, which describes no layout;
// the ceiling leaves room for a record this build sizes generously.
constexpr std::size_t kStuntJumpMinimumStride = kStuntJumpRecordBytes;
constexpr std::size_t kStuntJumpMaximumStride = 400;
// Below this a run is noise rather than the table. Vice City has 36 jumps, so a
// real find sits above it; the margin lets a partly built table still report.
constexpr int kStuntJumpMinimumRun = 20;
// How many positions one block may yield before the scan gives up on it. Only
// an offset and two coordinates are held per position, so this bounds both the
// memory and the run search that follows.
constexpr std::size_t kStuntJumpPositionLimit = 400000;
// How many qualifying runs are kept while searching one block.
constexpr std::size_t kStuntJumpRunsPerBlock = 64;
// A reward is a sum of money, so it is a small count rather than a float's bits
// read as an integer. Ranking only.
constexpr int kStuntJumpMaximumReward = 1000000;
// A jump names five positions across fifteen floats, so most of them differ.
// Ranking only.
constexpr std::size_t kStuntJumpMinimumDistinctValues = 8;
// A jump's trigger and landing volumes are real rooms of space. Ranking only.
constexpr float kStuntJumpMinimumExtent = 0.5f;
constexpr float kStuntJumpMaximumExtent = 500.0f;
// How many runners-up the dump writes out, and how many rows each one writes.
constexpr std::size_t kStuntJumpAlternativesWritten = 6;
constexpr std::size_t kStuntJumpRowsWritten = 60;
// How many candidates are carried while scanning, before the file keeps the
// best few. Ranking can only choose among what survives the trim.
constexpr std::size_t kStuntJumpCandidatesKept = 40;

// One place in memory holding a world position, kept small because a block can
// hold hundreds of thousands of them.
struct StuntJumpPosition {
  std::size_t offset = 0;
  float x = 0.0f;
  float y = 0.0f;
};

// One record read in full, once its run has been chosen.
struct StuntJumpRecord {
  std::size_t offset = 0;
  std::array<float, kStuntJumpFloats> values{};
  int reward = 0;
};

// A run of positions at one constant stride, which is what an array of them is.
struct StuntJumpRun {
  std::size_t offset = 0;
  std::size_t stride = 0;
  int count = 0;
  float span = 0.0f;
  float away_from_origin = 0.0f;
};

// One block's run with the records it names, ready to rank against another's.
struct StuntJumpCandidate {
  StuntJumpRun run;
  std::uintptr_t base = 0;
  std::vector<StuntJumpRecord> records;
  float layout_fit = 0.0f;
};

inline bool IsWorldCoordinate(float value) {
  // Rejects infinities and not-a-number as well, since both fail every compare.
  return value > -kStuntJumpWorldLimit && value < kStuntJumpWorldLimit;
}

// Whether three floats name a place anywhere in the world. Three zeroes are the
// one position refused: that is what unwritten memory reads as, and taking it
// would make every zeroed page an array of positions.
inline bool LooksLikeWorldPosition(const float* values) {
  if (values[0] == 0.0f && values[1] == 0.0f && values[2] == 0.0f) return false;
  return IsWorldCoordinate(values[0]) && IsWorldCoordinate(values[1]) &&
         values[2] > kStuntJumpMinimumHeight && values[2] < kStuntJumpMaximumHeight;
}

inline bool IsAwayFromOrigin(float x, float y) {
  const float distance_x = x < 0.0f ? -x : x;
  const float distance_y = y < 0.0f ? -y : y;
  return distance_x > kStuntJumpOriginExclusion ||
         distance_y > kStuntJumpOriginExclusion;
}

// Whether six floats read as two opposite corners of a sane volume. The corner
// order is not assumed: the manager stores a minimum and a maximum, but which
// comes first does not change what the box is.
inline bool LooksLikeStuntJumpBox(const float* values) {
  for (int axis = 0; axis < 3; ++axis) {
    const float low = values[axis];
    const float high = values[axis + 3];
    if (!IsWorldCoordinate(low) || !IsWorldCoordinate(high)) return false;
    const float extent = high > low ? high - low : low - high;
    if (extent < kStuntJumpMinimumExtent || extent > kStuntJumpMaximumExtent) {
      return false;
    }
  }
  return true;
}

inline bool LooksLikeStuntJumpReward(int reward) {
  return reward >= 0 && reward <= kStuntJumpMaximumReward;
}

// Whether a record's values vary the way real places do, rather than repeating.
inline bool HasEnoughDistinctValues(const float* values, std::size_t count) {
  std::size_t distinct = 0;
  for (std::size_t index = 0; index < count; ++index) {
    bool seen = false;
    for (std::size_t earlier = 0; earlier < index; ++earlier) {
      if (values[earlier] == values[index]) {
        seen = true;
        break;
      }
    }
    if (!seen) ++distinct;
  }
  return distinct >= kStuntJumpMinimumDistinctValues;
}

// Whether one record matches the manager's own layout in every particular.
inline bool FitsKnownStuntJumpLayout(const StuntJumpRecord& record) {
  return LooksLikeStuntJumpBox(record.values.data()) &&
         LooksLikeStuntJumpBox(record.values.data() + 6) &&
         LooksLikeStuntJumpReward(record.reward) &&
         HasEnoughDistinctValues(record.values.data(), record.values.size());
}

// What share of a run's records match that layout. A fraction rather than a
// verdict, so one unusual jump costs a candidate a little rather than all of it.
inline float LayoutFit(const std::vector<StuntJumpRecord>& records) {
  if (records.empty()) return 0.0f;
  std::size_t fitting = 0;
  for (const StuntJumpRecord& record : records) {
    if (FitsKnownStuntJumpLayout(record)) ++fitting;
  }
  return static_cast<float>(fitting) / static_cast<float>(records.size());
}

// Every place in a block of memory holding a world position. Reads through
// memcpy because a heap block carries no alignment promise for our purposes.
//
// This walks every four-byte offset of every heap block the game holds, which is
// hundreds of megabytes, so the two horizontal coordinates are tested first and
// reject almost every offset between them.
inline std::vector<StuntJumpPosition> FindStuntJumpPositions(
    const unsigned char* bytes, std::size_t size) {
  std::vector<StuntJumpPosition> positions;
  if (size < kStuntJumpRecordBytes) return positions;
  for (std::size_t offset = 0; offset + kStuntJumpRecordBytes <= size;
       offset += sizeof(float)) {
    float triple[3] = {0.0f, 0.0f, 0.0f};
    std::memcpy(triple, bytes + offset, sizeof(triple));
    if (!LooksLikeWorldPosition(triple)) continue;
    positions.push_back({offset, triple[0], triple[1]});
    if (positions.size() >= kStuntJumpPositionLimit) break;
  }
  return positions;
}

// One record read in full at an offset.
inline StuntJumpRecord ReadStuntJumpRecord(const unsigned char* bytes,
                                           std::size_t offset) {
  StuntJumpRecord record;
  record.offset = offset;
  std::memcpy(record.values.data(), bytes + offset, sizeof(record.values));
  std::memcpy(&record.reward, bytes + offset + sizeof(record.values), sizeof(int));
  return record;
}

// Every run in a block that could be the table: enough records, reaching across
// the city, and mostly away from any model's own origin. Runs are returned in
// the order found and the caller ranks them, so one block can offer more than
// one candidate and a decoy at a lower address cannot shadow the table.
inline std::vector<StuntJumpRun> FindStuntJumpRuns(
    const std::vector<StuntJumpPosition>& positions) {
  std::vector<StuntJumpRun> runs;
  std::unordered_map<std::size_t, std::size_t> index_of;
  index_of.reserve(positions.size() * 2);
  for (std::size_t index = 0; index < positions.size(); ++index) {
    index_of.emplace(positions[index].offset, index);
  }

  for (std::size_t first = 0; first < positions.size(); ++first) {
    for (std::size_t second = first + 1; second < positions.size(); ++second) {
      const std::size_t stride = positions[second].offset - positions[first].offset;
      if (stride < kStuntJumpMinimumStride) continue;
      if (stride > kStuntJumpMaximumStride) break;
      // Walk each run once, from the position that starts it. Without this a
      // dense regular array rewalks the same run from every member.
      if (positions[first].offset >= stride &&
          index_of.count(positions[first].offset - stride) != 0) {
        continue;
      }
      int count = 2;
      std::size_t next = positions[second].offset + stride;
      while (index_of.count(next) != 0) {
        ++count;
        next += stride;
      }
      if (count < kStuntJumpMinimumRun) continue;

      // Measure the run over its own members, which needs them found again;
      // only runs long enough to matter reach here, so this is rare.
      float lowest_x = 0.0f, highest_x = 0.0f, lowest_y = 0.0f, highest_y = 0.0f;
      int away = 0;
      bool started = false;
      for (int step = 0; step < count; ++step) {
        const auto found =
            index_of.find(positions[first].offset + stride * step);
        if (found == index_of.end()) continue;
        const StuntJumpPosition& position = positions[found->second];
        if (!started) {
          lowest_x = highest_x = position.x;
          lowest_y = highest_y = position.y;
          started = true;
        }
        lowest_x = position.x < lowest_x ? position.x : lowest_x;
        highest_x = position.x > highest_x ? position.x : highest_x;
        lowest_y = position.y < lowest_y ? position.y : lowest_y;
        highest_y = position.y > highest_y ? position.y : highest_y;
        if (IsAwayFromOrigin(position.x, position.y)) ++away;
      }
      const float span_x = highest_x - lowest_x;
      const float span_y = highest_y - lowest_y;
      const float span = span_x > span_y ? span_x : span_y;
      const float away_share = static_cast<float>(away) / static_cast<float>(count);
      if (span < kStuntJumpMinimumSpan) continue;
      if (away_share < kStuntJumpMinimumAwayFromOrigin) continue;
      runs.push_back({positions[first].offset, stride, count, span, away_share});
      if (runs.size() >= kStuntJumpRunsPerBlock) return runs;
    }
  }
  return runs;
}

// What ranks one candidate above another: how closely its records match the
// manager's own layout, then being as long as the game's own count, then
// reaching furthest, then the lower address so two sessions agree.
//
// Fit leads because the heap holds a great many arrays of world positions and
// the count does not tell them apart: a spatial grid and a table of jumps can
// both hold exactly as many entries as the game reports. Only fit says whether
// the floats form a jump. It sorts rather than rejects, so a build laying a
// record out differently still surfaces its best candidate.
inline bool CandidateRanksBefore(const StuntJumpCandidate& left,
                                 const StuntJumpCandidate& right, int wanted) {
  if (left.layout_fit != right.layout_fit) return left.layout_fit > right.layout_fit;
  const bool left_matches = wanted > 0 && left.run.count == wanted;
  const bool right_matches = wanted > 0 && right.run.count == wanted;
  if (left_matches != right_matches) return left_matches;
  if (left.run.span != right.run.span) return left.run.span > right.run.span;
  return left.base + left.run.offset < right.base + right.run.offset;
}

}  // namespace gtavc
