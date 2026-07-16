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
- Reserved globals above `$9378` (`$9400` up) are SCM-internal marker handles and
  visibility flags. `$9006`, `$9008`, and `$9009` in the bookkeeping gap below
  `$9378` are SCM-internal scratch (a package counter and two once-guards). The
  ASI never reads or writes any of these.
