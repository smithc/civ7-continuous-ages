# Development: build, test, architecture

## Contents

- [Requirements](#requirements)
- [Repository layout](#repository-layout)
- [How the mod is built](#how-the-mod-is-built)
- [Build and install](#build-and-install)
- [Automated tests](#automated-tests)
- [Parallel games](#parallel-games)
- [After a game patch or DLC](#after-a-game-patch-or-dlc)

## Requirements

- Civilization VII installed (the generator reads the game's own data files).
- Python 3.10 or later. The build uses only the standard library.
- Windows for the automated tests, and the Steam client running and logged in (`run_autoplay.ps1`
  starts the game through Steam; a parallel game starts the game from its executable, and the game still
  needs the Steam client).
- For parallel games (the release set): a Windows setting for the Documents folder. It is outside the
  repo, so check it on each PC: `python gamepool.py check` (see [Parallel games](#parallel-games)).
- Optional, for crash dump analysis: `pip install -r generator/requirements-tools.txt`.

The default game folder is the Steam folder
`C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VII`. Use `--game-dir` if
your game is somewhere else.

## Repository layout

| Path | Purpose |
| --- | --- |
| `generator/build_mod.py` | Builds the mod for the three world ages from the installed game files (`build/continuous-ages`); `--install` copies it to the game's Mods folder. The build report goes to `build/continuous-ages-build-report.md`, outside the mod folder, so that it is not uploaded with the mod. |
| `generator/build_test1.py` | The edits to the game's age transition script (`TRANSITION_EDITS`) and shared build helpers. |
| `generator/civ7data.py` | Reads the game's modules and simulates the game database of each world age. |
| `generator/classification.py` | Which game tables are content (loaded in every world, locked per civ) and which are systems (stay with their world age). |
| `generator/ui/ca-civ-age.js` | The civ age banner; logs each civ's age and civ choice at each age end. |
| `generator/ui/ca-tree-layout.js` | Tree screen columns from the prereqs inside each tree (the Breakthrough prereq of each age's first civics is in the tech tree; without this the civic tree has empty columns). It also repairs lines over more than one column: the game's `tree-grid.js` links them wrongly when a node has two of them, and its `tree-line.js` draws the last piece at the wrong height when the line's last dummy is a little below the target card (stray lines). The hover highlight skips the tech nodes in the path to a later-age civic (the game's code stops at the first one). |
| `generator/checks/` | In-game check scripts and the autoplay test (built in only with `--checks`). |
| `generator/iterate.py` | Build, install, autoplay and analysis in one step. `--worker N` runs it as a parallel game worker (see [Parallel games](#parallel-games)). |
| `generator/gamepool.py` | Parallel game workers: one folder per worker (`build/workers/w<N>/`) with its own user folders, the worker's environment, the game started from its executable, the worker's game process, and the check and setup of the Documents setting that parallel games need (`check`, `setup-documents`, `restore-documents`). It knows the game, not the mod. |
| `generator/regression.py` | The release regression set (every suite, the live scenarios, the save load test) on N workers at once: `--list`, `run`, `status`, `rerun`, `stop`. Results in `build/regression/<stamp>.txt`. |
| `generator/live.py` | Live tests: starts a game for a script, runs JavaScript in the game through the UI debugger (port 9444), runs scenario files and writes `build/scenarios/<time>/REPORT.md` (see [Testing](testing.md#live-tests)). Before a launch it closes a crash reporter left by an earlier game (Steam counts it as the game and starts no other); it keeps the id of each game process it starts, and closes that game also after a crash. `live.py --worker N <command>` runs in a parallel game worker; only one live game at a time (port 9444). |
| `generator/scenarios/` | Scenario tests for `live.py` (`scenarios.json` lists them) and probe scenarios. |
| `generator/ui_test.py` | UI test in the game: loads a save, runs `checks/ca-ui-test.js`, takes screenshots and checks the civic tree lines and hover highlight (see [UI test](#ui-test)). |
| `generator/run_autoplay.ps1` | Starts the game with an autoplay suite and waits for it to end. It closes the game it started at once when the hang watchdog of the test build writes its `[CA-CHECK][HANG] ... "detected"` record in `UI.log` (the base-game save hang, [Known limits](known-limits.md#open-checks)), and if `UI.log` and `RandCalls.csv` have not changed for 10 minutes (`-StallMinutes`); the report then says `HANG FAIL`. It compares times in UTC, so a run goes on when daylight saving time ends. In a worker (`CIV7_WORKER` set by `iterate.py --worker N`) it starts the game from its executable, follows only that process, closes only that game's crash reporter, reads only that game's dumps, and closes the game after the time limit (`-TimeoutMinutes`), so the worker is free for the next item. |
| `generator/autoplay/` | Autoplay suites. |
| `generator/tools/crashstack.py` | Names the game frames of a crash dump's stack. |
| `generator/tools/screenshot.py` | Screenshot of the primary screen as PNG (standard library only). |
| `docs/` | The documentation. |
| `workshop/preview.jpg` | The Steam Workshop preview image (not part of the mod). |
| `workshop/description.bbcode` | The Steam Workshop description, with Steam formatting (paste it on the Workshop page). |
| `LICENSE` | MIT License. |

## How the mod is built

The mod is generated, not hand-written. For each world age (Antiquity, Exploration, Modern) the
generator:

1. Simulates the game database of that world age from the installed game files and DLC.
2. Copies the **content** of the other two ages into it (tables on the content list in
   `classification.py`). **Systems** of other ages are not copied. A table on neither list is left
   out and reported as "unclassified", so a new game mechanic is never active in the wrong age.
3. Writes the rules as SQL (`data/<AQ|EX|MO>/continuous-ages-rules.sql`): the joined trees, the
   Breakthrough techs, the gates on content, units kept, policies, civ abilities, legacy cards, and so
   on. Each rule has a comment in the generated file.
4. Writes game effects (`continuous-ages-effects.xml`): copies of game modifiers with a Breakthrough
   requirement added.
5. Validates each world's database: it loads the base game, the DLC and the mod in load order and
   reports load errors and new foreign-key violations.

The mod's transition script (`scripts/age-transition-post-load.js`) is the game's own script with the
reset steps removed. Each edit must match the installed script exactly, so a game patch that changes
the script stops the build instead of producing a wrong copy.

## Build and install

```
cd generator
python build_mod.py --install          # the mod only
python build_mod.py --checks --install # with the test scripts
python build_mod.py --package          # a release zip in build/dist (see releasing.md)
```

Then enable "Continuous Ages" in the game's Additional Content (Mods) screen.

## Automated tests

`iterate.py` builds the mod with the checks, installs it, plays an AI-only game through the game's
automation, and writes `build/iterations/<time>/REPORT.md` with the logs and a copy of the source.

| Purpose | Command (in `generator/`) | Time |
| --- | --- | --- |
| Smoke test: load, Antiquity checks, civs ahead of the world in techs and civics | `python iterate.py --suite ContinuousAgesTransition.json --turns 80 --observe NONE --timeout 25` (fast test 0.1: techs and main civics cost a tenth) | about 3 min |
| All three ages, end to end | `python iterate.py --suite ContinuousAgesTransition.json --no-fast-test --turns 700 --observe NONE --timeout 150 --expect-transitions 3` | about 16 min |
| Civs ahead of the world (seed 777, DLC civs) | `python iterate.py --suite ContinuousAgesTransitionSeed777.json --fast-test 0.4 --turns 700 --observe NONE --timeout 150` | about 15 min |
| Antiquity to Exploration from a save | `python iterate.py --suite ContinuousAgesFromSaveAQ135.json --no-fast-test --turns 20 --observe NONE --timeout 25` | about 4 min |
| A save of an earlier version (copied to `CA_COMPAT.Civ7Save`; see [Save compatibility](releasing.md#save-compatibility)) | `python iterate.py --suite ContinuousAgesFromSaveCompat.json --no-fast-test --turns 20 --observe NONE --timeout 25` | about 5 min |
| Exploration to Modern from a save | `python iterate.py --suite ContinuousAgesFromSaveEX135.json --no-fast-test --turns 20 --observe NONE --timeout 25` | about 5 min |
| Age Transition Impact: Regroup | `--suite ContinuousAgesTransitionOriginal.json` | about 16 min |
| AI civs keep their civs (Persistence): Test of Time trees and legacy civs for every civ | `--suite ContinuousAgesTransitionPersist.json` or `ContinuousAgesTransitionSeed777Persist.json` | about 16 min |
| Game speeds | `--suite ContinuousAgesTransitionQuick.json`, `...Epic.json`, `...Marathon.json` (marathon: `--turns 1500 --timeout 240`) | 11 / 20 / 32 min |
| Catch-up Research at +100% or +50% (to the Exploration transition) | `python iterate.py --suite ContinuousAgesTransitionCatchUp.json --no-fast-test --turns 200 --observe NONE --timeout 60` (or `...CatchUp50.json`) | about 8 min |
| One human slot (autoplay plays it) | `--suite ContinuousAgesTransitionHuman.json --observe 0` | about 15 min |
| A live game from a save, in a new game process (rule 2l's tags) | `python live.py --worker 1 scenario scenarios/project_tags_load.js --suite ContinuousAgesLiveLoad.json` (loads `CA_TAGTEST_EX`, which `project_achievements.js` saves) | about 1 min |
| Earth map | `--suite ContinuousAgesEarth.json` | varies |
| Time-Tested civs from the start (Mughal, Norman, Mongolia, Qing, Inca, Ming): unique units and their base units (rule 2i) | `python iterate.py --suite ContinuousAgesTimeTested.json --fast-test 0.4 --turns 700 --observe NONE --timeout 150` | about 15 min |
| The default setup: random AI civs, which can come from any age (Time-Tested) | `python iterate.py --suite ContinuousAgesDefault.json --no-fast-test --turns 700 --observe NONE --timeout 150 --expect-transitions 3 --set MapSeed=1001 --set GameSeed=1001` (run several seeds) | about 16 min |
| The base game in the same setup (control) | add `--control` (the mod's logging and automation test only; most checks then fail) | as the suite |
| A negative control: a run without a rule, which must fail | add `--disable-rule 2i` (or `6b`, `meet`, `civic-gate`, `oldres`, `worldproj`, `achieve`, `religion`; see `DISABLE_RULES` in `build_mod.py`) | as the suite |
| Civic tree screen (not an autoplay) | `python ui_test.py --save CA_AQ135` (see [UI test](#ui-test)) | about 2 min |
| All scenario tests (not an autoplay; needs `build_mod.py --install --checks`) | `python live.py all` (see [Testing](testing.md#scenario-tests)) | about 1 to 2 min each |
| One scenario, or a live game to drive by hand | `python live.py scenario scenarios/meet_distant.js`, or `live.py start`, `wait`, `eval`, `quit`; `--manual` for a normal game without automation | about 1 min |
| A probe: test modifiers that answer one engine question | `python build_mod.py --install --checks --probe disable_gate`, then a scenario | about 1 min |
| Several of these at once | the same `iterate.py` or `live.py` commands, each with its own `--worker N` (see [Parallel games](#parallel-games)) | as the longest |
| The release set: every suite above, all live scenarios, the save load test | `python regression.py run --workers 6` (`--list` shows the items) | see [Parallel games](#parallel-games) |

See [Testing](testing.md) for which kind of test proves what, and for the coverage of the design goals.

The from-save suites load the saves `CA_AQ135` and `CA_EX135` from the game's `Saves/Single` folder.
They are not in the repository; make them from your own game (a save at turn 135 of Antiquity and of
Exploration).

`--observe 0` shows the game as player 0. Some engine queries from the UI answer only for the
observed player.

Other `iterate.py` options: `--set KEY=VALUE` sets a test parameter of the suite's first test (seeds,
civs); `--expect-transitions N` fails a run with fewer world transitions. A crash before turn 5 of the first
age (a known crash in the game's audio engine at start) is retried once, and the report says so.

### What a run checks

A run fails on:

- crashes, database errors or script errors;
- leaks: a civ that starts, buys or holds content (including units from a transition) of an age it
  has not entered, or has techs or civics of such an age;
- lost or duplicate military units by class at a transition;
- lost techs, civics, traditions, policies or buildings at a transition;
- a reset at the reload, before any civ plays (age end against the transition script's records): fewer
  cities (a city made a town), gold or influence lower by more than 1 (a cap), or fewer plots of a
  resource type that was on the map. The base game's Exploration step replaces some island resources with
  treasure resources (1 to 18 plots in 95 runs); the check allows that many fewer island plots, as the
  step's log line counts them;
- with `--expect-transitions N`: fewer than N world transitions (each age end counts, the Modern one too);
- a legacy (`Player_Legacies.csv`) of a later age than the world it came in. The log has no age column, so
  the world comes from the turn, which restarts in each world; a legacy fails only when its world is certain;
- an active civ ability of a later-age civ before the civ's Breakthrough;
- a later-age civic that the game refuses although its prereqs and its gate are complete, at two
  checks in a row (`CIVICGATE` record; the original 0.2.1 bug), a later-age civic that the game allows
  before its gate, or a later-age civic tree shown before its gate (unique tree: tech Breakthrough;
  Test of Time tree: civic Breakthrough). A node counts as done from depth 1; masteries are not needed;
- the same for techs (`TECHGATE`): a later-age tech that the game refuses although its prereqs and its
  gate (the tech Breakthrough of its age) are complete, at two checks in a row, or one that it allows
  or researches before its gate. An Antiquity tech is the control: when the game refuses it, the
  answers of that check do not count. The tech being researched is not asked;
- Catch-up Research (`CATCHUP`): a node group whose median research speed against the base cost is
  outside 0.85 to 1.20 of the expected value. Expected: 2x (+100%) or 1.5x (+50%) for the techs and
  civics of earlier ages and the Breakthroughs into the world age, else 1x. The game shows the bonus
  in the cost, so the speed is (cost - progress) / (turns - 0.5) / yield times base cost / cost. The
  base cost is the node's cost in this run where no bonus applies, so a run from a save is not
  judged. A group needs 5 samples;
- the civ age banner (`[CA-CHECK][UI]` lines) showing another civ age or world age than the player's
  check, at two comparisons in a row. In autoplay the observer hides the banner, so it is compared
  with the first check after each load;
- a civ choice against the AI mode (for example an AI civ that switches with Persistence), a new civ
  of another age, or a missing record;
- a base unit started after the civ's gate by a civ whose unique unit replaces it (rule 2i, from the
  production log), or the engine still mapping the base unit to a locked unique unit (`REPLACE`);
- hidden culture or science that grows at 3 checks in a row past 3 turns of yield (`BANK`: a tree with no
  next node for the civ, as the civic tree of 0.2.1).

Known engine limits are listed by name in the report (see [Known limits](known-limits.md)).

### UI test

```
cd generator
python ui_test.py --save CA_AQ135   # any save in Saves/Single whose local player is human
```

`ui_test.py` builds and installs the mod with the checks and starts the game with the suite
`autoplay/ContinuousAgesUITest.json`: load the save, run the automation test `CAUITest`
(`checks/ca-ui-test.js`), quit. The test opens the civic tree, scrolls to each age border, and
points at the first civic after it. At each view it logs a `[CA-CHECK][UISHOT]` marker; `ui_test.py`
then takes a screenshot of the whole screen, so keep the game window in front. The report
(`build/uitest/<time>/REPORT.md`, with the screenshots and logs) fails on:

- a break in a line over more than one column: at each dummy card, the line into it and the line out
  of it must meet (measured from the drawn pieces' screen boxes);
- a civic on the path to the pointed civic that the hover highlight does not mark;
- a view that recorded no line pieces, or a hover check that recorded no civics (before, a test that
  found no cards passed);
- a script error in the test.

A run takes about 2 minutes.

## Parallel games

Several test games can run at once on one PC. Each one runs as a **worker** (`generator/gamepool.py`):

```
cd generator
python gamepool.py check                       # READY? (Steam, the game, the Documents setting)
python iterate.py <suite and flags> --worker 1 # as any iterate.py run, in worker 1
python live.py --worker 3 all                  # the live scenarios, in worker 3
python regression.py run --workers 6           # the release set, 6 games at once
python gamepool.py status                      # each worker: game process, turn, last log change
```

### How it works

- **Own user folders.** A worker is the folder `build/workers/w<N>/`. Its `profile/` folder is a small
  copy of a Windows user profile. The worker's game runs with `USERPROFILE`, `LOCALAPPDATA`, `APPDATA`
  and `TEMP` in that folder. The game finds its folders with `SHGetKnownFolderPath`, and that call
  expands `%USERPROFILE%` from the process environment. So each worker has its own Logs, Mods, option
  files, crash dumps and Saves. A new worker gets a copy of the real user's game folder (options, the
  Mods database, legal and account caches; not Logs, dumps or mods).
- **Own build and run folder.** `iterate.py --worker N` builds in `build/workers/w<N>/build/`
  (`build_mod.py --out`), installs into the worker's Mods folder, and writes `build/iterations/<time>-w<N>/`.
  `live.py --worker N` writes `build/scenarios/<time>-w<N>/`. The real Mods folder (the mod the user
  plays) does not change.
- **No Steam launch.** The worker starts `Civ7_Win64_DX12_FinalRelease.exe -autojson <suite>
  -bypassStartButton` itself, with `SteamAppId=1295660` in the environment. With that variable,
  `SteamAPI_RestartAppIfNecessary` (in `steam_api64.dll`) does not hand the launch to Steam, as when
  Steam starts the game. The game still connects to the Steam client: Steam must run and own the game.
  One Steam client serves every worker.
- **Shared parts.** The game install, the Steam client, and the GPU shader caches
  (`%LOCALAPPDATA%\D3DSCache`, `NVIDIA`, `AMD`: each worker has a directory junction to the real folder,
  so a new worker does not compile every shader again). Every program on the PC already uses these
  caches at the same time. Windows Error Reporting writes all dumps to the real user's `CrashDumps`
  folder; a worker run reads there only the dumps with its own game's process id in the name.
- **Test saves.** Before a game starts, a worker run copies every `CA_*.Civ7Save` of the real
  `Saves\Single` folder into the worker's own Saves folder (the from-save suites and the save load test
  need them).
- **Same results.** The same build, seed and flags give byte-identical CSV logs in a worker, alone or
  next to other workers, and in a run without a worker (2026-11-01: `Player_Stats`, `RandCalls`,
  `CityBuildQueue`, `CombatLog`, `Player_Legacies` of 20261101-145822-w1, -150407-w1 and -150427-w2).

### The Documents setting (outside the repo)

The game keeps its saves in `Documents\My Games\Sid Meier's Civilization VII\Saves`. Windows reads the
Documents folder from the registry, `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell
Folders`, values `Personal` and `{F42EE2D3-909F-4907-8871-4C22FC0BF756}`. The Windows default is
`%USERPROFILE%\Documents`, which follows a worker. OneDrive's folder backup writes a full path there
(`C:\Users\<you>\OneDrive\Documents`), and no environment variable can move a full path. Then every
worker gets the same Saves folder, and the autosaves of parallel games (`AutoSave_<age>_<turn>`) overwrite
each other, and each game's "keep the last 10" deletes the other games' autosaves.

`python gamepool.py setup-documents --yes` writes the same folder in the `%USERPROFILE%` form
(`%USERPROFILE%\OneDrive\Documents`, type `REG_EXPAND_SZ`, the form that Windows uses for AppData,
Downloads and the other folders). Normal programs still get the same folder. Only a process with another
`USERPROFILE` (a worker's game) gets another one. It is a change to the user's Windows settings, not to
the repo:

- **Check it on each PC, and after a Windows or OneDrive change.** `python gamepool.py check` shows the
  registry values, the folder of normal programs and of worker 1, and READY or NOT READY. `iterate.py
  --worker`, `live.py --worker` and `regression.py run` make the same check before they start a game, and
  stop with `NOT READY` and the fix (no run folder). One worker at a time can run without the setting with
  `CIV7_ALLOW_SHARED_SAVES=1` (its saves then go to the real Saves folder, as in a run without a worker).
- **Without the change** (another PC, or Documents outside the user profile), runs without `--worker`
  work as before, one at a time.
- `python gamepool.py setup-documents` without `--yes` shows the change. With `--yes` it saves the old
  values once to `build/workers/documents-registry-backup.json`, writes the new ones, and checks that
  normal programs still get the same folder (if not, it writes the old values back at once).
- `python gamepool.py restore-documents --yes` writes the full path again (the form that OneDrive wrote).
- On the development PC, the change was made on 2026-11-01 (`C:\Users\smith\OneDrive\Documents` to
  `%USERPROFILE%\OneDrive\Documents`). After it: normal programs and the legacy `Shell Folders` key had
  the same path as before, and OneDrive's `KfmFoldersProtectedNow` (3584: Desktop, Documents, Pictures)
  did not change.

### Limits

- **Port 9444** (the UI debugger that `live.py` drives) has room for one game: the first game that
  starts gets it, and the others run without it. Autoplay workers set `UIDebugger 0`; a live worker sets
  `UIDebugger 1`, and `live.py` refuses to start, and stops waiting, when another process holds the port.
  So only one live game runs at a time (`regression.py` keeps one live item at most).
- **Runs without `--worker`** start the game through Steam, which starts no second game; they refuse to
  start while any game runs, also a worker's. Do not start workers during such a run either: its runner
  follows the first game process that it finds.
- **`ui_test.py`** takes screenshots of the whole screen: it has no worker mode. Run it alone.
- **Never while the user plays.** A worker does not touch the user's folders, but its game takes CPU and
  GPU. `regression.py` refuses to start while a game runs that no worker started.
- **Delete a worker only with `python gamepool.py reset N`.** It removes the shader-cache junctions
  first: some delete tools follow a junction and empty its target (the real cache folder).
- **Speed.** One game uses about 5 to 7 of the 24 cores of the development PC (Core Ultra 9 285K, 64 GB,
  RTX 5090) and about 4 GB of memory in Antiquity. In a spike of 60 Antiquity turns, 2 games at once each
  played as fast as one game alone, and 4 games at once each took 1.2 to 1.7 s per turn instead of 1.0
  (about 2.7 times the work per hour).
- **The release set on 4 workers** (2026-11-01, `build/regression/20261101-150843.txt`): all 19 items
  passed in 86 minutes; one at a time they take about 257 minutes (3.0 times faster). Each game played
  about 1.5 times slower than alone (the three-age game: 22 minutes instead of 15; the human slot: 49
  instead of 45). With 4 games, the GPU's 3D engine is at 100% (each game draws as many frames as it can,
  about 100 per second, in a maximized window at the High profile), the CPU at about 84%, and the GPU
  memory at about 28 of 32 GB (5.7 to 7 GB per game). That set ran at the High profile, before the worker
  graphics below.
- **Worker settings (since 2026-11-01).** `gamepool.prepare()` writes `WORKER_APP_OPTIONS` into each
  worker's `AppOptions.txt` (`TickIntervalInHZ 0`: no frame cap), `WORKER_GRAPHICS` into its
  `GraphicsOptions.txt` (`Profile Minimum`, every quality option at its lowest, `RenderScale 0.5`,
  `VSync 0`), and `WORKER_USER_OPTIONS` into its `UserOptions.txt`: saves without the minimap
  picture (`AddMinimapSnapshotToSaves 0`), and no camera movement to the local player's combats and no
  historic-moment animation (`LookAtPlayerTurnCombat 0`, `LookAtPlayerOffTurnCombat 0`,
  `PlayHistoricMomentAnimation 0`; they matter in a game observed as player 0). `NotificationCameraPan` and
  `PlayerCombatCameraPan` stay as the user has them: the mod's automation test turns them off in memory, and
  `ContinuousAgesTransitionPanOn.json` (`CAAutoPan=1`) keeps them on. A GPU study of 2026-11-01 (the base
  game without the mod, the same seed, 100 Antiquity turns per game) found:

  | Games at once, setting | s/turn per game | Turns per second, all games | GPU memory per game |
  | --- | --- | --- | --- |
  | 4, High (as the first set ran) | 1.86 to 1.89 | 2.1 | 4.1 GB |
  | 4, frame cap 60 Hz | 2.15 | 1.9 | 4.1 GB |
  | 4, frame cap 30 Hz | 3.27 | 1.2 | 4.1 GB |
  | 4, minimum quality | 1.53 | 2.6 | 1.5 GB |
  | 5, minimum quality | 1.59 | 3.1 | 1.5 GB |
  | 6, minimum quality | 1.64 | 3.7 | 1.5 GB |
  | 6, minimum quality, no camera movement, priority held | 1.47 to 1.83 | 3.8 | 1.4 GB |
  | 6, the same and no frame cap, VSync off | 1.41 to 1.61 | **4.0** | 1.4 GB |
  | 1 alone, High, frame cap 238 (221 fps) | 1.04 | 1.0 | 4.1 GB |
  | 1 alone, minimum quality, frame cap 238 (226 fps) | 0.95 | 1.1 | 1.4 GB |
  | 1 alone, minimum quality, no frame cap, VSync off (468 fps) | 0.90 | 1.1 | 1.4 GB |

  The game does its turn work once per app tick (frame): a frame cap (`TickIntervalInHZ`) slows the turns,
  and cheaper frames make them faster. With 4 games a turn took about 1.27 s plus about 60 frame times;
  a game alone waits for about 22 frames per turn, and the rest (about 0.85 s) is the AI's own work, which
  the frame rate does not change. Minimum quality almost doubles the frames per second and also takes less
  CPU per frame; then the CPU is the limit (90 to 100%). No frame cap with VSync off adds about 5% alone
  and 6% with 6 games; a smaller window adds nothing reliable. All settings gave byte-identical CSV logs.
  So `regression.py` uses **6 workers** by default. The ratios come from early Antiquity: late-game turns
  use more CPU, so the gain can be smaller there.
- **The release set on 6 workers** (2026-11-01, `build/regression/20261101-191259.txt`, commit de3c37f, the
  worker settings above): 18 items in 56 minutes, with one repeat after a hang; one at a time they take
  about 242 minutes (4.3 times faster). The saves of v0.4.0 were kept from the set before, so `saves:play`
  did not run. The longest items set the time: Marathon took 51 minutes (31 alone) and the human slot 45
  (45 alone); the three-age game took 21 minutes (15 alone).
- **Priority.** The game sets its own priority class: Normal at start, AboveNormal some seconds later, and
  BelowNormal when its window loses the focus; it sets it again and again. With several games, the one
  whose window had the focus ran at BelowNormal and the others at AboveNormal: at 100% CPU it played about
  half as fast (2.45 against 1.2 s/turn). The third hang of 2026-11-01 was in such a game (checked: BelowNormal);
  the first two were also in worker 2, whose game ran at BelowNormal each time it was checked. In a
  worker, `run_autoplay.ps1` puts the game into a Windows job object with a priority-class limit (Normal):
  Windows keeps the class and ignores the game's changes. The limit needs the "increase scheduling
  priority" privilege (an elevated shell has it); without it, the runner sets Normal every 5 s, which holds
  only part of the time.
- **Hangs.** In the study, 3 of about 50 games at minimum quality stopped in the base game's turn-start
  autosave, all three in worker 2 (0 of 43 games at High that day, at about 84% CPU). After the priority
  was held, none in the next 18 games, then one in the 18 autoplay games of the 6-worker release set, in
  worker 5 (see [Known limits](known-limits.md#open-checks)), and one in 12 games of a hang farm. The runner
  closes a hung game a few seconds after the watchdog's record (about 25 seconds after the save started; a
  game without the record after 5 minutes without a log change in a worker, 10 without a worker), and
  `regression.py` runs a hung item once more from the start (`RETRY after HANG FAIL` in the results file). A
  continue from the last autosave was tried and dropped: after a load the base game picks some plots from
  other candidate lists, so the game is no longer the game of its seed (Known limits).

## After a game patch or DLC

1. Run `python build_mod.py` and read the "unclassified tables" line of each world. Classify each new
   table in `classification.py` as content or system.
2. If the build stops on a transition script edit, the game changed its transition script: update
   the edit in `build_test1.py`.
3. Run the three-age test.
