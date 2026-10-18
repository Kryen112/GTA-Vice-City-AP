#pragma once
#include <windows.h>
#include <atomic>
#include <deque>
#include <functional>
#include <mutex>
#include <memory>
#include <string>
#include <optional>
#include "console_text.hpp"

namespace gtavc {
class ConsoleFont;
class IngameConsole {
 public:
  explicit IngameConsole(std::function<void(std::string)> send);
  ~IngameConsole();
  void Add(const std::string& text); // safe from the network thread
  void Add(const ConsoleMessage& message, bool notify = false);
  void SetCompletionNames(std::vector<std::string> items, std::vector<std::string> locations);
  void Draw(bool show_hint = false, bool connected = false); // game/menu drawing thread
  void BlockControls();
  bool IsOpen() const { return active_.load(); }
  void ReleaseGraphics(); // before RenderWare shuts down
 private:
  static LRESULT CALLBACK WindowProc(HWND, UINT, WPARAM, LPARAM);
  void Key(WPARAM key);
  void Scroll(int rows);
  void ClearHistory();
  bool CopySelection();
  static IngameConsole* instance_;
  HWND window_ = nullptr;
  WNDPROC previous_ = nullptr;
  std::atomic<bool> active_{false};
  ConsoleInput input_;
  ConsoleCommandCompletion completion_;
  std::optional<std::pair<std::vector<std::wstring>, std::vector<std::wstring>>> pending_completion_;
  ConsoleInputHistory input_history_;
  std::size_t scroll_ = 0;
  int wheel_delta_ = 0;
  wchar_t pending_surrogate_ = 0;
  std::mutex mutex_;
  std::deque<ConsoleLine> lines_;
  ConsolePopupQueue popups_;
  std::uint64_t next_line_id_ = 0;
  std::vector<ConsoleLine> wrapped_lines_;
  bool wrap_dirty_ = true;
  std::function<void(std::string)> send_;
  std::unique_ptr<ConsoleFont> font_;
};
}
