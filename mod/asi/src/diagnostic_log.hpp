#pragma once

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <windows.h>
#include <bcrypt.h>

#pragma comment(lib, "bcrypt.lib")

namespace gtavc {

inline std::string DiagnosticPath(const std::filesystem::path& path) {
  const auto text = path.u8string();
  return std::string(reinterpret_cast<const char*>(text.data()), text.size());
}

inline std::string DiagnosticFileHash(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  if (!file) return "unavailable (open)";
  std::string bytes((std::istreambuf_iterator<char>(file)), {});
  if (file.bad()) return "unavailable (read)";
  unsigned char digest[32]{};
  if (BCryptHash(BCRYPT_SHA256_ALG_HANDLE, nullptr, 0,
                 reinterpret_cast<PUCHAR>(bytes.data()), static_cast<ULONG>(bytes.size()),
                 digest, sizeof(digest)) < 0) return "unavailable (SHA256)";
  std::string result;
  for (const auto byte : digest) {
    result += "0123456789abcdef"[byte >> 4];
    result += "0123456789abcdef"[byte & 15];
  }
  return result;
}

// fallback to localappdata if needed
inline std::filesystem::path OpenDiagnosticLog(const std::filesystem::path& primary,
                                              const std::filesystem::path& fallback,
                                              FILE*& file, std::string& problem) {
  problem.clear();
  const int error = _wfopen_s(&file, primary.c_str(), L"w");
  if (file != nullptr) return primary;
  problem = "Cannot open " + DiagnosticPath(primary) + "; errno=" + std::to_string(error);
  if (fallback.empty()) return {};
  std::error_code directory_error;
  std::filesystem::create_directories(fallback.parent_path(), directory_error);
  if (directory_error) {
    problem += "; fallback directory error=" + std::to_string(directory_error.value());
    return {};
  }
  const int fallback_error = _wfopen_s(&file, fallback.c_str(), L"w");
  if (file == nullptr) {
    problem += "; cannot open " + DiagnosticPath(fallback) + "; errno=" + std::to_string(fallback_error);
    return {};
  }
  return fallback;
}

}  // namespace gtavc
