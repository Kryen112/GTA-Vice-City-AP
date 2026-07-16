// Standalone protocol self-test: round-trips framing (small and chunked) and
// checks the guards, with no socket and no game. Proves the C++ protocol layer
// compiles and behaves in the 32-bit MSVC toolchain.
#include <iostream>
#include <map>
#include <set>
#include <vector>

#include "../src/protocol.hpp"
#include "../src/scm_completion.hpp"
#include "../src/scm_packages.hpp"

using namespace gtavc;

namespace {

std::vector<json> RoundTrip(const json& message) {
  MessageWriter writer;
  MessageReader reader;
  std::vector<json> received;
  for (const std::string& frame : writer.Frames(message)) {
    for (json& decoded : reader.Feed(frame.data(), frame.size())) {
      received.push_back(std::move(decoded));
    }
  }
  return received;
}

int failures = 0;

void Expect(bool condition, const char* label) {
  if (!condition) {
    std::cerr << "FAIL: " << label << "\n";
    ++failures;
  }
}

}  // namespace

int main() {
  const json small = CheckMessage(542000000);
  const std::vector<json> small_result = RoundTrip(small);
  Expect(small_result.size() == 1 && small_result[0] == small, "small round-trip");

  json items = json::array();
  for (int index = 0; index < 5000; ++index) {
    items.push_back(json::array({index, index * 7}));
  }
  const json big = json{{"type", msg::kItems}, {"items", items}};
  const std::vector<std::string> frames = MessageWriter().Frames(big);
  Expect(frames.size() > 1, "large message chunks");
  for (const std::string& frame : frames) {
    Expect(frame.size() <= kMaxFrameBytes, "every frame within the size bound");
    Expect(!frame.empty() && frame.back() == '\n', "every frame ends in a newline");
  }
  const std::vector<json> big_result = RoundTrip(big);
  Expect(big_result.size() == 1 && big_result[0] == big, "chunked round-trip");

  bool threw = false;
  try {
    MessageReader reader;
    const std::string bad = "this is not json\n";
    reader.Feed(bad.data(), bad.size());
  } catch (const ProtocolError&) {
    threw = true;
  }
  Expect(threw, "malformed frame raises");

  // Completion detection: only a global that was zero at the baseline and is
  // now nonzero counts as a check. A global nonzero at the baseline (an
  // undeclared global reading leftover bytecode) is never reported, so an
  // incomplete main.scm cannot flood every location.
  {
    const std::map<int, std::int64_t> watch = {
        {9031, 542000000}, {9032, 542000001}, {9033, 542000002}};
    const std::map<int, int> baseline = {{9031, 0}, {9032, 0}, {9033, 12345}};
    std::set<int> reported;

    auto quiet = DetectCompletedLocations(watch, baseline, baseline, reported);
    Expect(quiet.empty(), "no checks when nothing changed from the baseline");

    std::map<int, int> current = {{9031, 1}, {9032, 0}, {9033, 99999}};
    auto first = DetectCompletedLocations(watch, baseline, current, reported);
    Expect(first.size() == 1 && first[0] == 542000000,
           "reports the zero-baseline global that went nonzero, not the garbage one");

    auto repeat = DetectCompletedLocations(watch, baseline, current, reported);
    Expect(repeat.empty(), "does not report a location twice");

    current[9032] = 4;
    auto later = DetectCompletedLocations(watch, baseline, current, reported);
    Expect(later.size() == 1 && later[0] == 542000001, "reports a later completion");
  }

  // Hidden-package detection: a package seen present this game and then gone is
  // collected, matched to the pickup pool by coordinate. Detection is per
  // package (by which coordinate vanished), never by collection order, and a
  // package never seen present or already recorded does not report.
  {
    const std::vector<PackageLocation> packages = {
        {9075, 10.0f, 10.0f, 10.0f},
        {9076, 100.0f, 100.0f, 100.0f},
        {9077, 200.0f, 200.0f, 200.0f}};
    const std::set<int> none;
    std::set<int> seen;

    const std::vector<WorldPoint> all = {
        {10.0f, 10.0f, 10.0f}, {100.0f, 100.0f, 100.0f}, {200.0f, 200.0f, 200.0f}};
    auto present = DetectNewlyCollectedPackages(packages, all, seen, none);
    Expect(present.empty(), "no package collected while all are present");
    Expect(seen.size() == 3, "every present package is marked seen");

    // The middle package vanishes: only its global reports, not the first by
    // placement order.
    const std::vector<WorldPoint> without_middle = {
        {10.0f, 10.0f, 10.0f}, {200.0f, 200.0f, 200.0f}};
    auto collected = DetectNewlyCollectedPackages(packages, without_middle, seen, none);
    Expect(collected.size() == 1 && collected[0] == 9076,
           "the specific vanished package reports, not by collection order");

    // Recorded as collected: it does not report again.
    const std::set<int> recorded = {9076};
    auto repeat = DetectNewlyCollectedPackages(packages, without_middle, seen, recorded);
    Expect(repeat.empty(), "an already-recorded package does not report again");

    // Gone but never seen present (unplaced pool or a save loaded with it
    // already gone) is not treated as collected.
    std::set<int> fresh;
    auto unseen = DetectNewlyCollectedPackages(packages, {}, fresh, none);
    Expect(unseen.empty(), "a package never seen present is not collected");

    // Match tolerance: within two units stays present, beyond counts as gone.
    std::set<int> one_seen = {9075};
    const std::vector<WorldPoint> near = {{11.5f, 10.0f, 10.0f}};
    auto near_result = DetectNewlyCollectedPackages({packages[0]}, near, one_seen, none);
    Expect(near_result.empty(), "a pickup within two units keeps the package present");
    const std::vector<WorldPoint> far = {{13.0f, 10.0f, 10.0f}};
    auto far_result = DetectNewlyCollectedPackages({packages[0]}, far, one_seen, none);
    Expect(far_result.size() == 1 && far_result[0] == 9075,
           "a pickup beyond two units leaves the package collected");
  }

  if (failures == 0) {
    std::cout << "OK: protocol self-test passed\n";
    return 0;
  }
  return 1;
}
