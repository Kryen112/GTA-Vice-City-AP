# GTA: Vice City for Archipelago: player setup

This mod turns GTA: Vice City into an Archipelago game. Your progress unlocks and your rewards come from the multiworld, and your checks send items to the other players in your session.

Setup is three parts: install the Archipelago world, prepare your game folder, then connect the client. The client installs the in-game mod for you.

## What you need first

- **Archipelago 0.6.7 or newer.**
- **GTA: Vice City, the original classic PC version, executable 1.0**
  (`gta-vc.exe`). This mod requires an original 1.0 executable.
- **Ultimate ASI Loader**, installed in your game folder as `dinput8.dll`. Vice City does not load `.asi` plugins on its own, so this is required.
- **CLEO for Vice City**, installed in your game folder.

Ultimate ASI Loader and CLEO are free community tools. Install each into your Vice City folder following its own instructions.

## 1. Install the Archipelago world

You will receive one file: `gta_vice_city.apworld`.

- Double-click it and let the Archipelago Launcher install it, **or**
- copy it into the `custom_worlds` folder of your Archipelago installation.

That single file contains the world, the client, and the in-game mod. You do not download the mod separately.

## 2. Prepare your game folder

1. Confirm your `gta-vc.exe` is the original 1.0 build. If it is not, the client tells you which variant it found and stops.
2. Install Ultimate ASI Loader (`dinput8.dll`) into the folder that holds `gta-vc.exe`.
3. Install CLEO into the same folder.

You do not copy any Archipelago mod files by hand. The client does that in step 4.

## 3. Create or join a multiworld

This is the standard Archipelago flow. If you have played Archipelago before, it is the same here; the game name is **Grand Theft Auto Vice City**.

1. In the Archipelago Launcher, generate the options template for Grand Theft Auto Vice City.
2. Edit your `Grand Theft Auto Vice City.yaml`: set your name, choose which check classes are enabled, and pick your goal. Each option explains itself in the file.
3. Send your YAML to whoever is hosting the session, or host the generation yourself. The host produces the room you connect to.

## 4. Connect and play

1. In the Archipelago Launcher, open the **GTA Vice City Client**.
2. Connect it to the room address, using your slot name from the YAML.
3. **First connection only:** a folder picker opens. Choose the folder that holds `gta-vc.exe`. The choice is saved, so later connections skip this.
4. The client installs the in-game mod into that folder and launches the game for you. Start a **New Game** to begin the seed.

If your goal is the hidden-package hunt, the last Package Fragment you receive ends the game for you: whatever you are doing at the time, Tommy goes straight into the ending of *Keep Your Friends Close...*, credits and all.

### Client commands

Type these in the client console:

| Command | What it does |
| --- | --- |
| `/play` | Launch the game, or relaunch it after quitting. |
| `/setfolder` | Re-pick the install folder (the one holding `gta-vc.exe`). |
| `/installmod` | Reinstall or update the bundled mod. Close the game first. |
| `/restore` | Restore your normal saves and stop Archipelago save isolation. Close the game first. |

## The Archipelago page

Pause the game and pick **ARCHIPELAGO**, above Quit Game. The page shows
everything about your seed the game cannot tell you anywhere else: whether the
client is connected, how many checks you have sent of how many, how many items
have arrived, the game's own completion percentage, which way to the mainland is
open, and, for whatever your YAML enabled, which abilities are locked, which
content classes are still held, which radio stations you have, and whether the
radar is hidden.

## Saves are kept separate

Each seed gets its own save slots, and your existing Vice City saves are left untouched. Your original `main.scm` is backed up once when the mod installs. Run `/restore` (with the game closed) to switch back to your normal saves.

## If something goes wrong

- **The client says your executable is not 1.0.** It names the build it detected. You need an original 1.0 `gta-vc.exe`; no other build is supported.
- **The game starts but nothing Archipelago happens.** Confirm Ultimate ASI Loader is present as `dinput8.dll` and CLEO is installed, then run `/installmod` with the game closed and relaunch.
- **The client cannot find the game.** Run `/setfolder` and pick the folder that holds `gta-vc.exe`.
- **You started before connecting.** Progress re-derives from the server on every load and reconnect, so connect the client and reload your save.
