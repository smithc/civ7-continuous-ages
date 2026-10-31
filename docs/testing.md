# Testing: strategy, live tests and coverage

The tests must prove the design goals ([Vision](vision.md)), not only that nothing breaks. This page
says which kind of test proves what, how the live (scripted) tests work, what is covered today, and the
rules that keep the tests current. The commands and suites are in [Development](development.md#automated-tests).

## Contents

- [Test layers](#test-layers)
- [Live tests](#live-tests)
- [Scenario tests](#scenario-tests)
- [Coverage of the design goals](#coverage-of-the-design-goals)
- [Keeping the tests current](#keeping-the-tests-current)

## Test layers

| Layer | Tool | Proves | Use it | Time |
| --- | --- | --- | --- | --- |
| Offline build | `build_mod.py`, the skill check `verify.py` | The database of each world loads: no load errors, no broken references, no unclassified table; the transition script edits still match the game. | After each change. | 20 s |
| AI autoplay | `iterate.py` with a suite in `autoplay/` | Whole games and world transitions: continuity (nothing reset, nothing lost or duplicated), leaks (content before its gate, from the production and purchase logs), civ choice, hidden yield banks. | After a rule change; all suites before a release. | 3 to 30 min |
| Live scenario | `live.py` with a file in `scenarios/` | One exact situation that a script sets up and acts on: a rule that the AI rarely exercises, and the positive side of a gate (the civ can use what it opened). | For each rule that depends on an action the AI may not take, and for each player report. | 1 to 2 min |
| Probe | `build_mod.py --probe NAME`, then a live scenario | One engine question about a game effect, with test modifiers in a test build only. | Before a rule uses an engine feature that the base game uses differently. | 1 min |
| UI test | `ui_test.py` | The civic tree screen: lines and hover highlight. | After a change to the tree layout. | 2 min |
| Save compatibility | `tools/savecompat.py` and the suite `ContinuousAgesFromSaveCompat.json` | Saves of the previous version load and keep their state. | Before a release ([Releasing](releasing.md#save-compatibility)). | 5 min a save |

Rules for choosing:

- If the proof needs the AI to do something specific (sail deep ocean, meet a civ, train a unit, take
  a civ), write a scenario. Autoplay can show it only by chance: in about 130 runs, no civ past its
  gate ever had more than one unit on deep ocean in the Antiquity world.
- If the proof is about a whole game (continuity through transitions, the AI's own use of the rules),
  use autoplay. A fixed-civ suite (for example `ContinuousAgesTimeTested.json`) makes it repeatable.
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

The test build (`build_mod.py --install --checks`) has the automation test `CALive`
(`checks/ca-automation.js`). It sets up and hosts a game from the suite `autoplay/ContinuousAgesLive.json`
(civs, seeds, map; `HumanPlayers=1`) and leaves slot 0 to the script. The helpers in the game
(`globalThis.caLive`):

| Helper | Does |
| --- | --- |
| `advance(n)` | The AI plays slot 0 for about n turns (Autoplay), then gives it back. The count is not exact; it returns the turn. |
| `endTurn()` | Ends slot 0's turn without the AI. It works with open turn blockers. |
| `canTrain(unit)` | The engine's answer for training a unit in slot 0's capital, and `getBuildUnit`. |
| `grantNode(node)` | Grants a tech or civic with the debug operation `GRANT_TREE_NODE` (the game handles it a moment later). |
| `createUnit(type, x, y)` | Places a unit with the debug operation `CREATE_ELEMENT`. |
| `hasNode(node)`, `log(record)`, `finish(ok)` | Node state; a `[CA-CHECK][SCENARIO]` record; end of the test (the game quits). |

Found in live tests on game 1.5.0 (build 44):

- `GRANT_TREE_NODE` and `CREATE_ELEMENT` work in the retail game without FireTuner.
- `CREATE_ELEMENT` places a unit only on a plot that the player has revealed (`Visibility.revealAllPlots(id)`,
  as the tuner panels do), and moves it to the nearest valid plot. Check the unit's real position.
- The map reveal alone met a homeland civ, but not a civ of the Distant Lands.
- `EFFECT_PLAYER_DISABLE_BUILD_UNIT`: the dynamic form (no `permanent`, no `PermanentlyDisabled`) works
  with a turn or a node requirement, in the same turn. With `PermanentlyDisabled` and no `permanent`, it
  does nothing (`scenarios/probe_disable_gate.js`).

FireTuner (port 4318) reaches the same UI context, but it needs `EnableTuner 1` before the game starts,
which blocks achievements and marks saves. The tests do not need it.

## Scenario tests

`python live.py all` runs every scenario in `scenarios/scenarios.json`, one new game each, and writes
`build/scenarios/<time>-all.md` (last full set: 20261031-131035, all 4 passed in about 4 minutes).
Each scenario has a control step that must fail without the rule (for
example "behind the gate: not met"), so a scenario cannot pass by accident.

| Scenario | Proves | Settings | Passed |
| --- | --- | --- | --- |
| `rule_2i.js` | Rule 2i: before its Breakthrough a civ trains the base unit that its unique unit replaces; after it, only the unique unit. A base unit of another civ's pair stays enabled. | Ming; Mughal | 20261031-123844, 123921 |
| `meet_distant.js` | A civ past its Exploration Breakthrough meets a civ of the Distant Lands in the Antiquity world; behind the gate it does not (the base game's block). One side's flag is enough. | Egypt, continents map | 20261031-124701 |
| `ocean_damage.js` | Rule 6b: past the gate, a Cog on deep ocean takes damage (20 in one turn) until Shipbuilding; behind the gate, Tonga's Tehina takes none. | Tonga | 20261031-124913 |
| `probe_disable.js`, `probe_disable_gate.js` | Probes (not in the list): which form of the disable effect works. | `--probe disable`, `--probe disable_gate` | 20261031-123407 and a live session |

## Coverage of the design goals

Evidence: **strong** = engine state, a log, or a scenario assertion that fails the test; **weak** =
reported only, or it depends on the AI; **none** = no check.

| Goal or rule | Check | Evidence |
| --- | --- | --- |
| G1 continuity: techs, civics, policies, traditions, buildings, units kept | `STATE`/`AGEEND`/`CIVICS`/`POLICIES`, `RELOADUNITS`, `RELOADCONS` (CONTINUITY, LOST, DUPLICATE FAIL) | strong |
| G1: no city becomes a town, no gold or influence cap, old resources stay | cities and towns in the table; gold listed | weak / none |
| G2 own age, G3 snowball | civ age against world age table; production by native age | weak (fast test only) |
| G4 world systems wait for the world | none | none |
| G5 no content before its time (techs, civics, units, buildings, purchases, transition units, abilities, civic trees) | PLAYER, CIVICGATE, production and purchase leaks, GATEMODS (FAIL) | strong |
| G6 both yields matter: no civic dead end, no hidden bank growing | CIVICGATE stuck; `BANK` (a bank growing at 3 checks in a row: FAIL) | strong |
| G7 robust to patches | build validation; transition anchors | strong; DLC content of earlier ages: none |
| Rule 2i (unique units do not block base units) | `rule_2i.js`; production log "base after gate" (FAIL); `REPLACE` getBuildUnit (FAIL) | strong |
| Distant Lands meeting at the Breakthrough | `meet_distant.js` | strong |
| Rule 6b deep-ocean damage | `ocean_damage.js` | strong |
| Rule 6 deep ocean ends the turn until Shipbuilding | none | none |
| Rule 2g upgrades across ages | UPGRADE records (never seen in a run) | none |
| Rule 3 governments of the world age | reported | none |
| Rule 5e abilities after the gate; 5f card grants arrive | reported at the reload | weak |
| Catch-up Research costs | CATCHUP records, not analyzed | none |

Gaps to close next, most important first:

1. **G1 headline resets** have no failing check: add cities, towns, influence and resource plot counts
   to the age-end and reload records, and fail on a drop.
2. **The positive side of the gates**: a scenario that grants a gate and asserts that the civ can train
   or build the content it opened, upgrade a unit across ages (rule 2g), and end a unit's turn on deep
   ocean (rule 6); a check that a later-age tech is never refused once its prereqs and gate are done.
3. **G4**: assert the number of world transitions, and that no legacy path of a later age scores early.
4. Records that nothing reads (CATCHUP, the age banner), and the UI test, which passes when it records
   no lines.
5. Open checks in [Known limits](known-limits.md#open-checks): the Time-Tested AI civ choice and DLC
   content of earlier ages.

## Keeping the tests current

1. **Each rule names its proof.** A rule comment in `build_mod.py` (for example `2i`, `6b`) names the
   check or scenario that proves it, and this map has a row for it. Change both in the same commit.
2. **A new check must fail once.** Before a check counts as proof, show that it fails without the rule:
   a control step in the scenario, a probe, or a run of the previous release. Write the run stamp in the
   rule comment. Example: rule 2i's first form passed the build check but failed in the game
   (20261031-121009); the probe showed why.
3. **Each player report becomes a test.** Write the scenario or check before the fix, see it fail, then
   fix. Add it to `scenarios/scenarios.json` so that `live.py all` keeps running it.
4. **Prefer a scenario to waiting for the AI.** If a rule can be shown only when the AI happens to do
   something, it is not covered. Set the situation up.
5. **Before a release**: the offline build, `live.py all`, the three-age autoplay suites, the
   Time-Tested suite and the save compatibility test.
