# Grand Theft Auto Vice City Setup Guide

## Quick Links

- [Game Info](/games/Grand%20Theft%20Auto%20Vice%20City/info/en)
- [Options Page](/games/Grand%20Theft%20Auto%20Vice%20City/player-options)
- [GTA Vice City Archipelago GitHub](https://github.com/Kryen112/GTA-Vice-City-AP)
- [Releases](https://github.com/Kryen112/GTA-Vice-City-AP/releases)

This mod turns GTA: Vice City into an Archipelago game. Your progress unlocks and
your rewards come from the multiworld, and your checks send items to the other
players in your session.

Vice City connects directly to Archipelago using APCpp. No external Python client
needs to run while you play.

## Updating an existing Archipelago installation

For this native-client and marker update:

1. Close Vice City.
2. Replace `GtaVcAp.VC.asi` beside `gta-vc.exe` with the updated ASI.
3. Set your server and slot in `GtaVcAp.VC.ini`, as described under
   [Connection settings](#connection-settings), then launch Vice City directly.

Keep your existing patched `data/main.scm`, AP scripts in `CLEO`, ASI loader,
and CLEO runtime. You do not need to rerun the setup tool or regenerate
your multiworld for this update.

## Installing into a fresh game folder

The ASI alone is not a complete fresh installation. Mission gating and some
check detection still depend on the patched `data/main.scm` and AP CLEO scripts.
The ASI does not install or patch these files. The first-time instructions below
use **GTA Vice City Setup** in Archipelago Launcher to build and install them from
your game files. Setup works offline using Archipelago's bundled runtime; you do
not need a separate Python installation or the Python client.

## What you need first

- **Archipelago 0.6.7 or newer.**
- **GTA: Vice City, the original classic PC release, executable 1.0**
  (`gta-vc.exe`), with its original `data/main.scm`. This is the classic game,
  not the Definitive Edition, which is a different game the mod does not run on.
  The setup tool checks both and refuses to install when either is wrong, naming
  which build of the game it found and what it wanted.
- **[Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader)**,
  installed in your game folder as `dinput8.dll`. Vice City does not load `.asi`
  plugins on its own, so this is required.
- **[CLEO for Vice City](https://github.com/cleolibrary/III.VC.CLEO)**,
  installed in your game folder.
- **Optional, and strongly recommended:
  [Windowed Mode](https://github.com/ThirteenAG/III.VC.SA.WindowedMode)**, which
  runs the game in a window, or in borderless fullscreen, instead of the
  fullscreen mode Vice City uses on its own. On a modern PC that fullscreen mode
  can make the game very slow, and it can cause crashes. This plugin fixes both,
  and it does not change anything in the game itself.

All three are free community tools, and each link goes to the project's own
GitHub, where the downloads and the source both live. Section 2 says which
download to take from each.

## 1. Install the Archipelago world

You need one file, `gta_vice_city.apworld`, from the
[releases page](https://github.com/Kryen112/GTA-Vice-City-AP/releases). Whoever
is hosting your session may hand it to you directly instead.

- Double-click it and let the Archipelago Launcher install it, **or**
- copy it into the `custom_worlds` folder of your Archipelago installation.

That single file contains the world, the offline setup tool, and the in-game mod. You do not
download the mod separately.

## 2. Prepare your game folder

1. Confirm your `gta-vc.exe` is the original 1.0 build. The setup tool checks this
   before it installs, and tells you which build
   it found, so you do not have to know how to look; the mod attaches to 1.0 and
   to nothing else.
2. Install Ultimate ASI Loader into the folder that holds `gta-vc.exe`. Take
   `Ultimate-ASI-Loader.zip` from its
   [releases page](https://github.com/ThirteenAG/Ultimate-ASI-Loader/releases).
   Vice City is a 32-bit game, so every `_x64` asset there is the wrong one. The
   archive holds a single `dinput8.dll`, already under the name Vice City needs,
   so extract it next to the executable and you are done.
3. Install CLEO into the same folder. Take the Vice City archive from its
   [releases page](https://github.com/cleolibrary/III.VC.CLEO/releases), not the
   GTA III one, since that page serves both games from the same release, and
   extract it there. It brings `VC.CLEO.asi` and a `CLEO` folder. The mod is
   verified against CLEO 2.1.1; if a newer release misbehaves, that is the one
   to fall back to.
4. Optional, and strongly recommended: install Windowed Mode into the same
   folder. Take the archive from its
   [releases page](https://github.com/ThirteenAG/III.VC.SA.WindowedMode/releases)
   and extract `III.VC.SA.WindowedMode.asi` next to the executable. One file
   covers GTA III, Vice City and San Andreas, so you do not have to pick a
   version. Press **Alt+Enter** in game to switch between a window and
   borderless fullscreen. Newer releases also add an ini file next to the
   plugin, which sets which of the two the game starts in. Archipelago does not
   need this plugin, but the entry **The game is very slow, or it crashes when
   you Alt+Tab away from it**, under **If something goes wrong** at the end of
   this page, explains what it fixes.

For a fresh installation, the setup tool installs the Archipelago scripts and
ASI in section 4. For the native-client update to an existing installation,
follow the shorter update instructions above.

## 3. Create or join a multiworld

This is the standard Archipelago flow. If you have played Archipelago before, it
is the same here; the game name is **Grand Theft Auto Vice City**.

1. In the Archipelago Launcher, generate the options template for Grand Theft
   Auto Vice City.
2. Edit your `Grand Theft Auto Vice City.yaml`: set your name, choose which check
   classes are enabled, and pick your goal. Each option explains itself in the
   file, and the
   [options page](/games/Grand%20Theft%20Auto%20Vice%20City/player-options) says
   the same thing in the browser.
3. Send your YAML to whoever is hosting the session, or host the generation
   yourself. The host produces the room you connect to.

## 4. Install once, then connect in game

### Fresh installation only

1. Close Vice City. In Archipelago Launcher, open **GTA Vice City Setup**
   under Tools. Restart the launcher if you just updated the apworld.
2. Choose the folder that holds `gta-vc.exe`.
3. The setup tool installs the ASI, patches the game scripts and text, and backs
   up the original files. It creates `GtaVcAp.VC.ini` if missing and preserves
   an existing INI. No room connection is required, and setup does not launch
   the game or move saves.
4. Set your connection details below, then launch Vice City directly.

You can run **GTA Vice City Setup** again to update an existing installation.
On Windows, it can also be started with:

```text
ArchipelagoLauncher.exe "GTA Vice City Setup"
```

### Connection settings

You can configure the connection entirely in game: press **F8**, enter
`/server HOST:PORT`, `/slot NAME`, optional `/password PASSWORD`, then `/connect`.
The console remembers server and slot in `%LOCALAPPDATA%/GtaVcAp/connection.ini`;
these take precedence over the defaults below. Entered passwords stay in memory
for the run, and changing the server or slot clears them.
Unacknowledged checks are also kept in this user folder and replayed on reconnect.
Old check files beside the ASI are copied there automatically.

For initial defaults, you can instead use the INI beside the ASI:

1. Open `GtaVcAp.VC.ini` beside `GtaVcAp.VC.asi` in the game folder
   (create it if updating manually). If it already
   contains `[toasts]` settings, keep those and add this section:

   ```ini
   [archipelago]
   server=127.0.0.1:38281
   slot=YourSlotName
   password=
   ```

   Replace the address and slot with your room's details. Leave the password
   empty unless the room requires one. `host:port` uses TLS for remote hosts;
   use `ws://host:port` for an explicitly unencrypted remote server.
2. Launch Vice City directly. The ASI connects, loads slot data, and reconnects
   automatically. Start a **New Game** for a new seed, or load your existing
   save for this seed. The Python client does not need to run while playing.

Enabled, unfinished checks have colored dots on the minimap and pause-menu map:
packages green, robberies light red, rampages dark red, pickups orange,
stunt jumps blue, properties yellow, side events cyan, and shop stock purple.
Each dot has a 5x5 pixel center and a one-pixel black outline.
Missions retain their existing markers. Current seeds work without regeneration.

Items, goals, and DeathLink use the room's slot data. Pending checks remain in
`%LOCALAPPDATA%/GtaVcAp/GtaVcAp.<seed-hash>.json` until the server acknowledges
them, so moving the mod to another folder preserves them.

If your goal is the hidden-package hunt, the last Package Fragment you receive
ends the game for you: whatever you are doing at the time, Tommy goes straight
into the ending of *Keep Your Friends Close...*, credits and all.

## The Archipelago page

Pause the game and pick **ARCHIPELAGO**, above Quit Game. The page shows
everything about your seed the game cannot tell you anywhere else: whether the
client is connected, how many checks you have sent of how many, how many items
have arrived, the game's own completion percentage, which way to the mainland is
open, and, for whatever your YAML enabled, which abilities are locked, which
content classes are still held, which radio stations you have, and whether the
radar is hidden.

## What the mod does to your game folder

The mod's mission gating lives in the game's own script file, `data/main.scm`.
The apworld does not carry a copy of that file: it carries the differences, and
the setup tool builds the modded script from **your** copy when it installs.

Two things follow from that.

- Your `data/main.scm` has to be the original 1.0 one. If it is not, the setup tool
  says so, prints the fingerprint it found, and installs nothing. Restore
  `data/main.scm` from your own copy of the game files and run setup again. It also
  refuses when `AP_mod_backup\main.scm` exists and is not the original; delete
  that file and run setup again.
- The mod backs your original script up to `AP_mod_backup\main.scm` in the game
  folder the first time it installs, and that backup is the copy it patches from
  every time after. Leave the folder alone. If you delete it, restore `data/main.scm` from your
  own copy of the game files.

Resolve any setup error before launching the game: an unpatched script cannot
provide the Archipelago mission gating and check detection.

## Saves and seed changes

Connect from the main menu using **F8**, `/server HOST:PORT`, `/slot NAME`,
optional `/password PASSWORD`, and `/connect`. Connection settings can also be
set in the INI. Type `/help` for local commands, `!help` for server commands, or
chat normally. `/hint [item]` asks for hints; `/deathlink [on|off]` controls DeathLink.
Other players' messages, hints, countdowns, releases and goals appear in the console.

Saves select themselves automatically under `AP_Seeds/<seed-and-slot-hash>` in
`GTA Vice City User Files`. Existing career saves and `gta_vc.set` stay in place.
Save access is blocked until the server identifies the seed; connect before
loading or saving. After disconnection, this seed's saves remain available.
Restart Vice City before switching to another seed or slot.

The legacy Python client is no longer included. If it previously moved your
saves, close the game and back up the entire `GTA Vice City User Files` folder
in Documents. Your normal saves are in `AP_Career`, stored seed saves are in
`AP_Seeds/<seed>`, and the active seed's saves are the loose `.b` files in the
main folder. To restore a set, move the loose `.b` files to a separate backup
folder first, then copy the desired set into the main folder. Keep the source
folders and `gta_vc.set`; do not overwrite saves you want to keep.

## If something goes wrong

- **Setup says your `gta-vc.exe` is another build.** It names the build it
  found. The mod attaches to the classic 1.0 executable and to no other, so no
  other build can run it, patched or not.
- **Setup says it could not tell which build your `gta-vc.exe` is.** It
  installs anyway and this may be nothing: a compressed or repacked executable
  is unreadable from the outside and unpacks to a perfectly good 1.0 once the
  game starts. It is worth remembering only if nothing Archipelago then happens
  in game.
- **The game starts but nothing Archipelago happens.** Confirm Ultimate ASI
  Loader is present as `dinput8.dll` and CLEO is installed, both covered in
  section 2, then run **GTA Vice City Setup** with the game closed and relaunch. CLEO
  prints its version in the bottom left corner of the main menu, so no banner
  there sends you back to those two before anything else.
- **Setup says your `main.scm` is not the original 1.0 script.** It prints
  the fingerprint it found and the one it wants. Restore `data/main.scm` from
  your own copy of the game files, and remove `AP_mod_backup\main.scm` if it is
  there and is not the original. Another Vice City mod that replaces the script
  is the usual cause.
- **Setup cannot find the game.** Pick the folder that holds `gta-vc.exe`.
- **The built-in client does not connect.** Check `[archipelago]` in
  `GtaVcAp.VC.ini` and the room address, then use `/connect` in the F8 console. The pause menu and
  `gtavc_ap_asi.log` report connection errors. The room must be running.
- **Wrong seed save loaded.** Load a save from this room or start a new game.
  Restart Vice City if the server was changed to another seed.
- **The game is very slow, or it crashes when you Alt+Tab away from it.**
  Install Windowed Mode from section 2 and press Alt+Enter. Vice City's own
  fullscreen mode takes over your whole screen, which modern PCs handle badly.
  It is worse if your screen has a high refresh rate, or if you have more than
  one screen. That same fullscreen mode can also crash the game when you switch
  to another window. Windowed Mode runs the game in a window instead, and avoids
  both. This is a Vice City problem, not an Archipelago one: it happens the same
  way without the mod, so the client cannot fix it for you.
- **The game crashes a few seconds after you start it, in `quartz.dll`.** Those
  are the two intro videos. The game plays them with an old Windows video
  component that does not always work any more. Rename `GTAtitles.mpg` and
  `Logo.mpg` in the `movies` folder, to `.bak` or anything else, and the game
  skips them. This is normal Vice City behavior, not Archipelago, and the game
  starts faster without them.
