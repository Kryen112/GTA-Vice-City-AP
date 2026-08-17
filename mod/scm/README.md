# Custom main.scm build

The mod ships one static canonical `main.scm` whose gates read AP-controlled
reserved globals. These scripts build it from the player's own 1.0 decompile.
No Rockstar-derived data lives in the repo: the vanilla decompile, the built
source, and the compiled `main.scm` are all generated locally and stay out of
version control.

## Pipeline

1. Decompile the player's own vanilla 1.0 `main.scm` with Sanny Builder:
   `sanny.exe --decompile main.scm clean.txt --game vc`.
2. Apply the AP transform: `python build_scm.py clean.txt built.txt`. This adds
   the reserved-global foundation, each launcher's unlock gate, each location's
   completion write, reward re-gating, the mainland-area watcher, and the
   package, activity, stat, and reward watchers.
3. Apply the AP-driven markers: `python add_markers.py built.txt built.markers.txt apwatchers.txt`.
   This makes every mission-giver marker appear only on its AP unlock, severs the
   vanilla story reveals and launcher starts, adds the APMARK watcher, and moves
   the three heaviest completion watchers into the CLEO script it writes to
   `apwatchers.txt`, so the MAIN section stays under the game's script buffer.
4. Compile both: `sanny.exe --compile built.markers.txt main.scm --game vc` and
   `sanny.exe --compile apwatchers.txt apwatchers.cs --game vc`.
5. Install `main.scm` into the game `data` folder and `apwatchers.cs` (plus, for
   manual marker testing, `../cleo/aptest_markers.txt` compiled to `.cs`) into
   the game `CLEO` folder.

## Notes

- The gate tables in `build_scm.py` and `add_markers.py` mirror the world tables
  (`scm.py`, `data.py`, `rules.py`). `scripts/dump_scm_spec.py` prints the same
  spec derived directly from those tables; keep the two in agreement.
- Venue mission gates (launch and marker) additionally require the venue
  purchase's completion global and its ownership global (`$9400..$9414`, one
  per purchasable property in purchase order, ASI-written from the ownership
  items), so a venue strand stays hidden and unstartable until the property is
  bought and owned. In logic the purchase's stand-in is the items to pass
  Shakedown, the mission that puts the businesses up for sale. The safehouse
  save threads gate on the same ownership globals (save pickup and garage wait
  for bought plus owned), and the Pole Position and Sunshine Autos
  asset-completion recognitions do too. With the properties class disabled the
  client stamps every ownership global and maxes the venue unlock globals
  through config_globals, collapsing all of it to vanilla purchase-only.
- Cap the Collector keeps its vanilla asset prerequisite in the FIN1 gate:
  Hit the Courier passed (`$273`), Cop Land passed (`$268`), and the vanilla
  owned-asset count `$1175` at seven or more of the nine income assets.
- Area gating: the APAREA watcher opens the mainland on Mainland Access
  (`$9030`) and the two Starfish Island gates on Starfish Island Access
  (`$9031`): the east gate on the item alone, the west gate only together
  with Mainland Access, since that gate is the sole barrier on the island's
  mainland crossing.
- Class-cash flags `$9417..$9420` (side events, stunt jumps, rampages,
  properties; ASI-stamped from slot_data) gate the vanilla cash suppression:
  while a flag is one, the class's one-time completion cash and its on-screen
  amount are skipped (the AP check is the reward, mirrored back as filler);
  at zero everything pays vanilla. Story mission pass cash is deleted outright
  (always on); venue missions and Checkpoint Charlie's first run gate on the
  properties flag; each side event gates its first-completion payout on the
  side-events flag OR its completion global, so replays pay vanilla winnings.
  Repeatable earnings (emergency pay, till cash, race winnings, in-mission
  bonuses) are never touched, and a build-time audit pins every remaining
  payout so a new site fails the build instead of leaking. Reserved globals
  above `$9446` are SCM-internal: `$9447` up are marker handles and
  visibility flags. `$9004`, `$9006`, `$9007`, `$9008`, and `$9009` in the
  bookkeeping gap below `$9379` are SCM-internal scratch (the two island-gate
  once-guards, a package counter, and two reward once-guards). The ASI never
  reads or writes any of these.
- Ability locks: `$9421..$9428` (one lock flag per ability item, ASI-stamped
  from slot_data) and `$9429..$9436` (one unlock per item, ASI-written from
  the received items) are ASI-facing only; no gate reads them. The ASI
  enforces each lock per frame while its flag is set and its unlock is zero
  (input masks, the wallet pin, the vehicle-entry cancel, and the weapon
  rampage icon hold), so the script carries nothing for them.
- Content locks: `$9437..$9441` (one lock flag per content item, ASI-stamped
  from slot_data) and `$9442..$9446` (one unlock per item), in the order
  hidden packages, rampages, stunt jumps, property purchases, robbable
  stores. Three of the classes are pickups, so holding them belongs to the ASI
  and the script needs nothing for them. The other two have no icon to hold, so their gates
  belong to the script rather than the ASI: the USJ thread reads the stunt jump
  pair and the two store robbery handlers read the store pair. The top unlock
  is the highest reserved global, which the foundation's sizing line references
  as `$9446`.
- Stunt jump dump: F7 in a loaded game writes `gtavc_ap_stuntjumps.txt` beside
  the executable. Vice City defines its 36 unique stunt jumps nowhere a build
  step can read, neither in the SCM nor as a static table in the executable;
  the game builds them on the heap at start. The ASI scans its own heap for
  the record shape (two bounding boxes then a camera position) and takes the
  longest run at one stride, preferring a run as long as the game's own
  `CStats::TotalNumberOfUniqueJumps`, and toasting the shortfall when it
  finds fewer. Development tool: it runs only on the key, reads no reserved
  global, and writes nothing into the world beyond its own result toast.
  `scripts/dump_check_coords.py` takes the file as its third argument and
  folds the jumps into the tracker pack's coordinate table.
- Minimap shuffle: `$9415` (the shuffled flag) and `$9416` (the Minimap item
  unlock) are ASI-facing only; no gate reads them. The ASI hides the radar
  disc while the flag is set and the unlock is zero, so the script carries
  nothing for them.
- Radio randomization: the foundation initializes the resolve map
  `$9390..$9398` to identity and the scripted `set_radio_channel` sites read it,
  so the script is vanilla until the ASI overwrites the map from the station
  unlocks. The APRADIO watcher consumes the `$9399` retune request the ASI
  posts (station id plus one, zero idle).
