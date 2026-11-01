# Development: build, test, architecture

## Contents

- [Requirements](#requirements)
- [Repository layout](#repository-layout)
- [How the mod is built](#how-the-mod-is-built)
- [Build and install](#build-and-install)
- [Automated tests](#automated-tests)
- [After a game patch or DLC](#after-a-game-patch-or-dlc)

## Requirements

- Civilization VII installed (the generator reads the game's own data files).
- Python 3.10 or later. The build uses only the standard library.
- Windows for the automated tests (`run_autoplay.ps1` starts the game through Steam).
- Optional, for crash dump analysis: `pip install -r generator/requirements-tools.txt`.

The default game folder is the Steam folder
`C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VII`. Use `--game-dir` if
your game is somewhere else.

## Repository layout

| Path | Purpose |
| --- | --- |
| `generator/build_mod.py` | Builds the mod for the three world ages from the installed game files (`build/continuous-ages`); `--install` copies it to the game's Mods folder. |
| `generator/build_test1.py` | The edits to the game's age transition script (`TRANSITION_EDITS`) and shared build helpers. |
| `generator/civ7data.py` | Reads the game's modules and simulates the game database of each world age. |
| `generator/classification.py` | Which game tables are content (loaded in every world, locked per civ) and which are systems (stay with their world age). |
| `generator/ui/ca-civ-age.js` | The civ age banner; logs each civ's age and civ choice at each age end. |
| `generator/ui/ca-tree-layout.js` | Tree screen columns from the prereqs inside each tree (the Breakthrough prereq of each age's first civics is in the tech tree; without this the civic tree has empty columns). It also repairs lines over more than one column: the game's `tree-grid.js` links them wrongly when a node has two of them, and its `tree-line.js` draws the last piece at the wrong height when the line's last dummy is a little below the target card (stray lines). The hover highlight skips the tech nodes in the path to a later-age civic (the game's code stops at the first one). |
| `generator/checks/` | In-game check scripts and the autoplay test (built in only with `--checks`). |
| `generator/iterate.py` | Build, install, autoplay and analysis in one step. |
| `generator/live.py` | Live tests: starts a game for a script, runs JavaScript in the game through the UI debugger (port 9444), runs scenario files and writes `build/scenarios/<time>/REPORT.md` (see [Testing](testing.md#live-tests)). Before a launch it closes a crash reporter left by an earlier game (Steam counts it as the game and starts no other); it keeps the id of each game process it starts, and closes that game also after a crash. |
| `generator/scenarios/` | Scenario tests for `live.py` (`scenarios.json` lists them) and probe scenarios. |
| `generator/ui_test.py` | UI test in the game: loads a save, runs `checks/ca-ui-test.js`, takes screenshots and checks the civic tree lines and hover highlight (see [UI test](#ui-test)). |
| `generator/run_autoplay.ps1` | Starts the game with an autoplay suite and waits for it to end. It closes the game it started if `UI.log` and `RandCalls.csv` have not changed for 10 minutes (`-StallMinutes`); the report then says `HANG FAIL`. It compares times in UTC, so a run goes on when daylight saving time ends. |
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
| Earth map | `--suite ContinuousAgesEarth.json` | varies |
| Time-Tested civs from the start (Mughal, Norman, Mongolia, Qing, Inca, Ming): unique units and their base units (rule 2i) | `python iterate.py --suite ContinuousAgesTimeTested.json --fast-test 0.4 --turns 700 --observe NONE --timeout 150` | about 15 min |
| The default setup: random AI civs, which can come from any age (Time-Tested) | `python iterate.py --suite ContinuousAgesDefault.json --no-fast-test --turns 700 --observe NONE --timeout 150 --expect-transitions 3 --set MapSeed=1001 --set GameSeed=1001` (run several seeds) | about 16 min |
| The base game in the same setup (control) | add `--control` (the mod's logging and automation test only; most checks then fail) | as the suite |
| A negative control: a run without a rule, which must fail | add `--disable-rule 2i` (or `6b`, `meet`, `civic-gate`; see `DISABLE_RULES` in `build_mod.py`) | as the suite |
| Civic tree screen (not an autoplay) | `python ui_test.py --save CA_AQ135` (see [UI test](#ui-test)) | about 2 min |
| All scenario tests (not an autoplay; needs `build_mod.py --install --checks`) | `python live.py all` (see [Testing](testing.md#scenario-tests)) | about 1 to 2 min each |
| One scenario, or a live game to drive by hand | `python live.py scenario scenarios/meet_distant.js`, or `live.py start`, `wait`, `eval`, `quit`; `--manual` for a normal game without automation | about 1 min |
| A probe: test modifiers that answer one engine question | `python build_mod.py --install --checks --probe disable_gate`, then a scenario | about 1 min |

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

## After a game patch or DLC

1. Run `python build_mod.py` and read the "unclassified tables" line of each world. Classify each new
   table in `classification.py` as content or system.
2. If the build stops on a transition script edit, the game changed its transition script: update
   the edit in `build_test1.py`.
3. Run the three-age test.
