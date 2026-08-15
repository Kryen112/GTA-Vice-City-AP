"""Locate the radio retune statics in the GTA Vice City 1.0 executable.

Anchor: CPad::ChangeStationJustDown at 0x4AA590 (plugin-sdk's own 1.0 table).
The music manager's press handler, per the reVC decompilation, runs

    if (CPad::GetPad(0)->ChangeStationJustDown()) {
        if (!UsesPoliceRadio(vehicle) && !UsesTaxiRadio(vehicle)) {
            gNumRetunePresses++;
            gRetuneCounter = 20;
            RadioStaticCounter = 0;
        }
    }

so within a short window after each call site there is a distinctive
`mov dword ptr [gRetuneCounter], 20` (C7 05 addr 14 00 00 00) beside an
`inc dword ptr [gNumRetunePresses]` (FF 05 addr) or add-by-one form. The
script finds every E8 call to the anchor, extracts those operands, and
cross-checks how often each candidate address is referenced text-wide.
"""
import struct
import sys

EXE = sys.argv[1]
ANCHOR_ADDRESS = 0x4AA590

with open(EXE, "rb") as handle:
    image = handle.read()

e_lfanew = struct.unpack_from("<I", image, 0x3C)[0]
machine, section_count = struct.unpack_from("<HH", image, e_lfanew + 4)[:2]
optional_size = struct.unpack_from("<H", image, e_lfanew + 20)[0]
image_base = struct.unpack_from("<I", image, e_lfanew + 24 + 28)[0]
section_table = e_lfanew + 24 + optional_size

sections = []
for index in range(section_count):
    offset = section_table + index * 40
    name = image[offset:offset + 8].rstrip(b"\0").decode("latin-1")
    virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
        "<IIII", image, offset + 8)
    sections.append((name, virtual_address, virtual_size, raw_pointer, raw_size))
    print(f"section {name:8s} address={image_base + virtual_address:#010x} "
          f"vsize={virtual_size:#x} raw={raw_pointer:#x}")

text = next(section for section in sections if section[0] == ".text")
text_address = image_base + text[1]
text_raw = text[3]
text_size = min(text[2], text[4])
body = image[text_raw:text_raw + text_size]

def address_of(raw_index):
    return text_address + raw_index

call_sites = []
position = 0
while True:
    position = body.find(b"\xE8", position)
    if position < 0 or position + 5 > len(body):
        break
    relative = struct.unpack_from("<i", body, position + 1)[0]
    if address_of(position) + 5 + relative == ANCHOR_ADDRESS:
        call_sites.append(position)
    position += 1

print(f"\ncall sites to {ANCHOR_ADDRESS:#x}: "
      f"{[hex(address_of(site)) for site in call_sites]}")

candidates = {}
for site in call_sites:
    window = body[site:site + 0x100]
    print(f"\n--- site {address_of(site):#x} window hex ---")
    print(window[:0xA0].hex(" "))
    for at in range(len(window) - 10):
        if window[at:at + 2] == b"\xC7\x05" and window[at + 6:at + 10] == b"\x14\x00\x00\x00":
            address = struct.unpack_from("<I", window, at + 2)[0]
            print(f"  mov dword [{address:#010x}], 20   at {address_of(site + at):#x}  -> gRetuneCounter?")
            candidates.setdefault("counter", set()).add(address)
    for at in range(len(window) - 6):
        if window[at:at + 2] == b"\xFF\x05":
            address = struct.unpack_from("<I", window, at + 2)[0]
            print(f"  inc dword [{address:#010x}]        at {address_of(site + at):#x}  -> gNumRetunePresses?")
            candidates.setdefault("presses", set()).add(address)
        if window[at:at + 2] == b"\x83\x05" and window[at + 6] == 1:
            address = struct.unpack_from("<I", window, at + 2)[0]
            print(f"  add dword [{address:#010x}], 1     at {address_of(site + at):#x}  -> gNumRetunePresses?")
            candidates.setdefault("presses", set()).add(address)

print("\nreference counts across .text (any instruction embedding the address):")
for label, addresses in candidates.items():
    for address in sorted(addresses):
        needle = struct.pack("<I", address)
        count = body.count(needle)
        print(f"  {label}: {address:#010x} referenced {count} times")
