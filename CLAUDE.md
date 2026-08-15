# GTA: Vice City Archipelago

Archipelago world plus game mod for GTA: Vice City, classic PC exe 1.0.
PLAN.md owns scope. NEXT_APWORLD_PLAYBOOK.md owns process. notes/INDEX.md is
the decision log: read the relevant note before re-deciding anything it
covers, and record new non-obvious decisions there.

PLAN.md and notes/ are deliberately untracked. Never stage, commit, or
gitignore them. Stage explicit paths only; never `git add -A` or `git add .`.

## Layout
- `apworld/gta_vice_city/`: the AP world package. Hand-written Python, no
  generators. All access logic lives in `rules.py` as boolean predicates;
  diffs there are logic, everything else is plumbing.
- `apworld/gta_vice_city/client/`: bridge client on CommonClient, bundled in
  the world and registered as a launcher component. Hosts the localhost
  listener; the ASI connects to it. `scripts/build_apworld.py` links the world
  into the Archipelago checkout, packages it (client included) into a
  `.apworld` with an Archipelago manifest, and installs it to the frozen
  install's `custom_worlds`.
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
- Money never gates logic. All money is free-roam grindable; cash items
  exist only to reduce grind.
- Toggle semantics: a disabled check class behaves fully vanilla in game.
  The content stays playable, its vanilla rewards reactivate, its locations
  do not exist, its class-specific items leave the pool. Story missions are
  always on.
- The 100% goal requires every check class enabled; generation rejects it
  otherwise.
- New game per seed. Received state re-derives from AP server state on
  every load and reconnect, never from in-memory bookkeeping alone.
  One-shot grants re-apply only past the saved applied-index; items lost to
  death or old saves stay lost.
- Bridge protocol: newline guard on every outbound frame, chunked large
  frames, version handshake, seed-hash refusal on mismatch.
- All item application (unlock globals, one-shot effects) and DeathLink
  defer on exactly one condition, the game's player-not-controllable flag.
  No other deferral list exists.
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
