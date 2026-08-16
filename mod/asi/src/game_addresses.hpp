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

// The call site immediately before CWorld::Process inside CGame::Process,
// classic 1.0 executable only. Hooking it after the call gives the one point
// in the frame where a pad write still reaches the player: CGame::Process
// opens by calling CPad::UpdatePads (0x4A4412), which rebuilds the whole
// controller state from the devices, and CWorld::Process (0x4A45C8) is what
// runs the player ped's control, so a mask written anywhere after that (the
// gameProcessEvent handler included) is read by nobody and overwritten on
// the next frame.
//
// Pinned from the executable:
// - This call and the CWorld::Process call have exactly one caller each in
//   .text and sit in one run of back-to-back call instructions with no
//   branch target between them, so the hook runs once on every frame the
//   world processes.
// - Its callee, 0x624EC0, takes no arguments and cleans no stack (it opens
//   on a byte compare against a static and ends in a plain ret, never
//   touching ecx), which is what lets the hook declare it as a cdecl
//   zero-argument call; a thiscall or stack-argument callee would corrupt
//   the frame.
// - CTheScripts::Process (0x44FED0, plugin-sdk's version-detected address)
//   runs earlier in the same function, at 0x4A4501, so a script reading
//   buttons still sees the real pad and mission menus keep working.
//   plugin-sdk's processScriptsEvent names a different site, 0x4A45AA,
//   which calls 0x5A92E0 behind a conditional jump and so is not a
//   per-frame point; it also precedes this call.
constexpr unsigned int kBeforeWorldProcessCallSite10 = 0x4A45C3;

}  // namespace gtavc
