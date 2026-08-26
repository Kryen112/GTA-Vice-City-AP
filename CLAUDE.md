# GTA: Vice City Archipelago

Archipelago world plus game mod for GTA: Vice City, classic PC exe 1.0.
PLAN.md owns scope. NEXT_APWORLD_PLAYBOOK.md owns process. notes/INDEX.md is
the decision log: read the relevant note before re-deciding anything it
covers, and record new non-obvious decisions there.

PLAN.md and notes/ are deliberately untracked. Never stage or commit them.
notes/ has a .gitignore entry, so it stays out of `git status`; PLAN.md has
none, so it keeps showing there. Stage explicit paths only; never `git add -A`
or `git add .`.

## Layout
- `apworld/gta_vice_city/`: the AP world package. Hand-written Python, no
  generators. All access logic lives in `rules.py` as boolean predicates;
  diffs there are logic, everything else is plumbing.
- `apworld/gta_vice_city/client/`: bridge client on CommonClient, bundled in
  the world and registered as a launcher component. Hosts the localhost
  listener; the ASI connects to it. `scripts/build_apworld.py` links the world
  into the Archipelago checkout, stages the mod payload into it, and hands the
  packaging to Archipelago's own `Build APWorlds` launcher component, then
  installs the result to the frozen install's `custom_worlds`. The manifest
  fields the world owns live in `apworld/gta_vice_city/archipelago.json`, and
  what stays out of the package lives in its `.apignore`; nothing in `scripts/`
  decides what a well formed apworld looks like.
- `mod/asi/`: C++ plugin on plugin-sdk. `mod/cleo/`: CLEO scripts.
  `mod/scm/`: main.scm source for Sanny Builder.
- `scripts/`: entry points shared by hooks, CI, and manual runs.
- `notes/`: decision log and research (untracked).

## House style, all languages
- No em dashes anywhere.
- Comments in present tense, describing what the code does. No changelog
  narration, no reasoning about the diff, no external references
  (playtester names, issue numbers, log excerpts).
- Spell identifiers in full; no abbreviations. Widen whitespace rather than
  truncate a name.
- No machine paths or user names in code or config defaults.
- Commits: short sentences ending in full stops, err shorter, no body, no
  AI attribution. Commit directly to main.

## Python (apworld, client, tools)
- Framework pin: Archipelago 0.6.7, sibling checkout `..\Archipelago`,
  overridable with `AP_ROOT`. Compatible with Python 3.11 through 3.13;
  3.12 is the dev interpreter.
- Lint: ruff, config in this repo's `ruff.toml` (mirrors Archipelago's).
  Passing lint unprompted is part of the definition of done.
- Every behavior change adds or updates a `WorldTestBase` test, unprompted.
- `python scripts/run_tests.py` is the single test entry point for
  pre-commit, CI, and manual runs.

## C++ (ASI plugin)
- 32-bit x86 only. Build with VS Build Tools 2022; the VS Community 2022
  install on the dev machine has no x86 compiler.
- Every game address goes through plugin-sdk's version-detected accessors
  or one central address table. No raw addresses scattered in logic.
- The ASI owns AP communication and state; CLEO owns in-world scripting
  where opcodes are cheaper than hooks; the SCM owns mission gating.

## Framework invariants (review as correctness blockers)
- Only progression items are guaranteed reachable by the generator. No
  access rule may require a non-progression item. Classification lives in
  `create_item` alone.
- `completion_condition` and every N-of-item threshold is a solvability
  contract. Any edit is high-risk and needs a test.
- Money AMOUNTS never gate logic. All money is free-roam grindable once
  Tommy can hold it; cash items exist only to reduce grind. Two items may
  gate a money-spending check, each only while its key is selected: Wallet
  (`ability_locks` wallet), because Tommy cannot hold money, and Property
  Purchases (`content_locks` properties), because the purchase icons are not
  in the world. Both gate on holding or reaching, never on an amount.
- Toggle semantics: a disabled check class behaves fully vanilla in game.
  The content stays playable, its vanilla rewards reactivate, its locations
  do not exist, its class-specific items leave the pool. Story missions are
  always on. The same holds per `ability_locks` key: an unselected key means
  no lock, no item, and no access rule naming that item.
  ONE exception, deliberate: a selected `content_locks` key holds its class
  in game even when that class's own toggle is off, so world content can be
  locked without being checks. The disabled class still contributes no
  locations and no class-specific items, and its vanilla rewards are the
  vanilla ones again, but the content stays held until the item arrives, so
  those rewards wait with it. `content_locks` therefore belongs to the
  in-world-modifier family with `randomize_pickups` and `shuffle_minimap`,
  not to the check-class family.
  `shuffle_emergency_rewards` is in that family too, and for the same reason: it
  takes the emergency chains' payouts into the item pool whether or not their
  levels are checks, so with `enable_emergency_vehicles` off the chains still
  play and simply stop paying out. Whether something is a CHECK and who hands
  over its REWARD are separate questions, and only the class toggle answers the
  first. The flag it stamps suppresses the vanilla grant and arms the applier
  together, so it must never be set without the items that replace what it
  suppresses: one option drives both, which is what makes that impossible.
- The 100% goal requires every check class HOLDING CONTENT the game's own
  completion stat counts to be enabled; generation rejects it otherwise. Holding
  some is the test, not holding only some: the emergency class carries 56
  checks and the stat counts five, one per activity completed, ignoring every
  intermediate milestone, and the goal still demands the class. `enable_pickups`
  is deliberately not one of those classes because the stat counts NOTHING it
  holds, so demanding it would make the goal mean something the game does not.
  The exemption is total, not just from the precondition: the goal is the
  GAME's percentage, so it counts exactly what the game's stat counts, and a
  class the stat never counted stays out of the completion condition even when
  the seed has it on. Shop items will be the same. A new class belongs to one
  list or the other in options.py, and a test refuses one that belongs to
  neither.
- New game per seed. Received state re-derives from AP server state on
  every load and reconnect, never from in-memory bookkeeping alone.
  One-shot grants re-apply only past the saved applied-index; items lost to
  death or old saves stay lost.
- Bridge protocol: newline guard on every outbound frame, chunked large
  frames, version handshake, seed-hash refusal on mismatch.
- All item application (unlock globals, one-shot effects) and DeathLink
  defer on exactly one condition, the game's player-not-controllable flag.
  No other deferral list exists. Beyond that one condition a fixed rate limit
  paces how fast grants leave, since delivering a backlog at once takes the game
  down: one grant per interval and no more than the window's count inside ANY
  window of it, measured back from now rather than from a boundary. The limit
  DELAYS and never drops, so every pending raise is delivered, and it may take
  minutes on a slot holding everything at once. Three things sit outside it
  deliberately, and each is a correctness requirement rather than a convenience:
  lowering a global happens at once, so a stale save cannot keep an ability for
  the seconds a pace would cost; a value the config stamp owns is neither raised
  nor lowered by the applier, because the stamp rewrites it in the same frame and
  a raise that cannot take would spend a slot forever ahead of everything else;
  and the order of paced raises ROTATES rather than running lowest-first, so one
  global that cannot hold its target cannot starve the rest. Any further
  withholding condition is the thing this clause exists to forbid, because a
  second one is where lost grants hide.
- DeathLink is that one deferral and no queue. A linked death that still cannot
  land is DROPPED rather than held: Tommy already dying or arrested, no game
  connected, a game boundary. A death is an event and not a fact about the slot,
  which is the opposite of a queued check, and those are still never dropped.
  It holds, like a grant, on a frame with no player ped to write into. The
  pacer never applies: it paces GRANTS, and a death is not one, so the three
  exemptions above stay three. The mod never reports back the death its own
  kill caused, which is what keeps two linked slots from bouncing one death
  forever, and it reports the game's own wasted state only, so an arrest is
  not a death. The option is
  slot_data, so the CLIENT is the only gate: the mod holds no copy of it, and a
  value stamped into a save would be a second answer that could disagree.
- Item and location id tables freeze at the first public release. After that,
  only append and never reorder or remove entries, since existing seeds and
  trackers depend on the ids. Before release they are free to change.

## Review and testing
- The `code-reviewer` subagent (read-only) reviews every diff touching
  `apworld/`, `client/`, `mod/`, or `scripts/` against this file; a Stop
  hook enforces it. Findings carry `file:line` and a severity.
- Pre-commit gates commits: hygiene, ruff, then world tests through
  `scripts/run_tests.py`. CI runs the same entry point.
- In-game verification is the final gate for anything player-visible;
  record date and result in `notes/`.
- Bisect before blaming. Measure before speculating. Read decompiled
  source instead of guessing game internals.
