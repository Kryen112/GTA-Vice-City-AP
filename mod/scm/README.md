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
   starts, adds the APMARK watcher, and moves THIRTEEN threads out of the MAIN
   section so it stays under the game's fixed script buffer. Three are rewritten
   into the watcher it writes to `apwatchers.txt`; four more are carried across
   verbatim into `aparea.txt`, `aprewd.txt`, `apradio.txt` and `appad.txt`; and
   the six weapon
   shops are carried into `apammu1.txt`, `apammu2.txt`, `apammu3.txt`,
   `aphard1.txt`, `aphard2.txt` and `aphard3.txt`. One file each throughout,
   because a CLEO script runs from its own entry point.

   The shops are the one set that cannot be split by cutting alone: each gosubs
   subroutines living inside HARD3's label space, so every shop file carries a
   copy of HARD3's body, reachable only through those gosubs. Duplicating is safe
   because a gosub runs in its caller's thread either way, which is what the till ladder's TIMERA depends on. One file for
   all six was tried and does NOT work: starting the other five would need
   `start_new_script` at a label inside a `.cs`, and CLEO for VC does not
   override that opcode, so the game's handler takes the local label as a raw
   instruction pointer and the thread runs memory below script space.
4. Compile all twelve, plus the script itself:
   `sanny.exe --compile built.markers.txt main.scm --game vc`, then the same for
   `apwatchers.txt`, `aparea.txt`, `aprewd.txt`, `apradio.txt`, `appad.txt`,
   `appickup.txt`
   and the six shop files to `.cs`. Sanny compiles headlessly only with the game
   folder as the working directory, and it lingers: compile ONE at a time and
   check the output file's timestamp, because a run that writes nothing still
   exits zero.
5. Install `main.scm` into the game `data` folder and every `.cs` (plus, for
   manual marker testing, `../cleo/aptest_markers.txt` compiled to `.cs`) into
   the game `CLEO` folder.

## Notes

- The gate tables in `build_scm.py` and `add_markers.py` mirror the world tables
  (`scm.py`, `data.py`, `rules.py`). `scripts/dump_scm_spec.py` prints the same
  spec derived directly from those tables; keep the two in agreement.
- Venue mission gates (launch and marker) additionally require the venue
  purchase's completion global and its ownership global (`$9841..$9855`, one
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
- Class-cash flags `$9858..$9861` (side events, stunt jumps, rampages,
  properties; ASI-stamped from slot_data) gate the vanilla cash suppression:
  while a flag is one, the class's one-time completion cash and its on-screen
  amount are skipped (the AP check is the reward, mirrored back as filler);
  at zero everything pays vanilla. The vanilla banner spells the pass line and
  the amount into one text key, so a suppressed site prints a moneyless banner
  of its own in the vanilla one's place, keyed `APPASS` ("MISSION PASSED!"),
  `APCOURS` ("Course Complete!") or `APWON` ("YOU HAVE WON!"); the installer
  adds all three to every text table, a banner that was nothing but the amount
  is dropped with no replacement, and the built script's count of each is
  pinned both ways.
  Story mission pass cash is deleted outright (always on); venue missions and
  Checkpoint Charlie's first run gate on the properties flag; each side event
  gates its first-completion payout on the side-events flag OR its completion
  global, so replays pay vanilla winnings.
  Each Sunshine Autos race gates its first-win prize and the banner under it the
  same way, on the properties flag OR that race's completion global.
  Repeatable earnings (emergency pay, till cash, race replay prizes, in-mission
  bonuses) are never touched, and a build-time audit pins every remaining
  payout so a new site fails the build instead of leaking. Reserved globals
  above `$9945` are SCM-internal: `$9946` up are marker handles and
  visibility flags. `$9004`, `$9006`, `$9007`, `$9008`, and `$9009` in the
  bookkeeping gap below `$9010` are SCM-internal scratch (the two island-gate
  once-guards, a package counter, and two reward once-guards). The ASI never
  reads or writes any of these.
- `$9528..$9803` is EMPTY and must stay so. The completion block runs
  `$9036..$9803`, sized at 768 slots while 492 locations use it, so that a
  location added later takes a spare slot instead of pushing every block above
  it up one and pointing a running seed's save at the wrong word. Nothing
  hands a spare slot out and nothing may claim one as scratch: the world
  publishes no name for them, and `scripts/check_scm_mirrors.py` reads a
  compiled script that names one as stale.
- Shop class flag: `$9862`, one while shuffle_shops is on, stamped by the
  ASI from slot_data. The six relocated shop threads read it before they
  put the AP marker on a wall or withhold what a purchase hands over, so a
  seed without the class leaves every shop exactly vanilla. A stand whose
  check is still to be taken also announces itself by the text key `APITEM`
  instead of the item's own name, and steps over the vanilla "you already
  have this" refusal: the tool stores' `not is_current_player_weapon`, the
  Ammu-Nations' `9999 > $852` ammo cap and the body armour stand's
  `100 > $873`. That refusal is what a pending stand cannot survive, since a
  tool store equips the player's own melee weapon on every frame it is open
  and a pending stand hands over no weapon to replace it with. The
  affordability test and the out-of-stock flags are NOT opened: the charge
  still leaves the player's money, and out of stock is already a logic term,
  carried by `shop_data.SHOP_STOCK_MISSIONS` for the fourteen items a mission
  racks and by `shop_data.CROSSING_STOCKED_ITEMS` for the Vice Point sniper,
  whose flag is the one the mainland crossing sets.
- Ability locks: `$9863..$9870` (one lock flag per ability item, ASI-stamped
  from slot_data) and `$9871..$9878` (one unlock per item, ASI-written from
  the received items) are ASI-facing only; no gate reads them. The ASI
  enforces each lock per frame while its flag is set and its unlock is zero
  (input masks, the wallet pin, the vehicle-entry cancel, and the weapon
  rampage icon hold), so the script carries nothing for them.
- What lives in MAIN and what does not: the buffer is 225,512 bytes and vanilla
  uses 204,596. The mod spent almost all of that headroom until the six weapon
  shops moved out, which freed about 24,000 bytes and is what made the shop
  withholding fit at all. The APMARK watcher family is the largest single
  resident at 11,632 bytes, and it cannot move: it starts a launcher thread per
  managed mission, and a label belongs to the file it compiles in, so a CLEO
  script cannot name them. Anything that only reads globals and acts on the world
  can move, which is what the twelve relocated threads have in common.

  Measure it, do not assume it. Compiling an over-size MAIN succeeds, and the
  game then loads what fits and drops the tail, which is where the audio threads
  live. `scripts/build_apworld.py` refuses to package one, after a build went
  3,471 bytes over and passed every other gate. Measure with the dword in the SCM header
  (follow the three `02 00 01` gotos from offset 0; the second target is the
  mission segment, whose layout is goto, dword target, one pad byte, then MAIN
  size, largest mission, mission count).
- Content locks: `$9879..$9883` (one lock flag per content item, ASI-stamped
  from slot_data) and `$9884..$9888` (one unlock per item), in the order
  hidden packages, rampages, stunt jumps, property purchases, robbable
  stores. No gate reads either range: the flags only tell the ASI which classes
  to list on its status page, and a whole-class release reaches the script
  through the district block below.
- District content locks: `$9889..$9943`, one unlock per content class per
  district, class-major over eleven districts in the apworld's
  `district_data.DISTRICTS` order. This is the block every content gate and
  every content hold reads, whatever `split_content_locks` is set to, because
  an item releases every global it covers: one for a class-in-one-district
  item, all eleven for a whole-class item. So the script needs no idea which
  granularity a seed chose.

  Every global no item covers is stamped at config time, and which value says
  why. A class-district pair holding no content of that class at all is stamped
  2, absent, whether or not the seed locks the class, and there are thirteen of
  those. Every other global no item covers, which is an unlocked class's
  remaining districts, is stamped 1, released. So an unlocked Robbable Stores is
  five ones and six twos rather than eleven of either.

  Every gate asks ">= 1", so both values let content through. They are apart for
  the status page alone, which must not offer a district holding none of a class
  as somewhere that class just became available.

  Stamping is also what lets each gate be a single condition, since the script
  cannot express "not locked OR released" in one, and it is the whole of the
  toggle invariant: at zero keys the entire block is stamped and every gate
  falls through.

  Three of the classes are pickups, so holding them belongs to the ASI, which
  puts a pool entry in a district by position. The other two have no icon, so
  their gates belong to the script and are per site: each of the 36 stunt jumps
  gates at its own takeoff test (38 sites, since ids 25 and 26 each have two
  definitions) and each of the 15 stores at its own entry into the shared
  robbery handler. The top of this block is two below the highest reserved
  global, which is the finale active flag `$9945` and is what the foundation's
  sizing line references; the finale warp flag `$9944` sits between them.
- Finale active: `$9945`, the top of the reserved block and so the foundation's
  sizing line, with the marker scratch starting one above it. The finale raises
  it on its own first line and drops it at its single exit, and the ASI keeps the
  ambient pickup layout off the pool while it is raised: the mansion siege places
  its own pickups to be survived with, and one ambient slot stands in the same
  grounds. The foundation's write is also its initialization, so a new game
  starts with the layout live, and it sits above the boot thread's loop label so
  it runs once. The ASI drops it itself if it ever sees it raised with
  `$onmission` at zero, which is what a thread killed from outside would leave.
- Ambient pickup checks: `appickup.cs` polls every slot handle from a `wait 0`
  loop and latches that slot's completion global, and it polls Phil's four
  in-shop stands the same way, into the last four globals of the SHOP block,
  because those stands are pickups the engine sells rather than objects a shop
  thread sells. `wait 0` and not slower: `has_pickup_been_collected`
  (`CPickups::IsPickUpPickedUp`, `0x441880`) never looks at the pickup pool. It
  scans a twenty-entry ring of recently collected handles and CLEARS the entry it
  matched, so a collection is an event in a small ring rather than a flag on the
  pickup. The same reading is why every handle a MISSION creates is tested for
  being non-zero first: the ring is zeroed at boot and every read leaves a zero
  behind, so asking about handle zero matches a spent entry and answers true, and
  a stand polled before its mission ran would report itself collected on the
  first frame the seed hash is up. The whole pass waits on that hash for a
  separate reason, which is that the ASI's baseline of the completion globals
  skips any global that starts non-zero.
- Finale warp: `$9944`. The hidden-packages goal is a macguffin hunt, so its
  last fragment plays the story's ending: the client asks for it on every
  status frame, the ASI raises this flag, and the boot-started APFIN watcher
  launches the finale on the conditions every vanilla launcher waits for and no
  others, so no marker, no money, no asset count and none of the AP gate. The
  mission it launches, and the vanilla flag that records its pass and so stops
  a second ending, are both read out of the source. Inside the mission the
  build inserts one branch past the setup that jumps to the block opening with
  `make_player_safe_for_cutscene` before the ending cutscene, which is what
  makes the player's state the mission's own business; on the way it stamps the
  sentinel over every handle the ending releases and the skipped body would
  have created, and nothing else, since the handles it does not own belong to
  other threads or are recreated past the jump. The build refuses a jump that
  skips a completion point or lands on a path reaching none.
- Minimap shuffle: `$9856` (the shuffled flag) and `$9857` (the Minimap item
  unlock) are ASI-facing only; no gate reads them. The ASI hides the radar
  disc while the flag is set and the unlock is zero, so the script carries
  nothing for them.
- Radio randomization: the foundation initializes the resolve map
  `$9831..$9839` to identity and the scripted `set_radio_channel` sites read it,
  so the script is vanilla until the ASI overwrites the map from the station
  unlocks. The APRADIO watcher consumes the `$9840` retune request the ASI
  posts (station id plus one, zero idle).
- Gonzalez's pad: hidden package 25 sits on the roof Treacherous Swine opens,
  and vanilla shuts all three of its doors again at that mission's teardown, so
  the route the logic names would be a window inside one mission rather than a
  reach. `open_gonzalez_pad_door` reopens all three at that teardown, in the
  placements the mission's own start uses, and reopens the middle door at
  Martha's Mug Shot's two teardowns as well, that being the only one it swaps.
  Those two are required rather than tidy: left vanilla they shut the landing
  behind a player who has already passed Treacherous Swine, breaking the route a
  second time.
  The creation at a new game and the mid-mission eject stay vanilla, so the pad
  is shut until the mission opens it. The three doors stand at three heights,
  z 23.9, z 31.2 and z 35.2, which the mission itself pins: the upper two match
  the two doorway boxes it watches for the player stepping off the pad. Read the
  OPEN placements for where a door is and never the CLOSED ones, which share a
  bake origin at 465.375 30.336 33.181 that is neither doorway. The swaps leave
  the compile byte for byte the size it was. The edit is unconditional, which
  `notes/2026-08-26-gonzalez-pad-door.md` argues for: gating it on the packages
  class would put the vanilla hundred-package reward behind the same missable
  whenever that class is off and the packages content key on.
- The pad's warps: open doors are only half of that route, because the building
  has no walkable interior at all. Treacherous Swine carries the player up from
  the street doorway and back down from either upper doorway, fading and setting
  coordinates, and `add_pad_warp_watcher` keeps that pair alive afterwards as the
  APPAD thread: the mission's own boxes, sphere markers, destinations and
  headings, live whenever its vanilla passed flag is set and no mission is
  running. Reading that flag rather than anything this build writes is what makes
  it work in a save whose mission is already behind it. After a lift up it waits
  for the player to leave both upper doorways, since the mission's up destination
  stands inside one of its own down boxes and the mission walks the player out of
  it where this has nothing to walk them with. APPAD relocates to `appad.cs` like
  the other portable threads, for the usual buffer reason and a second one:
  keeping it out of `main.scm` leaves that file's size alone, so shipping it
  cannot shift an offset a save in progress still points at.
