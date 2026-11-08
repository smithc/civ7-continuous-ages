# Testing: strategy, live tests and coverage

The tests must prove the design goals ([Vision](vision.md)), not only that nothing breaks. This page
says which kind of test proves what, how the live (scripted) tests work, what is covered today, and the
rules that keep the tests current. The commands and suites are in [Development](development.md#automated-tests).

## Contents

- [Test layers](#test-layers)
- [Live tests](#live-tests)
- [Scenario tests](#scenario-tests)
- [Negative controls](#negative-controls)
- [Coverage of the design goals](#coverage-of-the-design-goals)
- [Keeping the tests current](#keeping-the-tests-current)

## Test layers

| Layer | Tool | Proves | Use it | Time |
| --- | --- | --- | --- | --- |
| Offline build | `build_mod.py`, the skill check `verify.py` | The database of each world loads: no load errors, no broken references, no unclassified table; the transition script edits still match the game; every rule names its proof (`RULE_PROOFS`). | After each change. | 20 s |
| AI autoplay | `iterate.py` with a suite in `autoplay/` | Whole games and world transitions: continuity (nothing reset, nothing lost or duplicated), leaks (content before its gate, from the production and purchase logs), civ choice, governments, hidden yield banks, catch-up costs. | After a rule change; all release suites before a release. | 3 to 30 min |
| Live scenario | `live.py` with a file in `scenarios/` | One exact situation that a script sets up and acts on: a rule that the AI rarely exercises, and the positive side of a gate (the civ can use what it opened). | For each rule that depends on an action the AI may not take, and for each player report. | 1 to 2 min |
| Negative control | `build_mod.py --disable-rule NAME` (or `iterate.py --disable-rule NAME`) | That a test fails without its rule (see [below](#negative-controls)). | Once for each new check or scenario. | 1 to 5 min |
| Probe | `build_mod.py --probe NAME`, then a live scenario | One engine question about a game effect, with test modifiers in a test build only. | Before a rule uses an engine feature that the base game uses differently. | 1 min |
| Base-game control | `iterate.py --control` | What the base game does in the same setup: the mod's logging and automation test, none of its data, rules or transition script. Most checks then fail; read the records you need. | When a finding might be base-game behavior. | 5 min an age |
| UI test | `ui_test.py` | The civic tree screen: lines and hover highlight. It fails when a view recorded no line pieces or no hover civics. | After a change to the tree layout. | 2 min |
| Save compatibility | `tools/savecompat.py` and the suite `ContinuousAgesFromSaveCompat.json` | Saves of the previous version load and keep their state. | Before a release ([Releasing](releasing.md#save-compatibility)). | 5 min a save |

Rules for choosing:

- If the proof needs the AI to do something specific (sail deep ocean, meet a civ, train a unit, take
  a civ), write a scenario. Autoplay can show it only by chance: in about 130 runs, no civ past its
  gate ever had more than one unit on deep ocean in the Antiquity world, and no run ever showed an
  upgrade across ages.
- If the proof is about a whole game (continuity through transitions, the AI's own use of the rules),
  use autoplay. A fixed-civ suite (for example `ContinuousAgesTimeTested.json`) makes it repeatable, and
  `ContinuousAgesDefault.json` with `--set MapSeed=N --set GameSeed=N` covers the default setup (random AI
  civs, which can come from any age).
- Engine queries from the UI context answer reliably only for the local player (slot 0 in a live game).
  In autoplay, read the logs (production, purchases, gossip, CSV files) for AI civs. The report marks
  the other queries "NOT RELIABLE".

## Live tests

The game serves a Chrome DevTools Protocol endpoint for its UI view on port 9444. This is on by default
(AppOptions.txt `UIDebugger`), so no option change is needed and achievements are not affected.
`live.py` uses it to run JavaScript in the game's UI context, the same context as the game's screens.
There is no channel into the gameplay script context; the script changes the game through the same
operations that the game's screens and its FireTuner panels send.

Note: the game opens this port on all network interfaces (0.0.0.0). That is the base game's behavior.

Facts that a scenario must respect (live tests of 2026-11-07, worker 1):

- **Resource assignment is open only on turn 1** in these test games (`Players.get(id).Resources.isResourceAssignmentLocked()`):
  with the mod and with the base-game control build (`--control`), in a normal game too. The mod does not cause
  it. A resource effect that counts assigned resources is therefore tested on turn 1 (`old_resources.js`).
- **Each debug grant of a tech adds one depth** (`GRANT_TREE_NODE`; `FullyUnlock` does not give the mastery).
  Grant again for an item that needs the mastery, and check `Game.ProgressionTrees.getNode(...).depthUnlocked`.
- `WorldBuilder.MapPlots.setResource` does not replace a resource: clear the plot first. A resource counts only with
  its matching improvement.
- **A node granted by debug in an earlier world did not unlock its units after a transition** (the Swordsman after the
  Exploration Breakthrough granted in the Antiquity world; 20261107-204543-w1). Normal research does: a civ past its
  Breakthrough in Antiquity built a Courser in the Exploration world (20261101-191315-w2, player 3). Grant the nodes in
  the world where the test checks them.
- **The game refuses a missionary to a civ without a founded religion.** The game offers a religion
  (`Religion.canCreateReligion()`) only in the Exploration world; `PlayerOperationTypes.FOUND_RELIGION` founds one,
  also in the Antiquity world (test setup beyond normal play).
- **A purchase needs a free plot next to the city** ("No suitable location to spawn this Unit."); a small capital
  with units around it refuses every purchase. On the first turn of a new world a city also refused the control unit
  once: check on a later turn.
- **The engine reads `Unit_TransitionRetains` of the world that ends**, not of the world that loads: each age's base
  list names its own unique commanders, and a row deleted in the Modern data did not remove a missionary at the Modern
  load (20261107-204942-w1).

Two ways to get a live game:

- **Automation test `CALive`** (the default): the suite `autoplay/ContinuousAgesLive.json` sets up and hosts
  the game (civs, seeds, map; `HumanPlayers=1`) and leaves slot 0 to the script.
- **A normal game** (`live.py start --manual`, `live.py scenario ... --manual`): the game starts at its main
  menu without automation, and `live.py` hosts a game with the same setup calls as the automation.

The helpers in the game (`globalThis.caLive`, file `checks/ca-live.js`; `live.py` injects it into a normal
game after each page load):

| Helper | Does |
| --- | --- |
| `advance(n)` | The AI plays slot 0 for about n turns (Autoplay), then gives it back. The count is not exact; it returns the turn. |
| `endTurn()` | Ends slot 0's turn without the AI. It works with open turn blockers. Right after `advance` the game can ignore the request, so it is sent again; it fails after 2 minutes. |
| `toAgeEnd()` | Takes slot 0 to the age's end (needs a build with short ages, `--age-points N`). |
| `canTrain(unit)` | The engine's answer for training a unit in slot 0's capital, and `getBuildUnit`. |
| `grantNode(node)`, `grantNodeAndWait(node)` | Grants a tech or civic with the debug operation `GRANT_TREE_NODE` (the game handles it a moment later). |
| `createUnit(type, x, y)` | Places a unit with the debug operation `CREATE_ELEMENT`. |
| `transition()` | Calls `transitionToNextAge`, as the legends screen does, after the age has ended. |
| `hasNode(node)`, `log(record)`, `finish(ok)` | Node state; a `[CA-CHECK][SCENARIO]` record; end of the automation test (the game quits). |

Found in live tests on game 1.5.0 (build 44):

- `GRANT_TREE_NODE` and `CREATE_ELEMENT` work in the retail game without FireTuner.
- `CREATE_ELEMENT` places a unit only on a plot that the player has revealed (`Visibility.revealAllPlots(id)`,
  as the tuner panels do), and moves it to the nearest valid plot. Check the unit's real position.
- The map reveal alone met a homeland civ, but not a civ of the Distant Lands.
- `EFFECT_PLAYER_DISABLE_BUILD_UNIT`: the dynamic form (no `permanent`, no `PermanentlyDisabled`) works
  with a turn or a node requirement, in the same turn. With `PermanentlyDisabled` and no `permanent`, it
  does nothing (`scenarios/probe_disable_gate.js`).
- `Game.AgeProgressManager.updateAgeProgressionPoints` (a tuner panel call) crashed the game in its age-end
  code when the UI called it. Use a build with short ages instead.
- **The human's civ at a world transition cannot be chosen by a script.** With an automation test, the game
  makes the transition itself and gives slot 0 a random civ (the slot's setting is "RANDOM"; setting a civ
  there before the age end did not change it). In a normal game started by `live.py`, the game also chose
  the civ itself (the same civs as with the automation test for the same seed), and the civ selection
  screen did not come. So the human's transition screens (civ selection, government, legacy cards) are
  still tested only by a person. Ending the automation test does not help: the game then goes back to the
  main menu.
- **The base game does the same** (comparison of 2026-10-31, 8-point ages, slot 0 founds its capital and
  only ends its turns, `scenarios/human_transition.js` steps): with the control build (`--control`, no rules
  of the mod) the human's last turn end led straight to the Exploration world, with no legends screen and no
  civ selection screen, and Egypt became Hawaii; with the mod, exactly the same. Also the same without the
  launch option `-bypassStartButton`. So the skipped screen comes from the scripted setup, not from the mod.
  A game started from the game's own menus was not tested this way.

FireTuner (port 4318) reaches the same UI context, but it needs `EnableTuner 1` before the game starts,
which blocks achievements and marks saves. The tests do not need it.

## Scenario tests

`python live.py all` runs every scenario in `scenarios/scenarios.json`, one new game each, and writes
`build/scenarios/<time>-all.md` (last full set: 20261031-142355, all 7 passed in about 6 minutes). An entry
can name build options (`"build": [...]`); `live.py all` installs that build first and the default test
build at the end. Each scenario has a control step that must fail without the rule (for example "behind the
gate: not met"), so a scenario cannot pass by accident.

In the release set 20261101-191259 (6 games at once), `meet_distant.js` failed one setup check (run
20261101-200105-w1): the game created the ship after the fixed 2-second wait, so the check found no ship.
The ship was in place for the control step, and the 4 checks of the rule passed. Three other scenarios had
the same fixed waits. Now `caLive.createUnitAndWait` (it waits up to 15 seconds for the new unit) and
`caLive.waitFor` (it polls a condition for up to 15 seconds), in `checks/ca-live.js`, replace the fixed waits
after a unit creation in `meet_distant.js`, `ocean_damage.js`, `deep_ocean_turn.js` and
`upgrade_across_ages.js`, after the move in `deep_ocean_turn.js`, and after the upgrade in
`upgrade_across_ages.js`. The 4 scenarios passed with these changes in one worker, with no other game
(`build/scenarios/20261102-094405-w1-all.md`: 4 of 4, all 23 checks). They have not run next to other games yet.

| Scenario | Proves | Settings |
| --- | --- | --- |
| `rule_2i.js` | Rule 2i: before its Breakthrough a civ trains the base unit that its unique unit replaces; after it, only the unique unit. A base unit of another civ's pair stays enabled. | Ming; Mughal |
| `meet_distant.js` | A civ past its Exploration Breakthrough meets a civ of the Distant Lands in the Antiquity world; behind the gate it does not (the base game's block). One side's flag is enough. | Egypt, continents map |
| `ocean_damage.js` | Rule 6b: past the gate, a Cog on deep ocean takes damage (20 in one turn) until Shipbuilding; behind the gate, Tonga's Tehina takes none. | Tonga |
| `ocean_cross_world.js` | Deep-ocean damage across the world transition (a player report of 2026-11-08: "the penalty is back in the Exploration world"), build `--age-points 8 --fast-test 0.01`. Antiquity world: past the gate, a Cog takes damage (control); Shipbuilding **researched** the normal way (prerequisites granted, then `SET_TECH_TREE_NODE`, 1 turn), not granted by debug; then a new Cog takes none. Exploration world: the kept Cog and 3 new ships take none in 2 turns (the test). Passed in 20261108-110207-w1 and 110815-w1. Negative control `--probe ocean_unprotected` (Shipbuilding's protection removed): both "no damage" checks failed, 14 and 31 damage (20261108-111047-w1). | the cheap-tech build |
| `deep_ocean_turn.js` | Rule 6: past the gate, a ship ordered across deep ocean stops on the first deep-ocean plot until Shipbuilding; with Shipbuilding it goes on. Behind the gate a ship does not enter deep ocean, although the engine's `canStart(MOVE_TO)` says yes. | Egypt |
| `gate_content.js` | Goals 3 and 5: an Exploration unit (Knight) and building (Wharf) are locked before the tech Breakthrough and usable after it. | Egypt |
| `upgrade_across_ages.js` | Rule 2g: a Swordsman cannot upgrade to a Man-at-Arms before the gate; after the gate and Heraldry, the upgrade works. | Egypt |
| `old_resources.js` | Rule 2j: on turn 1 of an Exploration game, Hides (valid only in Antiquity) put on the Camp plot of the capital's Ivory and assigned gives its Antiquity effect (+3 Production). Controls: Ivory unassigned, then put back and assigned, changes the yields. Passed in 20261107-142234-w1. A resource counts only when assigned, and in these test games assignment is open only on turn 1, so the scenario does not end a turn. | Egypt, `StartAge=AGE_EXPLORATION` |
| `world_projects.js` | Rules 2k and 2l: for each project that feeds a world system and needs no building, the civ gets its tech (to the depth the project needs; each debug grant adds one depth), and the capital is asked whether it can start it. An achievement of another world age can be started; one of the world age can (control); a final project of another age cannot (all finals need a building, so this scenario does not test them; `project_achievements.js` does, with placed buildings). Passed in the Antiquity world (20261107-154652-w1: Heliocentric Model and Invent Calculus) and the Exploration world (20261107-154729-w1: Chart the Stars and Spherical Earth). | Egypt; and `StartAge=AGE_EXPLORATION` |
| `project_achievements.js` | Rules 2l and 2k in one game of 4 phases on a short-age build (`--age-points 8`), 32 checks. **Antiquity:** no achievement before its tech (control); with the techs, the 2 Antiquity and 2 Exploration achievements can be started; Chart the Stars and Spherical Earth complete (debug `completeProduction`) and the rewritten Antiquity science triumph triggers in its own world (control); Heliocentric Model and Invent Calculus complete early; 4 tags read 1. A save (`Network.saveGame`) and a load in the same process (`Network.loadGame`). **After the load:** tags 1, the 4 blocked, the triumph still earned. **Exploration:** the Exploration science triumph triggers at world start (both projects built in Antiquity); tags 1; the 4 blocked; with the Modern Breakthrough and debug-placed buildings (a building that cannot be placed fails the run: no silent skip), Launch Satellite (Modern achievement) can be started, and the final projects Crewed Space Flight Prep (repeatable) and Break the Sound Barrier (one-winner triumph) cannot; Trans-Oceanic Flight (Modern achievement) completes and leaves its tag; a save for `project_tags_load.js`. **Modern:** after two transitions tags 1 and the 4 blocked; Trans-Oceanic Flight keeps its tag and stays blocked; controls: Break the Sound Barrier can be started in its own world, the Modern science triumph is not earned before it and is earned when it completes (the base game's rule), it leaves no tag; Prep and Launch Satellite can be started. Passed in 20261107-182529-w1 (Break the Sound Barrier final), and with the "done" sets (completed or tag) in 20261107-220723-w1 (32 checks; `project_tags_load.js` 20261107-221002-w1). Before that change: 20261107-173555-w1 and 20261107-174943-w1, with Break the Sound Barrier as an achievement. Phases end the age's last turn from a timer and return `transition: {auto: true}`, or start a load and return `reload: true` (`live.py` waits for the loaded game). | Egypt, `--age-points 8` |
| `project_tags_load.js` | Rule 2l's record in a **new game process**: the suite `ContinuousAgesLiveLoad.json` loads the save `CA_TAGTEST_EX` (base `LoadGame` test, then CALive). The Exploration world (control); the Exploration science triumph from the tags; the 4 tags and Trans-Oceanic Flight's tag are there, and none of these projects can be started; the final project Break the Sound Barrier stays blocked. Passed in 20261107-182823-w1 (6 checks; earlier forms 20261107-173849-w1, 175233-w1). Run it after `project_achievements.js` with the same build (the next entry in `scenarios.json`). | the save of the run before |
| `update_040.js` | Rule 2l in a game **updated from 0.4.0** during a world age (build `--age-points 8`; suite `ContinuousAgesLiveLoad.json`, save `CA_UPD040_AQ`). Phase 1, the loaded Antiquity world: the save and the rule's modifiers in the database (controls); Chart the Stars, completed under 0.4.0, blocked and without a tag; the known limit: with Mathematics and the Exploration techs granted, Spherical Earth and Heliocentric Model still cannot be started (the unlock does not attach in an old save). Phase 2, after the automatic transition: both can be started, a completion leaves its tag, and Chart the Stars can be built once more (known limit). Passed in 20261107-215829-w1 (8 checks). The first form, which expected the unlock in the loaded world, failed (20261107-214128-w1): that run found the engine fact. A `GameModifiers` probe (`--probe attach`) did not attach either (no positive control). | `CA_UPD040_AQ`: `make_save_040.js` with the v0.4.0 test build and `--age-points 8` (20261107-215638-w1), copied to the test saves |
| `religious_units.js` | Rule 2m in the Antiquity world: a leading civ with Piety, a Temple, gold and a religion (founded by the direct operation; the game offers none there, and refuses missionaries without one) cannot train or buy the Missionary; the Swordsman (same Breakthrough) it can (control). Passed in 20261107-205111-w1. | Egypt |
| `religion_modern.js` | Rule 2m at the Modern transition, in a game that starts in the Exploration world (all grants in that world). Exploration: with both Breakthroughs, Piety, a Temple and a religion (normal offer), the Missionary can be trained and bought, and a bought one appears (controls). Modern: the kept Missionary is gone and no civilian unit replaced it; with the religion and the Temple still there, the Missionary cannot be trained or bought; the Scout can (control). Passed in 20261107-205615-w1. | Egypt, `StartAge=AGE_EXPLORATION`, `--age-points 8` |
| `religion_lagging.js` | Rule 2m in the units' own world: a civ behind its tech Breakthrough (Exploration start), with the civic Breakthrough, Piety, a Temple and a religion, can train and buy the Missionary, as in the base game; the Swordsman (tech Breakthrough) it cannot (control). Passed in 20261107-204222-w1. | Egypt, `StartAge=AGE_EXPLORATION` |
| `probe_disable.js`, `probe_disable_gate.js` | Probes (not in the list): which form of the disable effect works. | `--probe disable`, `--probe disable_gate` |
| `make_save_040.js` | Not a test (not in the list): makes `CA_UPD040_AQ` for `update_040.js` with the v0.4.0 test build (`git worktree add <dir> v0.4.0`, then that tree's `build_mod.py --install --checks --age-points 8` with the worker's folders). `--probe attach` (a `GameModifiers` unlock of Spherical Earth) was read with `live.py eval` in the same save. | the v0.4.0 build |

## Negative controls

Each new check was shown to fail without its rule (rule 2 below):

| Control | Result |
| --- | --- |
| `build_mod.py --disable-rule 2i --disable-rule meet --disable-rule 6b`, then `live.py all` | All 4 scenarios of that time failed for the right reason: the base unit mapped to the unique unit and was not disabled after the gate (and the in-game `REPLACE` check failed), the distant civ was not met, and no damage after the gate (set 20261031-132430 to 132623). |
| `iterate.py --disable-rule civic-gate` (the 0.2.1 dead end again), 130 turns | `BANK` failed for all 6 civs (culture banks of 22 to 47 turns of yield, growing), and `CIVICGATE` failed (20261031-132723). |
| `GOV-AGE` on the records of earlier runs | Failed on every run before the government fix (for example 20261029-202958, 20261031-125020). |
| Rule 2i's first form (`PermanentlyDisabled`, not permanent) | Failed in the game (20261031-121009: Merchants after the gate); the probe showed why. |
| `build_mod.py --disable-rule oldres`, then `old_resources.js` | Failed for the right reason: the assigned Hides gave nothing, and both controls passed (20261107-142621-w1). |
| `build_mod.py --disable-rule worldproj`, then `world_projects.js` in both worlds (branch with rule 2k only) | Failed for the right reason: in the Antiquity world a civ could start Heliocentric Model and Invent Calculus (20261107-145209-w1), and in the Exploration world Chart the Stars and Spherical Earth (20261107-145247-w1); the controls passed. Since rule 2l those projects are achievements; the final projects are tested by `project_achievements.js` (Crewed Space Flight Prep and Break the Sound Barrier in the Exploration world), and its negative control (20261107-182915-w1) fails on both. |
| `build_mod.py --age-points 8 --disable-rule achieve --disable-rule worldproj`, then `project_achievements.js` (4 phases) and `project_tags_load.js` | With Break the Sound Barrier final: 11 test checks of `project_achievements.js` failed for the right reason (also: Break the Sound Barrier could be started in the Exploration world, Trans-Oceanic Flight left no tag) and all controls passed, including Break the Sound Barrier and its triumph in the Modern world (20261107-182915-w1); 5 checks of `project_tags_load.js` failed (no tags, projects open, no triumph from tags, Break the Sound Barrier open; 20261107-183204-w1). Before that change, 11 of 28 checks failed (10 test checks and the Break the Sound Barrier tag check) and all controls passed (20261107-174511-w1): tags 0 everywhere; the projects could be started again in each later world; no triumph at world start; Prep could be started in the Exploration world. An earlier run of this control (20261107-173958-w1) also failed the two Modern controls: at Modern turn 1 no Modern project could be started in that game. It did not happen again (3 later runs), and the diagnostics added since (capital, buildings, tech depth, failure reasons) would show the cause. |
| `build_mod.py --disable-rule religion` (with `--age-points 8` for `religion_modern.js`), then the three rule 2m scenarios | Each failed for the right reason, and its controls passed: the Missionary could be trained and bought in the Antiquity world (20261107-205343-w1); it stayed at the Modern load and could be trained and bought in the Modern world (20261107-205801-w1); a civ behind its tech Breakthrough could not train it in the Exploration world (20261107-204325-w1). |
| PROJECT REPEAT (`iterate.py`, CityBuildQueue: a once-per-player project completed twice by one civ) | Failed on three 0.4.0 runs, re-analyzed with the check on 2026-11-07 (`REANALYSIS.md` of 20261101-150859-w2, 20261101-155738-w1 and 20261101-002719: 6 to 11 repeats each, up to 3 completions of Chart the Stars by one civ); passed on rule 2l's 3-world run (20261107-173221-w2: 21 completions, none twice; civs 1 to 3 changed civ at both transitions). |

## Coverage of the design goals

Evidence: **strong** = engine state, a log, or a scenario assertion that fails the test; **weak** =
reported only, or it depends on the AI; **none** = no check. The proof of each numbered rule is also in
`RULE_PROOFS` (`build_mod.py`).

| Goal or rule | Check | Evidence |
| --- | --- | --- |
| G1 continuity: techs, civics, policies, traditions, buildings, units kept | `STATE`/`AGEEND`/`CIVICS`/`POLICIES`, `RELOADUNITS`, `RELOADCONS` (CONTINUITY, LOST, DUPLICATE FAIL) | strong |
| G1: no city becomes a town, no gold or influence cap, old resources stay | `AGEEND` against `RELOAD` (cities, towns, gold, influence) and `RESOURCES` against `RELOADRES` (plots per resource type; the Exploration transition's treasure resources on islands are allowed), before any civ plays (CITY, GOLD CAP, INFLUENCE CAP, RESOURCE FAIL) | strong once a run has the new records |
| G2 own age, G3 snowball | civ age against world age table; production by native age; `gate_content.js` | strong for the gate itself; weak for the AI's use (fast test only) |
| G4 world systems wait for the world | `TRANSITION` count with `--expect-transitions N` (FAIL); legacies of a later age than their world, from `Player_Legacies.csv` (LEGACY FAIL) | strong for the count; weak for legacies (the world is read from the turn numbers); legacy path scores, crises, treasure fleets: none |
| G5 no content before its time (techs, civics, units, buildings, purchases, transition units, abilities, civic trees) | PLAYER, CIVICGATE, TECHGATE, production and purchase leaks, GATEMODS (FAIL); `gate_content.js`, `rule_2i.js` | strong |
| G6 both yields matter: no civic or tech dead end, no hidden bank growing | CIVICGATE and TECHGATE stuck (refused at two checks in a row with prereqs and gate done: FAIL); `BANK` (a bank growing at 3 checks in a row: FAIL) | strong |
| G7 robust to patches | build validation; transition anchors; `RULE_PROOFS` | strong; DLC content of earlier ages: an open check |
| Rule 2i (unique units do not block base units) | `rule_2i.js`; production log "base after gate" (FAIL); `REPLACE` getBuildUnit (FAIL); a kept base unit converted to a rule-2i unique unit at a transition (LEAK FAIL) | strong |
| Distant Lands meeting at the Breakthrough | `meet_distant.js` | strong |
| Rule 6 deep ocean ends the turn until Shipbuilding | `deep_ocean_turn.js` | strong |
| Rule 6b deep-ocean damage | `ocean_damage.js`; `ocean_cross_world.js` (Shipbuilding researched in the Antiquity world, both worlds) | strong |
| Rule 2g upgrades across ages | `upgrade_across_ages.js` | strong |
| Rule 2k final projects stay with their world age | `project_achievements.js`: Crewed Space Flight Prep and Break the Sound Barrier blocked in the Exploration world and open in the Modern world, Break the Sound Barrier's triumph by the base game's rule; `project_tags_load.js`: still blocked after a load in a new process; the build report lists the finals and their reason; the build stops if an effect unlocks one | strong for Prep and Break the Sound Barrier; Launch Rocket and Operation Ivy (a completed legacy path, a wonder): build report only |
| Rule 2m religious units only in the Exploration world | `religious_units.js`, `religion_modern.js`, `religion_lagging.js`; RELOADUNITS names rule 2m removals at the load into a world that does not define the unit (any other religious unit gone still fails) | strong for the Missionary; the unique religious units (Kahuna, Pedanda, Hoceepkileni) follow the same rows (build report), not tested in the game |
| Rule 2l achievement projects: any world, once per game, triumph reads the tag | `project_achievements.js` (two transitions, a load in the game); `project_tags_load.js` (a new game process); `world_projects.js` (both worlds); PROJECT REPEAT in whole games; `update_040.js` (a game updated from 0.4.0); the build stops if a check cannot be rewritten | strong for slot 0: the tag across a load, a new process and two transitions; the Antiquity and Exploration triumphs at world start and in their own world; Modern achievements (Launch Satellite in the Exploration world; Trans-Oceanic Flight's tag into the Modern world). Weak: the AI's triumphs from tags (no AI built a project early in 20261107-173221-w2); a tag kept through a civ change (no repeats by civs that changed civ). Build report only: the legacy card `CARD_AT_MO_SCIENTIFIC_4` reads "done" (no script can choose a legacy card; the same "done" sets are proven by the triumphs). None: the Race triumph set (an open check) |
| Rule 2j kept resources keep their effects | `old_resources.js` (one resource, Hides, in the Exploration world); the build report lists each kept resource with its effects and text source | strong for the effect in the Exploration world; the Modern world and the tooltip text: build report only |
| Rule 3 governments of the world age | `GOV-AGE` (FAIL) | strong |
| Rule 5e abilities after the gate; 5f card grants arrive | reported at the reload | weak |
| Catch-up Research costs | `CATCHUP`: research speed against the base cost, median per node group (FAIL outside 0.85 to 1.20 of the expected 2x, 1.5x or 1x) | strong in a run through a transition; from a save: not judged (no base cost) |
| The civ age banner shows the civ's own age | banner text against the player's PLAYER records (two mismatches in a row: FAIL) | weak: autoplay hides the banner, so it is compared once after each load |
| Civic tree screen layout | `ui_test.py`: line joints, hover highlight, a view with nothing recorded (FAIL) | strong (run by hand) |
| The human's transition screens (civ selection, government, legacy cards) | none: a script cannot reach them (see [Live tests](#live-tests)) | none: needs a person |

Gaps to close next, most important first:

1. **The human's transition screens** need a person (see above).
2. **G4**: the legacy path scores are in no log; a check record of each civ's legacy path scores would
   show a later age's path that scores early. Crises and treasure fleets have no check.
3. **Rules 5e and 5f, positive side**: a scenario that grants a gate and checks that a later civ's ability
   turns on, and that a legacy card's node arrives.
4. **Checks that have not failed in the game yet**: the G1 reset checks (a negative control would keep the
   base game's `capGold` or city-to-town step), `TECHGATE` and the banner comparison (each failed on test
   input only; none failed in the 9 games of 20261031-144559 to 162612). The catch-up table failed in two
   games of that set, from a check bug: the tech and civic Breakthroughs have the same record name, and
   they shared one base cost (20261031-152452, 161244; fixed, both runs then pass on their logs).
5. Open checks in [Known limits](known-limits.md#open-checks).

## Keeping the tests current

1. **Each rule names its proof.** `RULE_PROOFS` in `build_mod.py` maps each rule id of the generated SQL (for
   example `2i`, `6b`) to the check or scenario that proves it; the build stops when a rule id has no entry.
   This map has a row for it. Change both in the same commit.
2. **A new check must fail once.** Before a check counts as proof, show that it fails without the rule:
   a control step in the scenario, a negative-control build (`--disable-rule`), a probe, or a run of the
   previous release. Write the run stamp here.
3. **Each player report becomes a test.** Write the scenario or check before the fix, see it fail, then
   fix. Add it to `scenarios/scenarios.json` so that `live.py all` keeps running it.
4. **Prefer a scenario to waiting for the AI.** If a rule can be shown only when the AI happens to do
   something, it is not covered. Set the situation up.
5. **Before a release**: the offline build, then the release set, `python regression.py run --workers 6`
   (in `generator/`): `live.py all`, the release suites in [Development](development.md#automated-tests)
   (with `ContinuousAgesDefault.json` on several seeds), and the save compatibility test, on parallel game
   workers ([Parallel games](development.md#parallel-games)).
   The set does not have the Regroup suite (`ContinuousAgesTransitionOriginal.json`): run it too.
   Set of 2026-11-07 for the 0.5.0 candidate (git 42b6a00): 15 of 18 items passed, and Regroup passed
   (20261107-235511-w2). Not passed: `live` (a control of `old_resources.js` under load; the scenario now
   waits for state, commit 84617d1); Time-Tested 20261107-221556-w6 (a check gap, U-TOT-SHADOW, fixed and
   re-analyzed; and a leak: a legacy civ's Modern building, an open check); Marathon 20261107-222452-w2 (a
   Mamluk lost at a civ change, an open check; see [Known limits](known-limits.md#open-checks)). Rule 2m's removals at the Modern load were seen in 10 of 13 whole games, and PROJECT
   REPEAT passed in all.
