# GTA: Vice City Archipelago 2.1.0

Requires fresh seeds and new saves, with matching APWorld and mod versions.

## Changes since 2.0.0

- Removed error spamming on connection errors.
- Moved overlapping mission launch markers.
- Required-asset map markers stay hidden until the property is purchasable.
- Added Mission Shuffle: `off`, `within_giver`, or `full`.
- Full shuffle mixes story and asset missions across givers. Checks stay tied to missions.
- An Old Friend and vehicle activities keep their original entrances.
- Set 0–9 completed assets to unlock the finale.
- New goal: complete Keep Your Friends Close wherever it appears.
- Location hints for shuffled missions show their giver and slot.
- World events can follow giver progress or their shuffled mission.
- Missions temporarily open needed crossings, then restore them and return you to the giver.
- Added `/unstuck` and `/increasetimer`.
- Fixed/Adjusted shuffled mission entrances, interiors, controls, and return warps.

## Previous release: 2.0.0

Vice City connects directly to Archipelago through the native ASI client.
Use the standalone setup to install or update the mod, and install the matching
APWorld in Archipelago for generation and hosting.

## Changes since 1.0.1

- Console command history and autocomplete for `!hint` items and
  `!hint_location` locations. Messages received while the console is open do
  not queue duplicate popup notifications.
- Longer minimap range for AP check markers. Unpurchased income assets appear
  for final-mission and 100% goals even without an AP purchase check. These
  markers are lime; linked purchase checks become yellow when available.
- Asset status names distinguish missing ownership (white), owned but
  unfinished (yellow), and completed income assets (green). Progressive item
  counts remain separate from asset completion.
- Configurable Pole Position spending: $1-$100 per five-second tick, default
  $20. The $300 requirement takes about 75 seconds at the default rate; choose
  `vanilla` for $5 per tick.
- Fix Malibu entrance locking around Death Row and report Distribution
  completion from Cherry Poppers' income state.
- Fix spacing for square brackets in the console font.
- Fix the water-creature object lifecycle crash at `006616B7`.
- Recover an already-initialized save directory when the startup callback was
  missed, allowing seed activation and AP save-folder creation to proceed.
  Initialization logging identifies any remaining startup waits.

The Pay 'n' Spray crash at `005C2D01` is not confirmed fixed. Temporary movement
diagnostics are not included. The save-directory recovery passed its regression
test.

## Also included since upstream 1.0.0

- Mission shuffle within each giver's branch, with protected opening and
  endpoint missions and corrected mission-marker cleanup.
- Configurable check percentages, emergency activity percentages, and taxi
  milestone spacing, with progression items preserved when reducing checks.
- Emergency progress tracking and recovery through AP DataStorage and a local
  cache, plus connection-indicator and HUD text improvements.
- Standalone setup distribution; the APWorld contains generation logic and
  documentation, while the installer supplies the game mod.

## Installation

1. Close Vice City and run `GTA-Vice-City-AP-Setup.exe` to install or update.
2. Install `gta_vice_city.apworld` in Archipelago for generation or hosting.
3. Start Vice City, connect through the F8 console, and start or load your game.

Updating the mod does not change an existing seed's settings or checks.
Generate a new seed to use new generation options. Existing seed saves remain
isolated from ordinary Vice City saves.

Setup requires 64-bit Windows, classic Vice City 1.0 English, and the player's
original `data/main.scm`. Generation/hosting requires Archipelago 0.6.7 or newer.
The unsigned installer downloads missing ASI Loader and CLEO runtimes.
See [setup instructions](apworld/gta_vice_city/docs/setup_en.md) for details.

It contains matching source, dependency materials, license notices, and build
instructions. `SHA256SUMS.txt` identifies the release assets.
