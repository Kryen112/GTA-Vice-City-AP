#pragma once

#include <windows.h>
#include <charconv>
#include <filesystem>
#include <fstream>
#include <mutex>
#include "json.hpp"
#include "game_state.hpp"

namespace gtavc {

// The server and local cache only gain consumed receipt indices. A new GTA save
// does not clear either record, and another copy of a trap has a different index.
class TrapHistory {
  using Json = nlohmann::json;
  std::filesystem::path file_;
  std::mutex mutex_;
  Json consumed_ = Json::object(), remote_ = Json::object();
  bool ready_ = false;

  static Json Validate(Json value) {
    if (value.is_null()) return Json::object();
    if (!value.is_object()) throw std::runtime_error("Invalid consumed trap record");
    for (auto entry = value.begin(); entry != value.end(); ++entry) {
      std::int64_t index = -1;
      const auto& key = entry.key();
      const auto parsed = std::from_chars(key.data(), key.data() + key.size(), index);
      if (parsed.ec != std::errc() || parsed.ptr != key.data() + key.size() || index < 0 ||
          key != std::to_string(index) || !entry.value().is_boolean() || !entry.value().get<bool>())
        throw std::runtime_error("Invalid consumed trap receipt");
    }
    return value;
  }

  void Save(const Json& value) {
    std::filesystem::create_directories(file_.parent_path());
    const auto temporary = std::filesystem::path(file_.wstring() + L".tmp");
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    output.exceptions(std::ios::failbit | std::ios::badbit);
    output << value.dump();
    output.close();
    if (!MoveFileExW(temporary.c_str(), file_.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
      throw std::runtime_error("Cannot persist consumed traps");
  }

 public:
  explicit TrapHistory(std::filesystem::path file) : file_(std::move(file)) {
    if (std::filesystem::exists(file_)) {
      std::ifstream input(file_, std::ios::binary);
      consumed_ = Validate(Json::parse(input));
    }
  }

  void Merge(const Json& value) {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto remote = Validate(value);
    auto merged = consumed_;
    merged.update(remote);
    if (merged != consumed_) Save(merged);
    consumed_ = std::move(merged);
    remote_ = remote;
    ready_ = true;
  }

  Json Pending() {
    std::lock_guard<std::mutex> lock(mutex_);
    Json result = Json::object();
    if (ready_) for (auto entry = consumed_.begin(); entry != consumed_.end(); ++entry)
      if (!remote_.contains(entry.key())) result[entry.key()] = true;
    return result;
  }

  TrapAction Consume(std::int64_t index) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (index < 0) throw std::runtime_error("Invalid trap receipt index");
    if (!ready_) return TrapAction::kWait;
    const auto key = std::to_string(index);
    if (consumed_.contains(key)) return TrapAction::kSkip;
    auto updated = consumed_;
    updated[key] = true;
    // Commit before triggering so a crash cannot turn a consumed trap into a replay.
    Save(updated);
    consumed_ = std::move(updated);
    return TrapAction::kApply;
  }
};
}  // namespace gtavc
