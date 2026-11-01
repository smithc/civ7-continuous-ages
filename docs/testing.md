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

| Scenario | Proves | Settings |
| --- | --- | --- |
| `rule_2i.js` | Rule 2i: before its Breakthrough a civ trains the base unit that its unique unit replaces; after it, only the unique unit. A base unit of another civ's pair stays enabled. | Ming; Mughal |
| `meet_distant.js` | A civ past its Exploration Breakthrough meets a civ of the Distant Lands in the Antiquity world; behind the gate it does not (the base game's block). One side's flag is enough. | Egypt, continents map |
| `ocean_damage.js` | Rule 6b: past the gate, a Cog on deep ocean takes damage (20 in one turn) until Shipbuilding; behind the gate, Tonga's Tehina takes none. | Tonga |
| `deep_ocean_turn.js` | Rule 6: past the gate, a ship ordered across deep ocean stops on the first deep-ocean plot until Shipbuilding; with Shipbuilding it goes on. Behind the gate a ship does not enter deep ocean, although the engine's `canStart(MOVE_TO)` says yes. | Egypt |
| `gate_content.js` | Goals 3 and 5: an Exploration unit (Knight) and building (Wharf) are locked before the tech Breakthrough and usable after it. | Egypt |
| `upgrade_across_ages.js` | Rule 2g: a Swordsman cannot upgrade to a Man-at-Arms before the gate; after the gate and Heraldry, the upgrade works. | Egypt |
| `probe_disable.js`, `probe_disable_gate.js` | Probes (not in the list): which form of the disable effect works. | `--probe disable`, `--probe disable_gate` |

## Negative controls

Each new check was shown to fail without its rule (rule 2 below):

| Control | Result |
| --- | --- |
| `build_mod.py --disable-rule 2i --disable-rule meet --disable-rule 6b`, then `live.py all` | All 4 scenarios of that time failed for the right reason: the base unit mapped to the unique unit and was not disabled after the gate (and the in-game `REPLACE` check failed), the distant civ was not met, and no damage after the gate (set 20261031-132430 to 132623). |
| `iterate.py --disable-rule civic-gate` (the 0.2.1 dead end again), 130 turns | `BANK` failed for all 6 civs (culture banks of 22 to 47 turns of yield, growing), and `CIVICGATE` failed (20261031-132723). |
| `GOV-AGE` on the records of earlier runs | Failed on every run before the government fix (for example 20261029-202958, 20261031-125020). |
| Rule 2i's first form (`PermanentlyDisabled`, not permanent) | Failed in the game (20261031-121009: Merchants after the gate); the probe showed why. |

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
| Rule 6b deep-ocean damage | `ocean_damage.js` | strong |
| Rule 2g upgrades across ages | `upgrade_across_ages.js` | strong |
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
   base game's `capGold` or city-to-town step), `TECHGATE`, the catch-up table and the banner comparison
   (each failed on test input only).
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
5. **Before a release**: the offline build, `live.py all`, the release suites in
   [Development](development.md#automated-tests) (with `ContinuousAgesDefault.json` on several seeds), and
   the save compatibility test.
