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
| `generator/checks/` | In-game check scripts and the autoplay test (built in only with `--checks`). |
| `generator/iterate.py` | Build, install, autoplay and analysis in one step. |
| `generator/run_autoplay.ps1` | Starts the game with an autoplay suite and waits for it to end. |
| `generator/autoplay/` | Autoplay suites. |
| `generator/tools/crashstack.py` | Names the game frames of a crash dump's stack. |
| `docs/` | The documentation. |
| `workshop/preview.jpg` | The Steam Workshop preview image (not part of the mod). |
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
| All three ages, end to end | `python iterate.py --suite ContinuousAgesTransition.json --no-fast-test --turns 700 --observe NONE --timeout 150` | about 16 min |
| Civs ahead of the world (seed 777, DLC civs) | `python iterate.py --suite ContinuousAgesTransitionSeed777.json --fast-test 0.4 --turns 700 --observe NONE --timeout 150` | about 15 min |
| Antiquity to Exploration from a save | `python iterate.py --suite ContinuousAgesFromSaveAQ135.json --no-fast-test --turns 20 --observe NONE --timeout 25` | about 4 min |
| Exploration to Modern from a save | `python iterate.py --suite ContinuousAgesFromSaveEX135.json --no-fast-test --turns 20 --observe NONE --timeout 25` | about 5 min |
| Age Transition Impact: Regroup | `--suite ContinuousAgesTransitionOriginal.json` | about 16 min |
| AI civs keep their civs (Persistence) | `--suite ContinuousAgesTransitionPersist.json` or `ContinuousAgesTransitionSeed777Persist.json` | about 16 min |
| Game speeds | `--suite ContinuousAgesTransitionQuick.json`, `...Epic.json`, `...Marathon.json` (marathon: `--turns 1500 --timeout 240`) | 11 / 20 / 32 min |
| Catch-up Research at +100% or +50% (to the Exploration transition) | `python iterate.py --suite ContinuousAgesTransitionCatchUp.json --no-fast-test --turns 200 --observe NONE --timeout 60` (or `...CatchUp50.json`) | about 8 min |
| One human slot (autoplay plays it) | `--suite ContinuousAgesTransitionHuman.json --observe 0` | about 15 min |
| Earth map | `--suite ContinuousAgesEarth.json` | varies |

The from-save suites load the saves `CA_AQ135` and `CA_EX135` from the game's `Saves/Single` folder.
They are not in the repository; make them from your own game (a save at turn 135 of Antiquity and of
Exploration).

`--observe 0` shows the game as player 0. Some engine queries from the UI answer only for the
observed player.

### What a run checks

A run fails on:

- crashes, database errors or script errors;
- leaks: a civ that starts, buys or holds content (including units from a transition) of an age it
  has not entered, or has techs or civics of such an age;
- lost or duplicate military units by class at a transition;
- lost techs, civics, traditions, policies or buildings at a transition;
- an active civ ability of a later-age civ before the civ's Breakthrough;
- a civ choice against the AI mode (for example an AI civ that switches with Persistence), a new civ
  of another age, or a missing record.

Known engine limits are listed by name in the report (see [Known limits](known-limits.md)).

## After a game patch or DLC

1. Run `python build_mod.py` and read the "unclassified tables" line of each world. Classify each new
   table in `classification.py` as content or system.
2. If the build stops on a transition script edit, the game changed its transition script: update
   the edit in `build_test1.py`.
3. Run the three-age test.
