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

Received items slide in down the left edge of the screen, naming the item, who
it came from and where it was found. Items apply as they arrive, including in
the middle of a mission.

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

Start with `NEXT_APWORLD_PLAYBOOK.md`. It is the build playbook and process
guardrails distilled from the HP2PC and Viscera Cleanup Detail projects: what to
stand up before writing game logic, which architecture calls to get right early,
and the mod-side patterns worth reusing.

Build the apworld with `python scripts/build_apworld.py`. Run the world tests
with `python scripts/run_tests.py`, which is the single entry point for
pre-commit, CI and manual runs.

## License

MIT, see `LICENSE`. Third party notices are in `NOTICE`.
