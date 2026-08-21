// Pure toast text handling, free of any game headers so the console self-test
// can exercise it without plugin-sdk or the game.
//
// A toast is one of the game's brief messages. The game keeps a pointer to the
// text of every message it has queued and displays them in sequence, so posting
// each pending line as its own message holds the screen for a multiple of a
// message's time. Lines pending together are joined into one message instead,
// and one message is posted at a time: the game's own queue is a few slots deep
// and refuses anything past them, so a backlog waits here, where nothing is lost.
#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace gtavc {

// How long a toast holds the screen, and the most text one may carry. The length
// bound keeps a message inside the buffer the game formats it through.
constexpr unsigned int kToastDurationMs = 4000;
constexpr std::size_t kToastMaxChars = 220;
// Messages one post may hand the game. One, because the game displays them in
// sequence anyway: posting a backlog at once only moves the wait into the game's
// own few-slot queue, which drops whatever does not fit. A line is never worth
// dropping, since the release lines are one-shot and carry the only explanation
// the player gets.
constexpr std::size_t kToastMessagesPerPost = 1;
// The most lines the queue holds. Reached only by a flood of inbound item
// toasts, whose full history the client window keeps anyway.
constexpr std::size_t kToastQueueMax = 32;

// Separates joined lines inside one message.
constexpr std::string_view kToastSeparator = "   ";

// One post: the messages to hand the game in order, and how many lines from the
// head of the queue they consumed. The rest of the queue stays for the next
// post, so `consumed` is always a prefix count.
struct ToastBatch {
  std::vector<std::string> messages;
  std::size_t consumed = 0;
};

inline ToastBatch PlanToastBatch(const std::vector<std::string>& pending,
                                 std::size_t max_chars,
                                 std::size_t max_messages) {
  ToastBatch batch;
  if (max_chars == 0 || max_messages == 0) return batch;
  std::string message;
  for (std::size_t index = 0; index < pending.size(); ++index) {
    const std::string& text = pending[index];
    // An empty line has nothing to show and would still hold a message slot
    // for its whole duration, so it is consumed and never posted.
    if (text.empty()) {
      batch.consumed = index + 1;
      continue;
    }
    if (!message.empty() &&
        message.size() + kToastSeparator.size() + text.size() > max_chars) {
      batch.messages.push_back(message);
      message.clear();
      if (batch.messages.size() >= max_messages) break;
    }
    if (!message.empty()) message += kToastSeparator;
    message += text;
    // A single line longer than one message is truncated rather than dropped,
    // so its opening words still reach the player.
    if (message.size() > max_chars) message.resize(max_chars);
    batch.consumed = index + 1;
  }
  if (!message.empty()) batch.messages.push_back(message);
  return batch;
}

}  // namespace gtavc
