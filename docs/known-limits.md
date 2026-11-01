# Known limits and open items

These limits come from the game engine. Each one is named in the test reports. None of them is a
reset of a civ's progress except where noted.

## Contents

- [Engine limits](#engine-limits)
- [Updating a game in progress](#updating-a-game-in-progress)
- [Not tested](#not-tested)
- [Open checks](#open-checks)
- [Ideas not built](#ideas-not-built)

## Engine limits

| Name | What happens | Effect |
| --- | --- | --- |
| **Half swap** | A civ behind its Breakthrough can take a new civ at a world transition (the game's choice). It gets the new name, and the game converts some kept units to the new civ's unique versions. The new civ's unique civic tree, abilities and unique items without a base-game unlock wait for the civ's Breakthrough. A unique unit that replaces a base unit of an earlier age (Settler, Merchant, Scout) no longer blocks that base unit before the Breakthrough; up to version 0.3.0 it did, and the civ had neither unit. Unique army commanders still do (see U-COMMANDER-GAP). | Mostly cosmetic. Avoid it by keeping your civ, or with the AI option Persistence ([Settings](settings.md)). |
| **Prereq in another tree** | The game never opens a prerequisite in another tree: a civic that needs a tech, or a civic of one civic tree that needs a civic of another, stays locked for all time. The base game has no such prerequisite (a query of the base data with all DLC finds 0). A tree's reveal requirement (`RevealRequirementSetId`) only adds a tree; it does not hide one. Evidence: iterations 20261029-141650 (civic needing a tech), 20261029-142802 (civic needing a civic of the main tree), 20261029-142316 (reveal sets). | The civic tree has its own Breakthroughs. Later-age civ trees have no prerequisite gate: unique trees show with the tech Breakthrough and Test of Time trees with the civic Breakthrough (gated reveal modifiers); branch trees keep their base-game conditions. Up to version 0.2.1, no civ could research an Exploration or Modern civic. |
| **U-CIVTREE** (lost own civics) | A civ that keeps its civ can lose 2 to 4 completed civics of its own Antiquity civ tree at the load (for example Egypt, Greece, Han; not Persia or Rome). They become researchable again. No cause was found, and the game has no call to grant them back. | A small reset: 150 to 250 culture per civic to research them again. |
| **U-UNIQUE-COMMANDER** | The game sometimes removes the previous civ's unique commander instead of converting it, with its promotions. | One commander lost in some transitions. |
| **Commander conversion** | The game converts kept commanders to the new civ's unique commander (for example Army Commander to Soltan, or the previous civ's unique commander: Noyan to Soltan in iteration 20261031-214228), also for a civ behind its gate. A script cannot change a unit's type. A test run fails if a kept base unit becomes the unique unit of a rule 2i pair (Settler, Merchant, Scout): those rows are gone, so the game has nothing to convert. | Cosmetic. |
| **U-COMMANDER-GAP** | A civ whose unique commander replaces the Army Commander (Mongolia, Bulgaria, Buganda, Joseon, Qajar) cannot train an Army Commander before its Breakthrough, as in version 0.3.0. The data row that blocks it (`UnitReplaces`, which has no condition) also lets the game convert the unique commander to an Army Commander, with its promotions, when the civ takes a new civ. A test build without the row lost the commander at each such change (iterations 20261031-155019 and 161244: Noyan; before, it was converted in 23 of 26 transitions). | The civ's armies wait for its Breakthrough or the unique commander. |
| **U-POLICY-LOAD** | At the Modern load the game gives every civ the Exploration main-tree policies, earned or not; Levies and Divine Right then replace Conscription and Oratory. | Policies change, not lost. |
| **U-GREAT-PERSON**, **U-CRISIS-UNIT** | Every great person is removed at each load, also for a civ that keeps its civ: Egypt's Tjaty, Spain's conquistadors, Abbasid's Alim al-Shaybani (iterations 20261031-153836, 155019, 155901). The base game keeps only commanders (`Unit_TransitionRetains`). Plague Physicians end with their crisis. | As in the base game. |
| **U-LEVY** | Independent powers research the joined tree at their own pace and can field later-age units, which a major civ can get by a levy before its own Breakthrough. | Rare (seen once, in a test with cheap techs). |

## Updating a game in progress

### From 0.2.1 to 0.3.0

Saves of 0.2.1 load with 0.3.0, and every civ keeps its state. Tested with five 0.2.1 saves (Antiquity
turns 100 and 135, Exploration turns 60 and 135, Modern turn 60), each played 20 turns with 0.3.0,
through the next world transition where there was one, and one 0.2.0 save of a human game
(`tools/savecompat.py` and the load test, see [Releasing](releasing.md#save-compatibility)):

- Cities, towns, units, traditions and policies are the same after the load. The stuck civics open
  at once: each civ can research its civic Breakthrough.
- **Civics finish one per turn for a while, and show "0 turns".** While no civic was open in 0.2.1, the
  game kept each civ's culture in a hidden bank (`CultureOverflow` in the save). When the civics open,
  the game pays the bank out, one civic per turn, and the civic screen counts the bank in its turns. It
  is culture the civ earned, so the mod keeps it (design goal 6). It ends by itself when the bank is
  spent, and the next world transition clears what is left. No script call can read or change the bank.
  Seen in the load test 20261029-184748: Egypt (bank about 3,900) finished one civic per turn from turn
  61 to 65, with 122 culture per turn. New games do not build a bank. The test runs check that
  (`BANK`, see [Testing](testing.md)).
- One difference until the next world transition: a civ that kept its civ already shows the Test of
  Time tree of the current age (0.2.1 showed it but kept it locked). In 0.3.0 that tree has no locked
  first civics, so the civ can research it before its civic Breakthrough. The tree was revealed in
  the saved game, which the new rules cannot take back; the next world transition sets the trees
  again (iterations 20261029-184748, 184915, 185138).

### From 0.3.0 to 0.4.0

Saves of 0.3.0 load with 0.4.0. Tested with five saves of a 0.3.0 game (iteration 20261101-014304:
Antiquity turns 100 and 135, Exploration turns 60 and 135, Modern turn 60), each played 20 turns with
0.4.0, through the next world transition where there was one.

- **AI governments of an earlier age stay until the next world transition (U-GOV-SAVE).** In 0.3.0 an
  AI civ could keep a government of an earlier age (Egypt kept Oligarchy, Rome kept Classical
  Republic). Rule 3 acts at a world transition, so such a civ keeps that government until the next one.
  In the Exploration save of turn 135, every civ took a government of the Modern age at the transition
  (iteration 20261101-010214). In a Modern-world save, the government stays for the rest of the game.
  The test report names it as `KNOWN LIMIT (U-GOV-SAVE)`, only for a government that the civ had at the
  load, in a world that the run did not enter by a transition.

## Not tested

- **Human play at a transition.** The screens a person uses at a world transition (civ choice,
  government choice, legacy cards) have not been used with the mod. The live tests can play a human slot,
  but not these screens: in a test the game chooses the human's civ itself, at random (see
  [Testing](testing.md#live-tests)). Please report anything wrong there.
- Multiplayer.
- A game that starts in Exploration or Modern.
- Map scripts other than Continents and Earth.
- The **Catch-up Research** option (see [Settings](settings.md#catch-up-research-mod-option)): costs in
  the Modern world and of civ-specific civic trees were not measured.

## Open checks

- **An AI civ of a later age took a civ of an earlier age at a transition.** In a game with
  Time-Tested civs (iteration 20261031-121009), the AI civ Ming (an Exploration civ played in
  Antiquity) took Mississippian, an Antiquity civ, in the Exploration world. The AI mode Mirroring
  should switch to a civ of the new age or keep the civ. Not yet compared with the base game; the
  mod does not change the civ choice. The test reports it as `CIV CHOICE FAIL`.
- **Crashes at game start.** About 3 of 60 test games crashed in the first minutes, in the game's
  audio engine. A retry ran clean each time. No crash happened later in a game. `iterate.py` now retries
  a run once when the game crashes before turn 5, and the report says so. One more crash, on
  2026-11-01 in `live.py all`: the third game in a row (scenario meet_distant) crashed 10 seconds after
  its start, during the base game's map generation (`addFeatures`), as the previous game's process
  closed (access violation in the game executable). Its process stayed for 22 minutes, and Steam
  started no other game meanwhile. `live.py` now keeps the id of each game process it starts, stops
  waiting at a new crash dump, and closes that process. In the rerun (`live.py all`, 2026-11-01,
  20261101-021300-all.md), a crash reporter stayed after at least 4 of the 7 test games with no crash
  and no dump; `live.py` closed it before the next launch, and all 7 scenarios passed. Not seen yet
  after a game that a person quits from the menu.
- **A missed age end in one test game (U-AGEEND-MISSED).** In iteration 20261031-214228 (seed 2002)
  the Antiquity age ended and the transition ran (the transition script wrote its records), but the
  test's `GameAgeEnded` handler did not run, so the run has no age-end records for that transition.
  The UI was slow then (many base-game `unit-flags.js` errors). In autoplay the game likely started the
  transition before the UI handled the event. The mod's own `GameAgeEnded` handler only writes test
  records. The other 188 world transitions of the stored runs (`build/iterations`, 153 runs) all reached
  the handler. The report now names it as
  `KNOWN LIMIT (U-AGEEND-MISSED)`, counts the transition, and matches each reload with its age end by
  the new world age (before, the next age end was compared with the wrong reload and failed).
- **One hang in 146 test games.** Iteration 20261031-162612 (one human slot, observed as player 0)
  stopped at the start of Modern turn 2, in the turn of player 0. No log changed for 26 minutes, no
  player had an active turn, the game used about 9 cores, and the UI still answered. An exact repeat
  (the same build and seed, iteration 20261031-174104 in a worktree at commit 55a94c4) wrote the same
  logs line for line up to that point, then played on. So the game data and the mod's rules, which are
  deterministic, do not cause it; a timing race in the game is likely. Not seen again. The test runner
  now closes a game whose logs have not changed for 10 minutes, and the report says `HANG FAIL`.
- **Extra units for a civ that keeps its civ (U-TOT-SHADOW).** A civ that keeps its civ can adopt a
  "legacy" civ of the new age with the Test of Time civic Syncretism (`MOD_SYNCRETISM`,
  `EFFECT_PLAYER_GRANT_SYNCRETIC_CHOICE`), with that civ's traits (`LegacyCivilizationTraits`), and
  can build that civ's unique units (rule 5j: after the civ's Breakthrough tech). New in version
  0.3.0: up to 0.2.1 the Test of Time tree was locked, so no civ got a legacy civ. At the
  next load the game converts those units to their base types and leaves two shadows for each. The
  mod's shadow step counts two shadows only for the unique units of the civ's own civs, so the extra
  shadows make new units. Iteration 20261029-150344: Rome (legacy Norman), 17 Chevaliers, then 15
  converted and 17 Swordsmen made (retagged to Rome's infantry class). Iteration 20261029-152811:
  Egypt (legacy Majapahit), 7 Cetbang converted to Cogs, and 6 Cogs made. A civ of a later age played
  from the start (Time-Tested) has the Antiquity Test of Time tree, so it can also take an Antiquity
  legacy civ: iteration 20261031-125020, Inca (legacy Mississippian), 4 Burning Arrows converted to
  Archers and 4 Warakaq made. A fix must know the
  legacy civ, or which units the game converted, at the load. The test report names it as
  `KNOWN LIMIT (U-TOT-SHADOW)`, only for a civ that kept its civ and only up to the number of legacy
  unique units gone, so any other duplicate still fails.

- **DLC content of an earlier age is not in the later worlds.** The mod copies the content of the
  other ages from the base game only (`other_age_groups(base_mods, ...)` in `build_mod.py`, the same
  since 0.1.0). A DLC civ's own content of an earlier age, for example Assyria's unique unit Magarru
  (`DLC/assyria`, `units.xml`, loaded in Antiquity only), is therefore not in the Exploration world.
  At the transition the game replaces such a unit, and an extra unit can come back. Iteration
  20261029-204508: Assyria (to Inca) had one Magarru and got a Courser and a Horseman. Iteration
  20261031-121009: Bulgaria (to Prussia) had one Boyar; the Modern world has no Boyar data, so the
  shadow step did not see it as a unique unit and made an extra Mortar. Iteration 20261031-152452:
  Bulgaria (to Prussia) had 7 Boyars and got 5 extra units. The test report names this case as
  `KNOWN LIMIT (U-DLC-EARLIER)`, only for a civ that changed civ and only up to the number of such
  unique units gone, so any other duplicate still fails. Other DLC content of an earlier age (unique
  buildings, civic trees) was not checked. To be fixed in a later version: copy the DLC content of the
  other ages too.

## Ideas not built

- **Cheap re-research for U-CIVTREE.** One modifier per Antiquity civ tree, with a large research
  speed-up (`EFFECT_PLAYER_ADJUST_PROGRESSION_TREE_EFFICIENCY`) for civs past the Exploration
  Breakthrough. Lost civics would come back in about a turn. Limit: the game keeps no record of which
  civics were lost, so a civ past its Breakthrough would get all its old civ-tree civics cheaply.
  The Catch-up Research option (off by default) covers this in part: with it on, lost civics of an
  earlier age cost half or two thirds of the turns.
