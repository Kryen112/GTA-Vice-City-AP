#pragma once
#include <algorithm>
#include <cstdint>
#include <deque>
#include <functional>
#include <string>
#include <string_view>
#include <vector>

namespace gtavc {
struct ConsoleSpan {
  std::string text;
  std::uint32_t color = 0xFFFFFF;
};
using ConsoleMessage = std::vector<ConsoleSpan>;
using ConsoleOutput = std::function<void(const ConsoleMessage&, bool notify)>;

class ConsoleCommandCompletion {
  std::wstring prefix_;
  int selected_ = -1;
 public:
  void Reset() { prefix_.clear(); selected_ = -1; }
  bool Complete(std::wstring& text, std::size_t& cursor, bool reverse = false) {
    const auto end = std::min(text.find_first_of(L" \t\r\n"), text.size());
    if (cursor == 0 || cursor > end || (text[0] != L'/' && text[0] != L'!')) {
      Reset(); return false;
    }
    // Complete only command names; arguments and ordinary chat stay untouched.
    static constexpr std::wstring_view commands[] = {
        L"/commands", L"/connect", L"/deathlink", L"/disconnect", L"/help", L"/hint",
        L"/item_groups", L"/items", L"/location_groups", L"/locations", L"/password",
        L"/ready", L"/received", L"/server", L"/slot",
        L"!admin", L"!alias", L"!checked", L"!collect", L"!countdown", L"!getitem",
        L"!help", L"!hint", L"!hint_location", L"!license", L"!missing", L"!options",
        L"!players", L"!release", L"!remaining", L"!status"};
    if (prefix_.empty()) prefix_ = text.substr(0, cursor);
    std::vector<std::wstring_view> matches;
    for (const auto command : commands)
      if (command.substr(0, prefix_.size()) == prefix_) matches.push_back(command);
    if (matches.empty()) { Reset(); return false; }
    const auto count = static_cast<int>(matches.size());
    selected_ = selected_ < 0 ? (reverse ? count - 1 : 0) :
        (selected_ + (reverse ? -1 : 1) + count) % count;
    const auto match = matches[selected_];
    if (text.size() - end + match.size() > 1024) { Reset(); return false; }
    text.replace(0, end, match);
    cursor = match.size();
    return true;
  }
};

struct ConsoleLine {
  std::wstring text;
  std::vector<std::uint32_t> colors; // one color per UTF-16 code unit
  std::uint64_t popup_until = 0;
  std::uint64_t history_id = 0;
};

constexpr std::uint64_t kConsolePopupLifetimeMs = 3750; // 3 seconds, then a 750ms fade
inline int ConsolePopupAlpha(std::uint64_t until, std::uint64_t now) {
  if (now >= until) return 0;
  return static_cast<int>(255 * std::min<std::uint64_t>(750, until - now) / 750);
}

// Preserve colors while wrapping at words, or within an overlong word. Without
// a font measurement this supplies the network thread's bounded history rows.
inline std::vector<ConsoleLine> WrapConsoleText(const ConsoleLine& message, float width = 86,
    const std::function<float(std::wstring_view)>& measure = {}) {
  if (message.text.empty()) return {message};
  std::vector<ConsoleLine> lines;
  for (std::size_t offset = 0; offset < message.text.size();) {
    auto end = offset, space = std::wstring::npos;
    float used = 0;
    while (end < message.text.size() && message.text[end] != L'\n') {
      const auto c = message.text[end];
      const std::size_t units = c >= 0xD800 && c <= 0xDBFF && end + 1 < message.text.size() &&
          message.text[end + 1] >= 0xDC00 && message.text[end + 1] <= 0xDFFF ? 2 : 1;
      const auto glyph = std::wstring_view(message.text).substr(end, units);
      const float advance = measure ? measure(glyph) : static_cast<float>(units);
      if (used + advance > width && end > offset) break;
      if (c == L' ') space = end;
      used += advance;
      end += units;
    }
    if (end < message.text.size() && message.text[end] != L'\n' &&
        message.text[end] != L' ' && space != std::wstring::npos && space > offset) end = space;
    const auto count = end - offset;
    lines.push_back({message.text.substr(offset, count),
                     {message.colors.begin() + offset, message.colors.begin() + offset + count},
                     message.popup_until, message.history_id});
    offset += count;
    if (offset < message.text.size() && (message.text[offset] == L'\n' || message.text[offset] == L' ')) ++offset;
  }
  return lines;
}

class ConsolePopupQueue {
  std::deque<ConsoleLine> waiting_, visible_;
 public:
  void Add(const ConsoleLine& line) {
    // ponytail: bounded flood protection; raise this if real rooms exceed 4096 queued rows.
    if (waiting_.size() < 4096) waiting_.push_back(line);
  }
  bool empty() const { return waiting_.empty() && visible_.empty(); }
  void Pause(std::uint64_t now) {
    // Give visible rows their full reading time again after closing F8.
    for (auto& line : visible_) line.popup_until = now + kConsolePopupLifetimeMs;
  }
  const std::deque<ConsoleLine>& Advance(std::uint64_t now, float width,
      const std::function<float(std::wstring_view)>& measure = {}) {
    while (!visible_.empty() && visible_.front().popup_until <= now) visible_.pop_front();
    while (visible_.size() < 4 && !waiting_.empty()) {
      auto rows = WrapConsoleText(waiting_.front(), width, measure);
      waiting_.pop_front();
      // Continuations wait their turn too; no part of a long message is skipped.
      for (std::size_t i = rows.size(); i > 1; --i) waiting_.push_front(std::move(rows[i - 1]));
      rows.front().popup_until = now + kConsolePopupLifetimeMs;
      visible_.push_back(std::move(rows.front()));
    }
    return visible_;
  }
};

inline std::size_t ConsoleScrollAfterArrival(std::size_t scroll, std::size_t added_rows,
                                           std::size_t history_rows) {
  return scroll ? std::min(scroll + added_rows, history_rows > 18 ? history_rows - 18 : 0) : 0;
}
}  // namespace gtavc
