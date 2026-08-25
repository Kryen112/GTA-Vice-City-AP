// The mod side of the frozen mod-to-client protocol. Mirrors the Python
// protocol.py: newline-delimited JSON, base64 chunking for oversized frames,
// and the same message schema. This layer has no game dependency, so the
// console harness links it directly and verifies interop against the real
// Python bridge with no game running.
#pragma once

#include <cstddef>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

#include "json.hpp"

namespace gtavc {

using json = nlohmann::json;

constexpr int kProtocolVersion = 4;
constexpr std::size_t kMaxFrameBytes = 4096;
constexpr int kMaxChunkParts = 4096;
constexpr int kMaxChunksInFlight = 64;
constexpr std::size_t kMaxPendingBufferBytes = 1u << 20;

// Message type values, shared with protocol.py.
namespace msg {
constexpr const char* kWelcome = "welcome";
constexpr const char* kRefused = "refused";
constexpr const char* kConfig = "config";
constexpr const char* kItems = "items";
constexpr const char* kChecked = "checked";
constexpr const char* kToast = "toast";
constexpr const char* kStatus = "status";
constexpr const char* kHello = "hello";
constexpr const char* kCheck = "check";
constexpr const char* kGoalReached = "goal_reached";
constexpr const char* kProgress = "progress";
constexpr const char* kApplied = "applied";
}  // namespace msg

class ProtocolError : public std::runtime_error {
 public:
  explicit ProtocolError(const std::string& what) : std::runtime_error(what) {}
};

// Serializes a message into one or more newline-terminated frames, chunking
// anything too large for a single frame.
class MessageWriter {
 public:
  std::vector<std::string> Frames(const json& message);

 private:
  std::vector<std::string> ChunkFrames(const std::string& payload);
  std::int64_t next_chunk_id_ = 0;
};

// Accepts received bytes and yields complete messages, reassembling chunks.
class MessageReader {
 public:
  std::vector<json> Feed(const char* data, std::size_t length);

 private:
  struct ChunkEntry {
    int total = 0;
    std::map<int, std::string> parts;
  };

  bool DecodeLine(const std::string& line, json* out);
  bool AcceptChunk(const json& envelope, json* out);

  std::string buffer_;
  std::map<std::int64_t, ChunkEntry> chunks_;
};

// Message builders (ASI to client).
json HelloMessage(const std::string& presented_seed_hash);
json CheckMessage(std::int64_t location);
json GoalReachedMessage();
json ProgressMessage(int percentage);
json AppliedMessage(std::int64_t index);

}  // namespace gtavc
