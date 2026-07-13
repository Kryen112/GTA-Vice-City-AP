#include "protocol.hpp"

#include <array>

namespace gtavc {
namespace {

constexpr const char* kChunkKey = "chunk";
const char kBase64Alphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

std::string Base64Encode(const std::string& input) {
  std::string output;
  output.reserve(((input.size() + 2) / 3) * 4);
  std::size_t index = 0;
  while (index + 3 <= input.size()) {
    const unsigned int triple = (static_cast<unsigned char>(input[index]) << 16) |
                                (static_cast<unsigned char>(input[index + 1]) << 8) |
                                static_cast<unsigned char>(input[index + 2]);
    output.push_back(kBase64Alphabet[(triple >> 18) & 0x3F]);
    output.push_back(kBase64Alphabet[(triple >> 12) & 0x3F]);
    output.push_back(kBase64Alphabet[(triple >> 6) & 0x3F]);
    output.push_back(kBase64Alphabet[triple & 0x3F]);
    index += 3;
  }
  const std::size_t remaining = input.size() - index;
  if (remaining == 1) {
    const unsigned int triple = static_cast<unsigned char>(input[index]) << 16;
    output.push_back(kBase64Alphabet[(triple >> 18) & 0x3F]);
    output.push_back(kBase64Alphabet[(triple >> 12) & 0x3F]);
    output.push_back('=');
    output.push_back('=');
  } else if (remaining == 2) {
    const unsigned int triple = (static_cast<unsigned char>(input[index]) << 16) |
                                (static_cast<unsigned char>(input[index + 1]) << 8);
    output.push_back(kBase64Alphabet[(triple >> 18) & 0x3F]);
    output.push_back(kBase64Alphabet[(triple >> 12) & 0x3F]);
    output.push_back(kBase64Alphabet[(triple >> 6) & 0x3F]);
    output.push_back('=');
  }
  return output;
}

int Base64Value(char character) {
  if (character >= 'A' && character <= 'Z') return character - 'A';
  if (character >= 'a' && character <= 'z') return character - 'a' + 26;
  if (character >= '0' && character <= '9') return character - '0' + 52;
  if (character == '+') return 62;
  if (character == '/') return 63;
  return -1;
}

std::string Base64Decode(const std::string& input) {
  std::string output;
  std::array<int, 4> quad{};
  int count = 0;
  for (const char character : input) {
    if (character == '=') break;
    const int value = Base64Value(character);
    if (value < 0) throw ProtocolError("invalid base64 in a chunked message");
    quad[count++] = value;
    if (count == 4) {
      output.push_back(static_cast<char>((quad[0] << 2) | (quad[1] >> 4)));
      output.push_back(static_cast<char>(((quad[1] & 0xF) << 4) | (quad[2] >> 2)));
      output.push_back(static_cast<char>(((quad[2] & 0x3) << 6) | quad[3]));
      count = 0;
    }
  }
  if (count == 2) {
    output.push_back(static_cast<char>((quad[0] << 2) | (quad[1] >> 4)));
  } else if (count == 3) {
    output.push_back(static_cast<char>((quad[0] << 2) | (quad[1] >> 4)));
    output.push_back(static_cast<char>(((quad[1] & 0xF) << 4) | (quad[2] >> 2)));
  }
  return output;
}

}  // namespace

std::vector<std::string> MessageWriter::Frames(const json& message) {
  const std::string payload = message.dump();
  if (payload.find('\n') != std::string::npos) {
    throw ProtocolError("a serialized message must not contain a newline");
  }
  if (payload.size() + 1 <= kMaxFrameBytes) {
    return {payload + "\n"};
  }
  return ChunkFrames(payload);
}

std::vector<std::string> MessageWriter::ChunkFrames(const std::string& payload) {
  const std::string encoded = Base64Encode(payload);
  const std::int64_t chunk_id = next_chunk_id_++;
  const std::size_t slice_size = kMaxFrameBytes - 256;
  const int total = static_cast<int>((encoded.size() + slice_size - 1) / slice_size);
  std::vector<std::string> frames;
  frames.reserve(total);
  for (int sequence = 0; sequence < total; ++sequence) {
    json envelope;
    envelope[kChunkKey] = chunk_id;
    envelope["seq"] = sequence;
    envelope["of"] = total;
    envelope["data"] = encoded.substr(sequence * slice_size, slice_size);
    frames.push_back(envelope.dump() + "\n");
  }
  return frames;
}

std::vector<json> MessageReader::Feed(const char* data, std::size_t length) {
  buffer_.append(data, length);
  if (buffer_.size() > kMaxPendingBufferBytes) {
    throw ProtocolError("inbound buffer exceeded the frame size limit");
  }
  std::vector<json> messages;
  std::size_t newline;
  while ((newline = buffer_.find('\n')) != std::string::npos) {
    const std::string line = buffer_.substr(0, newline);
    buffer_.erase(0, newline + 1);
    if (line.find_first_not_of(" \t\r") == std::string::npos) continue;
    json message;
    if (DecodeLine(line, &message)) messages.push_back(std::move(message));
  }
  return messages;
}

bool MessageReader::DecodeLine(const std::string& line, json* out) {
  json parsed = json::parse(line, nullptr, false);
  if (parsed.is_discarded() || !parsed.is_object()) {
    throw ProtocolError("a frame must be a JSON object");
  }
  if (parsed.contains(kChunkKey)) {
    return AcceptChunk(parsed, out);
  }
  *out = std::move(parsed);
  return true;
}

bool MessageReader::AcceptChunk(const json& envelope, json* out) {
  if (!envelope.contains("of") || !envelope.contains("seq") || !envelope.contains("data")) {
    throw ProtocolError("malformed chunk envelope");
  }
  const std::int64_t chunk_id = envelope[kChunkKey].get<std::int64_t>();
  const int total = envelope["of"].get<int>();
  const int sequence = envelope["seq"].get<int>();
  if (total < 1 || total > kMaxChunkParts) throw ProtocolError("invalid chunk count");
  if (sequence < 0 || sequence >= total) throw ProtocolError("invalid chunk sequence");
  ChunkEntry& entry = chunks_[chunk_id];
  if (entry.total == 0) entry.total = total;
  if (entry.total != total) throw ProtocolError("inconsistent chunk count across a message");
  entry.parts[sequence] = envelope["data"].get<std::string>();
  if (static_cast<int>(chunks_.size()) > kMaxChunksInFlight) {
    throw ProtocolError("too many chunked messages in flight");
  }
  if (static_cast<int>(entry.parts.size()) < total) return false;
  std::string encoded;
  for (int index = 0; index < total; ++index) encoded += entry.parts[index];
  chunks_.erase(chunk_id);
  json parsed = json::parse(Base64Decode(encoded), nullptr, false);
  if (parsed.is_discarded()) throw ProtocolError("invalid reassembled message");
  *out = std::move(parsed);
  return true;
}

json HelloMessage(const std::string& presented_seed_hash) {
  return json{{"type", msg::kHello}, {"protocol_version", kProtocolVersion},
              {"seed_hash", presented_seed_hash}};
}

json CheckMessage(std::int64_t location) {
  return json{{"type", msg::kCheck}, {"location", location}};
}

json GoalReachedMessage() { return json{{"type", msg::kGoalReached}}; }

json AppliedMessage(std::int64_t index) {
  return json{{"type", msg::kApplied}, {"index", index}};
}

}  // namespace gtavc
