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
   This makes every mission-giver marker appear only on its AP unlock, holds the
   whole marker and launcher pass until An Old Friend is done (the vanilla flag
   `$222` that mission sets), severs the vanilla story reveals and launcher
   starts, adds the APMARK watcher, and moves six threads out of the MAIN
   section so it stays under the game's fixed script buffer. Three are rewritten
   into the watcher it writes to `apwatchers.txt`; the other three are carried
   across verbatim into `aparea.txt`, `aprewd.txt` and `apradio.txt` beside it,
   one file each because a CLEO script runs from its own entry point.
4. Compile all four, plus the script itself:
   `sanny.exe --compile built.markers.txt main.scm --game vc`, then the same for
   `apwatchers.txt`, `aparea.txt`, `aprewd.txt` and `apradio.txt` to `.cs`.
   Sanny compiles headlessly only with the game folder as the working directory.
5. Install `main.scm` into the game `data` folder and the four `.cs` files (plus,
   for manual marker testing, `../cleo/aptest_markers.txt` compiled to `.cs`)
   into the game `CLEO` folder.

## Notes

- The gate tables in `build_scm.py` and `add_markers.py` mirror the world tables
  (`scm.py`, `data.py`, `rules.py`). `scripts/dump_scm_spec.py` prints the same
  spec derived directly from those tables; keep the two in agreement.
- Venue mission gates (launch and marker) additionally require the venue
  purchase's completion global and its ownership global (`$9413..$9427`, one
  per purchasable property in purchase order, ASI-written from the ownership
  items), so a venue strand stays hidden and unstartable until the property is
  bought and owned. In logic the purchase's stand-in is the items to pass
  Shakedown, the mission that puts the businesses up for sale. The safehouse
  save threads gate on the same ownership globals (the save pickup, the garage,
  the save-house radar icon and the cutscene's own "you can save here" text all
  wait for bought plus owned), and the Pole Position and Sunshine Autos
  asset-completion recognitions do too. Sunshine Autos' strand is its four
  import garage lists, each gated and completed at its own recognition block,
  and its six street races are flat checks behind the showroom's ownership
  condition alone, since the vanilla menu opens all six at the purchase. With
  the properties class disabled the
  client stamps every ownership global and maxes the venue unlock globals
  through config_globals, collapsing all of it to vanilla purchase-only.
- The Vercetti Protection gates (launch and marker) also wait on Rub Out having
  passed, since the strand gives from the estate that mission hands over and on
  the unlock alone its markers stand in Diaz's mansion. The term names Rub Out's
  launcher and both scripts read that launcher's own guard flag out of the
  source, so no vanilla flag number is written down. `data.py` owns which strand
  waits on which mission (`IN_GAME_PASSED_PREREQUISITES`).
- Cap the Collector keeps its vanilla asset prerequisite in the FIN1 gate:
  Hit the Courier passed (`$273`), Cop Land passed (`$268`), and the vanilla
  owned-asset count `$1175` at seven or more of the nine income assets.
- Area gating: the APAREA watcher opens each of the four vanilla crossings on
  its own item OR on Mainland Access, which is what lets one static script serve
  both `split_mainland_access` settings. With the option off only Mainland
  Access (`$9030`) is ever written, so every crossing opens together, the
  vanilla flip; with it on only the crossing globals are, so which one the seed
  hands over decides where the player crosses. The three bridge roadblocks are
  Prawn Island (`$9032`, object `$1781`), Leaf Links (`$9033`, `$1782`) and
  Ocean Beach (`$9034`, `$1783`), each branch guarded on its roadblock still
  existing rather than on a flag of its own, so its road switches and its delete
  run once. The Starfish west gate (`$1779`) is the fourth crossing (`$9035`)
  and needs Starfish Island Access (`$9031`) with it, since the gate is on the
  island; the east gate opens on that item alone. Both gates once-guard on the
  reserved scratch globals `$9004` (east) and `$9007` (west), because each swaps
  its object instead of deleting it. The shared part of the flip is a subroutine
  gosubbed from the bridge trigger and from the west gate, once-guarded by the
  vanilla flag `$847` it sets (which is also what stocks Ammu-Nation's sniper
  rifle): reaching it through the west gate is what stops a causeway item held
  without the island from flipping the mainland open before any route exists.
- Class-cash flags `$9430..$9433` (side events, stunt jumps, rampages,
  properties; ASI-stamped from slot_data) gate the vanilla cash suppression:
  while a flag is one, the class's one-time completion cash and its on-screen
  amount are skipped (the AP check is the reward, mirrored back as filler);
  at zero everything pays vanilla. Story mission pass cash is deleted outright
  (always on); venue missions and Checkpoint Charlie's first run gate on the
  properties flag; each side event gates its first-completion payout on the
  side-events flag OR its completion global, so replays pay vanilla winnings.
  Each Sunshine Autos race gates its first-win prize the same way, on the
  properties flag OR that race's completion global.
  Repeatable earnings (emergency pay, till cash, race replay prizes, in-mission
  bonuses) are never touched, and a build-time audit pins every remaining
  payout so a new site fails the build instead of leaking. Reserved globals
  above `$9515` are SCM-internal: `$9516` up are marker handles and
  visibility flags. `$9004`, `$9006`, `$9007`, `$9008`, and `$9009` in the
  bookkeeping gap below `$9392` are SCM-internal scratch (the two island-gate
  once-guards, a package counter, and two reward once-guards). The ASI never
  reads or writes any of these.
- Ability locks: `$9434..$9441` (one lock flag per ability item, ASI-stamped
  from slot_data) and `$9442..$9449` (one unlock per item, ASI-written from
  the received items) are ASI-facing only; no gate reads them. The ASI
  enforces each lock per frame while its flag is set and its unlock is zero
  (input masks, the wallet pin, the vehicle-entry cancel, and the weapon
  rampage icon hold), so the script carries nothing for them.
- What lives in MAIN and what does not: the buffer is 225,512 bytes and vanilla
  uses 204,596, so the mod has about 20,900 to spend and spends most of it. The
  APMARK watcher family is the largest single resident at 11,632 bytes, and it
  cannot move: it starts a launcher thread per managed mission, and a label
  belongs to the file it compiles in, so a CLEO script cannot name them. Anything
  that only reads globals and acts on the world can move, which is what the six
  relocated threads have in common. Measure with the dword in the SCM header
  (follow the three `02 00 01` gotos from offset 0; the second target is the
  mission segment, whose layout is goto, dword target, one pad byte, then MAIN
  size, largest mission, mission count).
- Content locks: `$9450..$9454` (one lock flag per content item, ASI-stamped
  from slot_data) and `$9455..$9459` (one unlock per item), in the order
  hidden packages, rampages, stunt jumps, property purchases, robbable
  stores. No gate reads either range: the flags only tell the ASI which classes
  to list on its status page, and a whole-class release reaches the script
  through the district block below.
- District content locks: `$9460..$9514`, one unlock per content class per
  district, class-major over eleven districts in the apworld's
  `district_data.DISTRICTS` order. This is the block every content gate and
  every content hold reads, whatever `split_content_locks` is set to, because
  an item releases every global it covers: one for a class-in-one-district
  item, all eleven for a whole-class item. So the script needs no idea which
  granularity a seed chose.

  Every global no item covers, which is an unlocked class's eleven plus the
  thirteen class-district pairs holding no content at all, is stamped to 1 at
  config time. That is what lets each gate be a single condition, since the
  script cannot express "not locked OR released" in one, and it is the whole of
  the toggle invariant: at zero keys the entire block is stamped and every gate
  falls through.

  Three of the classes are pickups, so holding them belongs to the ASI, which
  puts a pool entry in a district by position. The other two have no icon, so
  their gates belong to the script and are per site: each of the 36 stunt jumps
  gates at its own takeoff test (38 sites, since ids 25 and 26 each have two
  definitions) and each of the 15 stores at its own entry into the shared
  robbery handler. The top of this block is one below the highest reserved
  global, the finale warp flag `$9515`, which is what the foundation's sizing
  line references.
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
- Finale warp: `$9515`, the top of the reserved block and so the foundation's
  sizing line, with the marker scratch starting one above it. The
  hidden-packages goal is a macguffin hunt, so its last fragment plays the
  story's ending: the client asks for it on every status frame, the ASI raises
  this flag, and the boot-started APFIN watcher launches the finale on the
  conditions every vanilla launcher waits for and no others, so no marker, no
  money, no asset count and none of the AP gate. The mission it launches, and
  the vanilla flag that records its pass and so stops a second ending, are both
  read out of the source. Inside the mission the build inserts one branch past
  the setup that jumps to the block opening with
  `make_player_safe_for_cutscene` before the ending cutscene, which is what
  makes the player's state the mission's own business; on the way it stamps the
  sentinel over every handle the ending releases and the skipped body would
  have created, and nothing else, since the handles it does not own belong to
  other threads or are recreated past the jump. The build refuses a jump
  that skips a completion point or lands on a path reaching none.
- Minimap shuffle: `$9428` (the shuffled flag) and `$9429` (the Minimap item
  unlock) are ASI-facing only; no gate reads them. The ASI hides the radar
  disc while the flag is set and the unlock is zero, so the script carries
  nothing for them.
- Radio randomization: the foundation initializes the resolve map
  `$9403..$9411` to identity and the scripted `set_radio_channel` sites read it,
  so the script is vanilla until the ASI overwrites the map from the station
  unlocks. The APRADIO watcher consumes the `$9412` retune request the ASI
  posts (station id plus one, zero idle).
