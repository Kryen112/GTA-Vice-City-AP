#pragma once

namespace gtavc {

inline bool CanUnstuck(bool playing, bool exterior, bool on_foot,
                       bool controllable, bool paused, bool camera_transition) {
  return playing && exterior && on_foot && controllable && !paused && !camera_transition;
}

// Separate from the native camera, garage, script and cutscene control bits.
class UnstuckControlHold {
  static constexpr short kControlBit = 0x4000;
  int frames_ = 0;
 public:
  bool Begin(short& controls) {
    if (controls != 0 || frames_ != 0) return false;
    controls |= kControlBit;
    frames_ = 2;
    return true;
  }
  void Tick(short& controls, bool paused) {
    if (frames_ == 0 || paused) return;
    if (frames_ == 1) Reset(controls);
    else --frames_;
  }
  void Reset(short& controls) {
    if (frames_ != 0) controls &= ~kControlBit;
    frames_ = 0;
  }
};

}  // namespace gtavc
