#pragma once
#include <filesystem>
#include <functional>
#include <string>
#include <stdexcept>

namespace gtavc {
// A fixed-length hash names a seed AND slot; server strings never become paths.
inline std::filesystem::path SeedSaveDirectory(const std::filesystem::path& documents,
                                               const std::string& hash) {
  if (hash.size() != 16 || hash.find_first_not_of("0123456789abcdef") != std::string::npos)
    throw std::runtime_error("Invalid save seed identity.");
  const auto result = documents / "AP_Seeds" / hash;
  if (!documents.is_absolute() || result.string().size() > 220)
    throw std::runtime_error("Vice City's save path is too long or not absolute.");
  return result;
}
bool InstallSaveIsolation(std::function<void(const std::string&)> log,
                          std::function<bool(const std::string&)> can_write);
bool PrepareSaveSeed(const std::string& hash); // network thread: request/ack only
void TickSaveIsolation();                    // game update, outside any active render frame
}
