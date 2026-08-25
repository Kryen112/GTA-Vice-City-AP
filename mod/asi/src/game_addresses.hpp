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

// The money counter's own text print inside CHud::Draw, classic 1.0 executable
// only. Pinned from the executable rather than guessed:
//
// - CHud::Draw (plugin-sdk 1.0 address 0x557320) reads m_nDisplayMoney three
//   times as an absolute, 0x94ADCC, which is CWorld::Players (0x94AD28) plus the
//   0xA4 that plugin-sdk's CPlayerInfo layout gives that field.
// - At 0x5581A8 it formats that value with the string at 0x697B48, "$%08d",
//   which is the only occurrence of that format in the whole image, and widens
//   the result at 0x552500.
// - It then sets FONT_HEADING (SetFontStyle(2)), right justification, the
//   counter's scale and its green, and computes the counter's own position:
//   x = width - width * 110 / 640, y = height * 43 / 448.
// - This is the call that prints it. Redirecting the call substitutes the text
//   and inherits every one of those, so the replacement lands exactly where the
//   amount would and looks like it belongs.
//
// The signature the replacement declares is read from the same place: the site
// holds E8 rel32 and is followed by add esp, 0xc, so three dword arguments,
// caller cleaned, which is cdecl; the pushes before it are the text, then y,
// then x, so the order is (x, y, text). Nothing in the image branches into the
// five patched bytes and the site is not inside a loop, so the patch covers
// exactly one instruction on one path. The callee below is what the site must
// already point at for the pin to be this call and not another; the installer
// checks it and refuses rather than forwarding blindly.
constexpr unsigned int kMoneyPrintCallSite10 = 0x55830F;
constexpr unsigned int kMoneyPrintCallee10 = 0x551040;

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

// The buffer CText::Get returns for a key its table does not carry, classic 1.0
// executable only. The status page needs to know whether its own key resolved,
// and a missing key is not an error the game reports: it formats a placeholder
// into one static buffer and returns that, so the test is the pointer.
//
// Pinned from the executable: CText::Get (0x584F30, plugin-sdk's own address)
// calls its key search and, when the search returns null, writes the formatted
// placeholder five wide characters at a time into 0xA10A74 and up, then loads
// exactly that address into eax and returns (0x584FD5, mov eax, 0xA10A74). The
// hit path returns the value pointer out of the table instead, which is inside
// the loaded text data and can never be this address.
//
// What that buffer holds in this build is an EMPTY string, not the "key missing"
// text the debug builds and the decompilation show: the call site formats with
// the string at 0x69A478, which is four zero bytes, and passes no argument
// besides the buffer. So a page whose key is missing draws nothing rather than a
// placeholder, which is what lets the status page paint over the gap.
constexpr unsigned int kMissingTextBuffer10 = 0xA10A74;

// The in-shop pickup purchase path, classic 1.0 executable only. What an in-shop
// pickup charges is decided on one straight run of code that this site sits on.
// Pinned by disassembling the build rather than guessed:
//
// - The purchase dispatches on the pickup's type byte, movzx eax, byte ptr
//   [esi+0x2e] at 0x440D26 then jmp dword ptr [eax*4+0x688464] at 0x440D36,
//   types 1 to 18. Type 1 is the in-shop branch and it lands at 0x440D3D.
// - Before the dispatch, edx holds the model id and the weapon type it prices
//   from is resolved into ebx. Three models take a fixed type, 0x68E928
//   (bodyarmour) and 0x68E924 (adrenaline) to 0x26 and 0x68E930 (health) to
//   0x25; model id -1 alone reaches the table at 0x6884AC, whose zeroth entry is
//   the xor ebx, ebx at 0x440D24, because 0x440D04 is lea eax,[edx+1]; test
//   eax,eax; ja and test clears the carry flag so ja is jne. Every other model
//   reaches mov ecx, [edx*4+0x92D4C8] at 0x440D14, which is
//   CModelInfo::ms_modelInfoPtrs, followed by the call below. edi carries that
//   value into the branch (mov edi, ebx at 0x440D2A).
// - The branch then prices from it twice, movsx eax, word ptr [edi*2+0x688000]
//   at 0x440D4A for the affordability test against player money at
//   [ebp+0x94ADC8], and again at 0x440DDA for the charge.
//
// So an in-shop pickup's price comes from a field of its model info, and that
// field is a weapon type only for a weapon model. For the AP check marker it is
// not: CSimpleModelInfo::Init zeroes [modelinfo+0x30] at 0x56F77E and the `bonus`
// model has no LOD parent to overwrite it with, so the marker resolves to weapon
// type 0 and CostOfWeapon[0] is 0. Unpatched, a stand showing the marker sells
// for nothing.
//
// This makes the price a chosen number instead of one read off a field that does
// not mean price for this model. Nothing is unsafe about the zero; what it is not
// is deliberate, and it would stop being zero if that model ever gained a LOD
// parent, at which point the field is a pointer and indexes the 40 entry table
// far out of range.
//
// The price is the ONLY thing the marker needs from this path. The rest of what
// an in-shop AP check wants, selling whatever state the player is in and handing
// over nothing, the build already does for this model: the full armour refusal at
// 0x440BD0 and the full health one at 0x440C1A are each gated on comparing the
// PICKUP's own model, held in ecx from 0x440B86, so neither matches the marker;
// and 0x43D910's arm at 0x43DA20 compares the model against the word at
// 0x68E934, which 0x4A8205 fills from the model named `bonus`, then plays a sound
// and returns 1 without granting anything, which sends the caller to the charge.
//
// The callee is a two instruction getter, mov eax, [ecx+0x30]; ret, so it takes
// its object in ecx and nothing on the stack, and the caller cleans nothing. A
// hook over the call therefore has to answer in eax and nothing else, and it is
// handed the same two things the getter was: ecx is the model info and edx still
// holds the model id from 0x440D14, untouched between there and the call.
constexpr unsigned int kPickupChargedPriceCallSite10 = 0x440D1B;
constexpr unsigned int kPickupChargedPriceCallEnd10 = 0x440D20;
constexpr unsigned int kPickupPriceGetterCallee10 = 0x629C20;

// esi holds the PICKUP being priced at this site, which is what lets a stand be
// priced from a type of its own rather than from the model showing on it. Read
// off the instructions either side of the call: 0x440D26 takes the pickup type
// from [esi+0x2e] and 0x440D5E takes its object from [esi+0x10], both the
// offsets plugin-sdk gives CPickup, and nothing between 0x440D14 and the call
// writes esi.

// The getter has nine callers and only the two pinned here are prices. Two more
// sit in the pickup update, 0x004408A9 and 0x00440A2F, and are deliberately left
// alone: neither indexes CostOfWeapon. The first compares the answer against
// 0x25 to sort a weapon from health or armour, the second hands it to
// 0x005D5710. Answering the marker there would tell those two it is the weapon
// its PRICE index names, when what they need to hear is that it is not a weapon
// at all, which the raw field already says.

// The same getter again, on the path deciding what an in-shop slot SHOWS rather
// than what it charges, classic 1.0 executable only. 0x43D3B0 builds a pickup's
// visible object and stamps the weapon cost onto it at +0x170; 0x43F050 copies
// that stamp into the table at 0x7E9B22 the price renderer reads. Only the
// in-shop type is stamped: the type jump table at 0x6883C8 is indexed by the
// type less one and sends type 1 alone to the stamp, and the per frame writer at
// 0x4401DA belongs to the locked property type, whose switch at 0x440087 indexes
// by the type less 0x10.
//
// It takes the same hook as the purchase site, for the same reasons: ecx is the
// model info from 0x43D827 and edx still holds the model id, put there by
// 0x43D81A and untouched in between. Without it the marker prices from the raw
// field, which is zero, so a slot shows nothing to pay and then charges what the
// purchase path answers.
constexpr unsigned int kPickupShownPriceCallSite10 = 0x43D82E;
constexpr unsigned int kPickupShownPriceCallEnd10 = 0x43D833;

// The pickup is reachable here too, but not in a register of its own: ebx points
// AT the pickup's object field, so the pickup is that field's offset below it.
//
// Proved from the call sites rather than inferred. This site is inside
// CPickup::GiveUsAPickUpObject (0x43D3B0), whose prologue takes its first stack
// argument into ebx at 0x43D3BB and keeps it (0x43D3CB, 0x43D45D and 0x43D4C5 all
// write the created object through it). That function has exactly three callers,
// 0x4401FF, 0x44170E and 0x441B53, and all three set the argument up the same
// way: `lea eax, [esi+0x10]` and `lea ecx, [esi+0x14]`, pushed as the two object
// out-parameters, with `mov ecx, esi` making the same esi the `this`. So ebx is
// the pickup's own pObject field at every call there is, and 0x10 is the offset
// plugin-sdk gives that field.
//
// [esp+4] holds the pickup outright at this site, being where the prologue saved
// `this`, and it is deliberately NOT what is read: a hook's view of esp depends
// on what the hook's own stub pushed, and ebx does not.
//
// The pool arithmetic behind the index is checked as well as bounded, so a build
// where this stopped being true answers -1 and the stand prices at the marker's
// figure rather than at some other stand's.

// The three models the purchase path prices WITHOUT consulting the model info,
// classic 1.0 executable only. Each holds a model id, filled at load from the
// name in data/maps/generic.ide, and each takes a fixed weapon type before the
// dispatch: 0x440CCA reads the first and 0x440CD5 sets 0x26, 0x440CE0 reads the
// second and 0x440CEB sets 0x25, 0x440CF2 reads the third and 0x440CFD sets 0x26.
// The model compared is the PICKUP OBJECT's, loaded at 0x440CC3 and 0x440CC6.
//
// Anything reporting what a stand charges has to know these, because the model
// info gives zero for a model one of them names. The ten ambient stands wear only
// these, seven health and three adrenaline.
//
// They are not all a stand can wear: the script's other four type-1 stands are
// the heavy weapons Phil sells, which price from the model info exactly as it
// stands, randomize_pickups can put any non-bribe model on an ambient stand, and
// a pending check puts the marker there.
//
// Those 14 script sites are ALL the in-shop pickups there are. No engine site
// makes one: every immediate-type call to CPickups::GenerateNewOne passes 2, 4, 6,
// 8, 0x10, 0x11 or 0x12, and the only two that take the type from a variable read
// it out of the script's own parameters. So the guns on an Ammu-Nation counter are
// not in-shop pickups, which an F8 dump inside one confirmed by returning the ten
// ambient stands and nothing else.
constexpr unsigned int kPickupBodyArmourModelAddress10 = 0x68E928;
constexpr unsigned int kPickupHealthModelAddress10 = 0x68E930;
constexpr unsigned int kPickupAdrenalineModelAddress10 = 0x68E924;
constexpr int kPickupBodyArmourWeaponType = 0x26;
constexpr int kPickupHealthWeaponType = 0x25;
constexpr int kPickupAdrenalineWeaponType = 0x26;

// CostOfWeapon, the in-shop price table both reads above index, classic 1.0
// executable only. An int16 array of 40 entries; the dump reads it so a shop's
// prices can be recorded beside its stock rather than looked up by hand.
constexpr unsigned int kCostOfWeaponAddress10 = 0x688000;
constexpr int kCostOfWeaponCount = 40;

// The FIRST of the two model gates that let a pickup be taken from a vehicle,
// classic 1.0 executable only. 0x0044065A loads the pickup object's model, this
// instruction loads the police bribe model, and 0x00440667 compares them: equal
// takes the branch consulting the vehicle argument at 0x0044066F, unequal leaves
// at 0x00440669.
//
// What it leaves for is NOT the on-foot path. 0x00440750 is a second gate of the
// same shape against the model at 0x0068E940, camerapickup, which consults the
// vehicle at 0x0044075B in its turn. So two models are drivable in a vanilla
// game, not one. The ordinary path begins after both, at 0x004407A0, where
// `cmp [esp+0xa0], 0` followed by a jump is what actually refuses a driver.
// Either gate would serve; this one is patched because a bribe is the pickup the
// player already knows can be taken from a car.
//
// Patched by supplying the comparison's LEFT side rather than by touching the
// comparison or the branch, so the game's own control flow is untouched: answer
// with the pickup's own model and the existing compare agrees. The gate is the
// seven bytes of this one instruction, and the bytes are checked before they are
// replaced, since a build holding something else here is not this instruction.
constexpr unsigned int kVehicleCollectGateSite10 = 0x44065E;
constexpr unsigned int kVehicleCollectGateEnd10 = 0x440665;
constexpr unsigned char kVehicleCollectGateBytes10[] = {
    0x0F, 0xB7, 0x05, 0x38, 0xE9, 0x68, 0x00};

// The police bribe model id, filled at load from the name in the IDE files. The
// gate above reads it, and so does the replacement, so a seed that never patches
// still compares what the game would have compared.
constexpr unsigned int kPickupBribeModelAddress10 = 0x68E938;

}  // namespace gtavc
