#pragma once
#include <windows.h>
#include <deque>
#include <functional>
#include <mutex>
#include <memory>
#include <string>
#include "console_text.hpp"

namespace gtavc {
class ConsoleFont;
class IngameConsole {
 public:
  explicit IngameConsole(std::function<void(std::string)> send);
  ~IngameConsole();
  void Add(const std::string& text); // safe from the network thread
  void Add(const ConsoleMessage& message, bool notify = false);
  void Draw(bool show_hint = false); // game/menu drawing thread
  void BlockControls();
  void ReleaseGraphics(); // before RenderWare shuts down
 private:
  static LRESULT CALLBACK WindowProc(HWND, UINT, WPARAM, LPARAM);
  void Key(WPARAM key);
  static IngameConsole* instance_;
  HWND window_ = nullptr;
  WNDPROC previous_ = nullptr;
  bool active_ = false;
  std::wstring input_;
  ConsoleCommandCompletion completion_;
  std::size_t cursor_ = 0, scroll_ = 0;
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
