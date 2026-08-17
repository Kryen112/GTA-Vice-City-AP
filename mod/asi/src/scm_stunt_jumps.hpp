// Pure stunt jump table recovery, free of any game headers so the console
// self-test can exercise it without plugin-sdk or the game.
//
// The game holds its unique stunt jumps only as an array the jump manager
// builds on the heap at game start, so these read that array out of a block of
// live memory. Nothing offline carries the same positions: neither the SCM nor
// the executable defines them.
//
// What the array looks like is the manager's own record layout, stable across
// this game lineage: two bounding boxes, the landing camera, then the reward.
// The positions are matched as a shape rather than at fixed offsets, so a
// record this build pads differently still reads; only the reward is taken from
// where the layout says it sits, and the caller can turn that test off when
// requiring it finds nothing.
//
//     0x00  6 floats  start box, two opposite corners
//     0x18  6 floats  landing box, two opposite corners
//     0x30  3 floats  camera position
//     0x3C  int       reward
//     0x40  2 bytes   done, found
//
// A record is recognised by four tests: two boxes whose corners bracket a sane
// volume somewhere in the world, a camera position in the world, a reward that
// reads as a sum of money, and enough distinct values to be real places rather
// than a repeating pattern. Unrelated things still match, so the table is then
// picked out as a run of matches at one constant stride.
//
// The last two tests earn their place. A buffer of alternating plus and minus
// one matches the boxes and the camera at every offset, runs long, and carries a
// reward field holding a float's bits: without them it reads as a table.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <unordered_set>
#include <vector>

namespace gtavc {

// The floats one record carries: two boxes of six, then the camera.
constexpr std::size_t kStuntJumpFloats = 15;
// Vice City spans about two thousand units from the middle in each direction;
// the radar covers exactly that. A little over is allowed so a box corner just
// outside the map still reads as a position rather than as noise.
constexpr float kStuntJumpWorldLimit = 2100.0f;
// A jump's trigger and landing volumes are real rooms of space: never a point,
// never a district.
constexpr float kStuntJumpMinimumExtent = 0.5f;
constexpr float kStuntJumpMaximumExtent = 250.0f;
// The camera sits above the jump, so its height ranges wider than the ground.
constexpr float kStuntJumpCameraMinimumHeight = -200.0f;
constexpr float kStuntJumpCameraMaximumHeight = 1500.0f;
// The record stride the run search will consider. The known layout is 0x44;
// the bounds allow for a record this build pads differently.
constexpr std::size_t kStuntJumpMinimumStride = 48;
constexpr std::size_t kStuntJumpMaximumStride = 160;
// Below this a run is noise rather than the table. Vice City has 36 jumps, so
// a real find sits far above it; the margin lets a partly built table still
// report rather than vanish.
constexpr int kStuntJumpMinimumRun = 12;
// The reward is a sum of money, so it is a small count rather than a float's
// bits read as an integer. This is what separates a jump record from a buffer
// of unit vectors, whose reward field reads as plus or minus one billion.
constexpr int kStuntJumpMaximumReward = 1000000;
// A jump names fifteen positions across two volumes and a camera, so almost
// every one of them differs. A buffer holding a repeating pattern matches the
// box shape at every offset and carries only a handful of distinct values.
constexpr std::size_t kStuntJumpMinimumDistinctValues = 8;
// How many matches one block may yield before the scan gives up on it. A block
// densely full of the same shape is not the jump table, and collecting it all
// would be the one place this can exhaust a 32-bit address space.
constexpr std::size_t kStuntJumpRecordLimit = 200000;

// One place in memory whose shape matches a stunt jump record.
struct StuntJumpRecord {
  std::size_t offset = 0;
  std::array<float, kStuntJumpFloats> values{};
  int reward = 0;
};

// A run of records at one constant stride, which is what an array of them is.
struct StuntJumpRun {
  std::size_t offset = 0;
  std::size_t stride = 0;
  int count = 0;
};

// One block's best run with the records it names, kept so the dump can carry
// the runners-up alongside its first pick.
struct StuntJumpCandidate {
  StuntJumpRun run;
  std::uintptr_t base = 0;
  std::vector<StuntJumpRecord> records;
};

// How many runners-up the dump writes out.
constexpr std::size_t kStuntJumpAlternativesWritten = 3;

inline bool IsWorldCoordinate(float value) {
  // Rejects infinities and not-a-number as well, since both fail every compare.
  return value > -kStuntJumpWorldLimit && value < kStuntJumpWorldLimit;
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

inline bool LooksLikeStuntJumpCamera(const float* values) {
  return IsWorldCoordinate(values[0]) && IsWorldCoordinate(values[1]) &&
         values[2] > kStuntJumpCameraMinimumHeight &&
         values[2] < kStuntJumpCameraMaximumHeight;
}

inline bool LooksLikeStuntJumpReward(int reward) {
  return reward >= 0 && reward <= kStuntJumpMaximumReward;
}

// Whether a record's positions vary the way real places do. The box test alone
// passes any repeating pattern whose values sit a unit or two apart, which a
// buffer of unit vectors does at every single offset.
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

// The middle of a box given its two opposite corners.
inline std::array<float, 3> StuntJumpBoxCentre(const float* values) {
  return {(values[0] + values[3]) * 0.5f, (values[1] + values[4]) * 0.5f,
          (values[2] + values[5]) * 0.5f};
}

// Every place in a block of memory whose shape matches a record. Reads through
// memcpy because a heap block carries no alignment promise for our purposes.
//
// This walks every four-byte offset of every heap block the game holds, which
// is hundreds of megabytes, so the tests are ordered cheapest first: one float,
// then one box, then the rest. Almost every offset dies on the first compare.
inline std::vector<StuntJumpRecord> FindStuntJumpRecords(
    const unsigned char* bytes, std::size_t size, bool require_reward = true) {
  std::vector<StuntJumpRecord> records;
  constexpr std::size_t kNeeded = kStuntJumpFloats * sizeof(float) + sizeof(int);
  if (size < kNeeded) return records;
  for (std::size_t offset = 0; offset + kNeeded <= size; offset += sizeof(float)) {
    float first = 0.0f;
    std::memcpy(&first, bytes + offset, sizeof(first));
    if (!IsWorldCoordinate(first)) continue;
    std::array<float, kStuntJumpFloats> values{};
    std::memcpy(values.data(), bytes + offset, 6 * sizeof(float));
    if (!LooksLikeStuntJumpBox(values.data())) continue;
    std::memcpy(values.data() + 6, bytes + offset + 6 * sizeof(float),
                9 * sizeof(float));
    if (!LooksLikeStuntJumpBox(values.data() + 6)) continue;
    if (!LooksLikeStuntJumpCamera(values.data() + 12)) continue;
    StuntJumpRecord record;
    record.offset = offset;
    record.values = values;
    std::memcpy(&record.reward, bytes + offset + sizeof(values), sizeof(int));
    // Two compares before the thirty the distinct-values test costs, and the
    // pathological block is the one where every offset reaches this far.
    if (require_reward && !LooksLikeStuntJumpReward(record.reward)) continue;
    if (!HasEnoughDistinctValues(values.data(), values.size())) continue;
    records.push_back(record);
    if (records.size() >= kStuntJumpRecordLimit) break;
  }
  return records;
}

// The run of records spaced by one constant stride that best reads as the jump
// array. A run of exactly `wanted` records is the answer whenever one exists,
// since that is how many jumps the game says it built; otherwise the longest
// run stands in. Pass zero for `wanted` to take the longest outright.
//
// Length alone is not enough to go on: arrays of collision volumes have the
// same shape as a jump record and a longer one can share a memory block with
// the real table, so both candidates are tracked in the one pass.
inline StuntJumpRun BestStuntJumpRun(const std::vector<StuntJumpRecord>& records,
                                     int wanted) {
  std::unordered_set<std::size_t> offsets;
  offsets.reserve(records.size() * 2);
  for (const StuntJumpRecord& record : records) offsets.insert(record.offset);

  StuntJumpRun longest;
  StuntJumpRun matched;
  for (std::size_t first = 0; first < records.size(); ++first) {
    for (std::size_t second = first + 1; second < records.size(); ++second) {
      const std::size_t stride = records[second].offset - records[first].offset;
      if (stride < kStuntJumpMinimumStride) continue;
      if (stride > kStuntJumpMaximumStride) break;
      // Walk each run once, from the record that starts it. Without this a
      // dense regular array rewalks the same run from every member, which is
      // the difference between the search costing one pass per stride and
      // costing one per record per stride.
      if (records[first].offset >= stride &&
          offsets.count(records[first].offset - stride) != 0) {
        continue;
      }
      int count = 2;
      std::size_t next = records[second].offset + stride;
      while (offsets.count(next) != 0) {
        ++count;
        next += stride;
      }
      const StuntJumpRun run{records[first].offset, stride, count};
      if (wanted > 0 && count == wanted && matched.count == 0) matched = run;
      if (count > longest.count) longest = run;
    }
  }
  // Each run already starts at its first record, since a walk only begins where
  // nothing sits one stride back.
  return matched.count > 0 ? matched : longest;
}

// The records a run names, in array order. Takes `records` in ascending offset
// order, which is how FindStuntJumpRecords returns them.
inline std::vector<StuntJumpRecord> RecordsInRun(
    const std::vector<StuntJumpRecord>& records, const StuntJumpRun& run) {
  std::vector<StuntJumpRecord> found;
  if (run.count <= 0 || run.stride == 0) return found;
  std::size_t wanted = run.offset;
  for (const StuntJumpRecord& record : records) {
    if (record.offset != wanted) continue;
    found.push_back(record);
    if (static_cast<int>(found.size()) >= run.count) break;
    wanted += run.stride;
  }
  return found;
}

}  // namespace gtavc
