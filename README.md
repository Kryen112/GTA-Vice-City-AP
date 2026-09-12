# GTA: Vice City (Archipelago world)

An Archipelago world plus in-game mod for GTA: Vice City (classic PC,
executable 1.0). It turns Vice City into a multiworld game.

Current release: v1.0.0.

## What randomization does

Missions no longer unlock each other. Every mission giver's strand opens one
mission at a time, and only when the multiworld sends the progressive unlock
for that giver, so the seed decides the order you play the city in rather than
the story. Crossing to the mainland is an item, and so is Starfish Island. The
bridges stay shut until the multiworld hands you the way over.

Missions and activities stop paying their vanilla rewards. The check is the
reward, and the money a mission would have paid goes back into the item pool as
filler. The one mission that needs no item is the first Rosenberg meeting,
which is open on a new game and is where every seed starts.

## Checks

492 with every class enabled. Story missions are always on. Every other class is
a YAML toggle, and a disabled class behaves fully vanilla, keeping its own
rewards and holding no checks.

| Check class | Checks |
| --- | --- |
| Story missions | 44 |
| Hidden packages | 100 |
| Rampages | 35 |
| Unique stunt jumps | 36 |
| Emergency vehicle milestones | 56 |
| Properties and venue missions | 40 |
| Robbable stores | 15 |
| Side events | 14 |
| Ambient pickups | 116 |
| Shop items | 36 |

The emergency milestones are per level. The side events are the stadium events,
the chopper checkpoints, the RC missions, Cone Crazy, PCJ Playground, Trial by
Dirt and Test Track.

## Goals

- **Final mission.** Complete "Keep Your Friends Close...".
- **Hidden package hunt.** Receive a configurable number of Package Fragments
  from the multiworld, the macguffin of this world. Collecting a Hidden Package
  in game stays an ordinary check and is never goal progress.
- **The game's own 100 percent.** The completion percentage Vice City itself
  tracks.

## Options

**Ability locks.** Sprint, jump, crouch, vehicles, weapon equipping and your
wallet can each be taken away and put in the pool. Vehicles split into land, sea
and air. With the wallet locked, cash is void until it arrives.

**Content locks.** Hidden packages, rampages, stunt jumps, properties and
robbable stores can be held inert until their item arrives. Split them
city-wide, per district, or per district per class.

**Shuffles.** The 9 radio stations become items, and you start with one. The
minimap can start hidden. The ambient pickups can trade places among themselves.
The five emergency vehicle finish rewards can go into the pool.

**Traps** take a configurable share of the filler, default 15 percent, spread
over seven types. **DeathLink** is supported and off by default. It sends on
Wasted only, so an arrest is not a death.

## In game

Enabled, unfinished non-mission checks appear on the minimap and pause-menu map as colored dots.
Packages are green, robberies light red, rampages dark red, pickups orange, stunt jumps blue,
properties yellow, side events cyan, and shop stock purple.
Dots disappear when checked. Content-locked checks stay hidden until their content is unlocked.
Markers also follow the world's mission, ability and region requirements, including alternative vehicle routes and their sources.

The ASI connects directly to Archipelago using
[N00byKing's APCpp C++ library](https://github.com/N00byKing/APCpp). Set `server`,
`slot`, and optional `password` under `[archipelago]` in `GtaVcAp.VC.ini` beside
the ASI, then launch the game. Archipelago Launcher provides **GTA Vice City Setup**
for offline installation; the legacy Python client is no longer included. Unacknowledged checks are saved in
`%LOCALAPPDATA%/GtaVcAp/GtaVcAp.<seed-hash>.json` and replayed after reconnecting.
Existing check files beside the ASI are copied automatically without overwriting newer state.

Use `host:port` for the server (`127.0.0.1:38281` for a local room). Remote hosts
use TLS; an explicit `ws://host:port` selects an unencrypted server, and
`wss://host:port` selects TLS. Passwords entered with `/password` stay in memory for this run. An optional
password in the INI is stored as plain text. TLS never falls back to an unencrypted connection.

Press **F8** in the main menu or in game for the built-in console. Set a connection
with `/server HOST:PORT`, `/slot NAME`, optional `/password PASSWORD`, then `/connect`.
The server and slot are remembered in `%LOCALAPPDATA%/GtaVcAp/connection.ini`,
which takes precedence over the beside-ASI INI defaults. Changing server or slot
clears the in-memory password; enter it afterwards if needed. `/disconnect` stops the connection; `/connect`
retries. Type normally to chat, use `!help` for server commands, `/hint [item]`
for hints, and `/deathlink [on|off|seed]` to control DeathLink or restore the seed's setting.
The console displays other players' chat, hints, countdowns, releases and goal messages. Page Up/Down scroll the view, Ctrl+V pastes, Enter sends, and F8/Escape closes the console.
Tab completes `/` and  `!` command names, Shift+Tab cycles backwards.

Client commands also include `/ready` to toggle ready status and `/received [page]`
to review received items with their sender and source. `/items [page] [filter]`
and `/locations [page] [filter]` search the game's full name catalogs,
`/item_groups [page] [group]` and `/location_groups [page] [group]` list the server's group names or the members of an exact group name.
Lists show 20 results per page in the console without generating popups.
For example, use `/locations 1 Ocean Beach` or
`/item_groups Weapons`.
Use `!missing [filter]`, `!checked [filter]`, and `!hint` for the server's check lists and existing hints.

Saves automatically use `GTA Vice City User Files/AP_Seeds/<seed-and-slot-hash>`.
Career saves and `gta_vc.set` remain in place. Connect before loading or saving;
the ASI blocks save access until the seed is known. The selected folder stays
active across disconnects. Restart the game to change seed or slot.
Installation/update/removal remains in the launcher's Python setup; `/play` and
`/setfolder` are unnecessary inside the running game.

Server messages appear in a popup queue with up to four lines visible.
Opening the console pauses the queue.
Items apply when the game is playable, including during missions.

The pause menu carries an ARCHIPELAGO page above Quit Game: client connection,
checks sent, items received, the game's own completion percentage, which
crossings are open, whichever locks, stations and minimap setting the seed
configured, and the last messages in full.

## Trackers

Universal Tracker is supported and works out of the box. A PopTracker pack
lives at <https://github.com/Kryen112/GTAVC_AP_Poptracker>.

## Requirements

Archipelago 0.6.7 or newer, and the original classic PC release of GTA: Vice
City, executable version 1.0, with its original `data/main.scm`. This is the
classic game and not the Definitive Edition, which the mod does not run on. Two
free community tools go in the game folder,
[Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader) and
[CLEO](https://github.com/cleolibrary/III.VC.CLEO). You supply an original
`gta-vc.exe`; this project never distributes the game.

## For players

To install and play, see the
[setup guide](apworld/gta_vice_city/docs/setup_en.md), which ships inside the
apworld and is what an Archipelago WebHost serves as this world's tutorial. The
[game page](apworld/gta_vice_city/docs/en_Grand%20Theft%20Auto%20Vice%20City.md)
says what the randomizer does to the game.

## For developers

The native client builds on Windows with Visual Studio 2022 C++ Build Tools (x86 compiler and Windows SDK), Git, and these pinned source checkouts:

- plugin-sdk: `12487f6be7846946802497d7471f8c58473b3cd6` from
  <https://github.com/DK22Pac/plugin-sdk>. Set `PLUGIN_SDK_DIR` to its folder.
- vcpkg: `d7112d1a4fb50410d3639f5f586972591d848beb` from
  <https://github.com/microsoft/vcpkg>. Run `bootstrap-vcpkg.bat`; place it in
  the sibling `vcpkg` folder or pass `-VcpkgRoot` to the build script.

Run `scripts/build_native_client.ps1 -Test`. It builds the x86 static packages
`ixwebsocket[mbedtls]` and `jsoncpp`, builds plugin-sdk from source, builds the
Release ASI, and runs the SDK binding, game logic, save isolation and native session checks.
The script corrects three pickup-array bindings in a generated SDK source copy.
SDK outputs live in `.build/sdk`, and the ASI is `mod/asi/plugin/bin/GTA-VC/Release/GtaVcAp.VC.asi`.
Leave `GTA_VC_DIR` unset for a build to stop the asi file from being installing into the game folder.

Install Python's `websockets` package and run
`python scripts/native_interop_check.py .build/native_harness.exe` to test the actual APCpp transport against a local server. This test never connects to your multiworld.

`python scripts/build_native_data.py` regenerates the compiled location, item,
and marker tables from the world (requires `AP_ROOT` like the world tests).
Use `--check` to verify the checked-in tables. APCpp's pinned revision and local
patches are recorded in `mod/asi/third_party/apcpp/README.md`.

Start with `NEXT_APWORLD_PLAYBOOK.md`. It is the build playbook and process
guardrails distilled from the HP2PC and Viscera Cleanup Detail projects: what to
stand up before writing game logic, which architecture calls to get right early,
and the mod-side patterns worth reusing.

Build the apworld with `python scripts/build_apworld.py`. Run the world tests
with `python scripts/run_tests.py`, which is the single entry point for
pre-commit, CI and manual runs.

## License

Original project code and contributions by Kryen112 and randomcodegen are MIT
licensed; see `LICENSE`. The vendored APCpp library is LGPL-2.1-only, including
its local modifications. Dependencies retain their own licenses.
See `NOTICE` and `THIRD_PARTY_LICENSES` for attribution and full third party terms.

### Distributing the native client

The ASI statically links APCpp and its dependencies. When publishing a
binary, publish the matching source and relinking materials alongside it:

- This repository at the exact build revision, including the modified APCpp
  sources, generated native data, project files and build scripts.
- The exact dependency source versions and local patches used by the build,
  including the vcpkg revision and port changes, and the plugin-sdk revision.
- The build configuration and instructions, plus any application objects or
  libraries needed to relink if the supplied source cannot reproduce them.
- `LICENSE`, `NOTICE` and `THIRD_PARTY_LICENSES`, also bundled in the apworld.

`scripts/build_native_client.ps1` builds the ASI from source. Recipients must
be able to modify the LGPL libraries and relink the ASI; do not impose terms
prohibiting that or reverse engineering to debug those modifications. These
requirements apply to each released binary. License files by themselves do
not constitute a source or relinking bundle. Never include Rockstar's game
files in that bundle.

`THIRD_PARTY_LICENSES` records the dependency notices from the installed vcpkg
packages used here. Run `python scripts/collect_native_licenses.py` after changing
dependencies to refresh those notices.
