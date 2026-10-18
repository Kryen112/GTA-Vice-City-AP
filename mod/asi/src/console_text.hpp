#pragma once
#include <algorithm>
#include <cstdint>
#include <cwctype>
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
using CompletionOutput = std::function<void(std::vector<std::string>, std::vector<std::string>)>;

inline bool SecretConsoleInput(std::wstring_view text) {
  const auto start = text.find_first_not_of(L" \t");
  if (start == std::wstring_view::npos) return false;
  text.remove_prefix(start);
  const auto end = text.find_first_of(L" \t");
  text = text.substr(0, end);
  const std::wstring_view password = L"/password";
  return text.size() == password.size() && std::equal(text.begin(), text.end(), password.begin(),
      [](wchar_t a, wchar_t b) { return std::towlower(a) == b; });
}

struct ConsoleInput {
  std::wstring text;
  std::size_t cursor = 0, anchor = 0;
  std::size_t Previous(std::size_t at) const {
    if (at) --at;
    if (at && text[at] >= 0xDC00 && text[at] <= 0xDFFF &&
        text[at - 1] >= 0xD800 && text[at - 1] <= 0xDBFF) --at;
    return at;
  }
  std::size_t Next(std::size_t at) const {
    if (at < text.size()) {
      const auto c = text[at++];
      if (c >= 0xD800 && c <= 0xDBFF && at < text.size() &&
          text[at] >= 0xDC00 && text[at] <= 0xDFFF) ++at;
    }
    return at;
  }
  void Move(bool right, bool selecting) {
    if (!selecting && cursor != anchor) cursor = right ? std::max(cursor, anchor) : std::min(cursor, anchor);
    else cursor = right ? Next(cursor) : Previous(cursor);
    if (!selecting) anchor = cursor;
  }
  void Edge(bool end, bool selecting) {
    cursor = end ? text.size() : 0;
    if (!selecting) anchor = cursor;
  }
  std::wstring Selected() const { return text.substr(std::min(cursor, anchor), std::max(cursor, anchor) - std::min(cursor, anchor)); }
  void Erase(bool backwards) {
    auto first = std::min(cursor, anchor), last = std::max(cursor, anchor);
    if (first == last) {
      if (backwards) first = Previous(first);
      else last = Next(last);
    }
    text.erase(first, last - first);
    cursor = anchor = first;
  }
  void Insert(std::wstring value) {
    // clipboard newlines stay within one command, never submit another message
    for (auto& c : value) if (c == L'\r' || c == L'\n' || c == L'\t') c = L' ';
    value.erase(std::remove_if(value.begin(), value.end(), [](wchar_t c) { return c < 32 || c == 127; }), value.end());
    if (value.empty()) return;
    const auto first = std::min(cursor, anchor), last = std::max(cursor, anchor);
    auto count = std::min(value.size(), 1024 - (text.size() - (last - first)));
    if (count && count < value.size() && value[count - 1] >= 0xD800 && value[count - 1] <= 0xDBFF &&
        value[count] >= 0xDC00 && value[count] <= 0xDFFF) --count;
    if (!count) return;
    text.replace(first, last - first, value, 0, count);
    cursor = anchor = first + count;
  }
  void Clear() { std::fill(text.begin(), text.end(), 0); text.clear(); cursor = anchor = 0; }
};

class ConsoleCommandCompletion {
  std::wstring prefix_;
  int selected_ = -1;
  bool arguments_ = false;
  bool cycling_ = false;
  std::vector<std::wstring_view> Matches(std::wstring_view prefix, std::wstring_view command,
                                       bool arguments) const {
    static constexpr std::wstring_view commands[] = {
        L"/clear", L"/commands", L"/connect", L"/deathlink", L"/disconnect", L"/help", L"/hint",
        L"/increasetimer", L"/item_groups", L"/items", L"/location_groups", L"/locations", L"/password",
        L"/port", L"/quit", L"/ready", L"/received", L"/server", L"/slot", L"/status", L"/unstuck",
        L"!admin", L"!alias", L"!checked", L"!collect", L"!countdown", L"!getitem",
        L"!help", L"!hint", L"!hint_location", L"!license", L"!missing", L"!options",
        L"!players", L"!release", L"!remaining", L"!status"};
    std::vector<std::wstring_view> matches;
    if (arguments) {
      if (command != L"!hint" && command != L"!hint_location") return matches;
      for (const auto& name : command == L"!hint" ? items : locations)
        if (name.size() >= prefix.size() && std::equal(prefix.begin(), prefix.end(), name.begin(),
            [](wchar_t a, wchar_t b) { return std::towlower(a) == std::towlower(b); })) matches.push_back(name);
    } else {
      for (const auto name : commands)
        if (name.size() >= prefix.size() && std::equal(prefix.begin(), prefix.end(), name.begin(),
            [](wchar_t a, wchar_t b) { return std::towlower(a) == b; })) matches.push_back(name);
    }
    return matches;
  }
 public:
  std::vector<std::wstring> items, locations;
  void Reset() { prefix_.clear(); selected_ = -1; cycling_ = false; }
  std::wstring Preview(const std::wstring& text, std::size_t cursor) const {
    if (cycling_ || text.empty() || cursor != text.size() || SecretConsoleInput(text)) return {};
    const auto end = std::min(text.find_first_of(L" \t\r\n"), text.size());
    const bool arguments = cursor > end;
    auto start = arguments ? text.find_first_not_of(L" \t\r\n", end) : 0;
    if (start == std::wstring::npos) start = cursor;
    const auto prefix = std::wstring_view(text).substr(start);
    const auto matches = Matches(prefix, std::wstring_view(text).substr(0, end), arguments);
    if (matches.empty() || start + matches.front().size() > 1024) return {};
    return std::wstring(matches.front().substr(prefix.size()));
  }
  bool Complete(std::wstring& text, std::size_t& cursor, bool reverse = false) {
    auto end = std::min(text.find_first_of(L" \t\r\n"), text.size());
    const bool arguments = cursor > end;
    const auto command = text.substr(0, end);
    if (cursor == 0 || cursor > text.size() || (text[0] != L'/' && text[0] != L'!') ||
        (arguments && command != L"!hint" && command != L"!hint_location")) {
      Reset(); return false;
    }
    if (arguments != arguments_) Reset();
    arguments_ = arguments;
    std::size_t start = 0;
    if (arguments) {
      start = text.find_first_not_of(L" \t\r\n", end);
      if (start == std::wstring::npos) start = cursor;
      if (cursor < start) { Reset(); return false; }
      end = text.size();
    }
    if (!cycling_) prefix_ = text.substr(start, cursor - start);
    const auto matches = Matches(prefix_, command, arguments);
    if (matches.empty()) { Reset(); return false; }
    const auto count = static_cast<int>(matches.size());
    selected_ = selected_ < 0 ? (reverse ? count - 1 : 0) :
        (selected_ + (reverse ? -1 : 1) + count) % count;
    auto match = matches[selected_];
    if (text.size() - (end - start) + match.size() > 1024) { Reset(); return false; }
    text.replace(start, end - start, match);
    cursor = start + match.size();
    cycling_ = true;
    return true;
  }
};

class ConsoleInputHistory {
  std::deque<std::wstring> entries_;
  std::size_t position_ = 0;
  std::wstring draft_;
 public:
  void Add(const std::wstring& text) {
    if (!text.empty() && !SecretConsoleInput(text)) {
      entries_.push_back(text);
      if (entries_.size() > 100) entries_.pop_front();
    }
    position_ = entries_.size();
    draft_.clear();
  }
  void Recall(bool older, std::wstring& text, std::size_t& cursor) {
    if (older) {
      if (!position_) return;
      if (position_ == entries_.size()) draft_ = SecretConsoleInput(text) ? L"" : text;
      --position_;
    } else {
      if (position_ == entries_.size()) return;
      ++position_;
    }
    text = position_ == entries_.size() ? draft_ : entries_[position_];
    cursor = text.size();
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
    // flood protection
    if (waiting_.size() < 4096) waiting_.push_back(line);
  }
  bool empty() const { return waiting_.empty() && visible_.empty(); }
  void Clear() {
    waiting_.clear();
    visible_.clear();
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

constexpr std::size_t kConsoleHistoryRows = 20;
inline std::size_t ConsoleScrollAfterArrival(std::size_t scroll, std::size_t added_rows,
                                           std::size_t history_rows) {
  return scroll ? std::min(scroll + added_rows, history_rows > kConsoleHistoryRows ? history_rows - kConsoleHistoryRows : 0) : 0;
}
}  // namespace gtavc
