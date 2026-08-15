// The central table of raw game addresses, for the few statics plugin-sdk
// does not expose. Every entry is pinned for one exact executable build by
// reversing, never guessed, and callers must check plugin::GetGameVersion()
// for that build before dereferencing, so a foreign executable never takes a
// stray write.
#pragma once

namespace gtavc {

// The music manager's radio retune press count (gNumRetunePresses in the
// decompilation), classic 1.0 executable only. Pinned from the executable:
// the single call site of CPad::ChangeStationJustDown (plugin-sdk 1.0 address
// 0x4AA590) is followed, after the police-radio and taxi-radio checks, by
// inc dword ptr [0x783998] and mov dword ptr [0x78399C], 20, matching the
// decompiled press handler (gNumRetunePresses++; gRetuneCounter = 20). Both
// statics sit in .bss and are referenced about twenty times across .text,
// consistent with the decompiled usage.
constexpr unsigned int kRetunePressesAddress10 = 0x783998;

}  // namespace gtavc
