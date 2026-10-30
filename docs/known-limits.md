# Known limits and open items

These limits come from the game engine. Each one is named in the test reports. None of them is a
reset of a civ's progress except where noted.

## Contents

- [Engine limits](#engine-limits)
- [Updating a game in progress (from 0.2.1)](#updating-a-game-in-progress-from-021)
- [Not tested](#not-tested)
- [Open checks](#open-checks)
- [Ideas not built](#ideas-not-built)

## Engine limits

| Name | What happens | Effect |
| --- | --- | --- |
| **Half swap** | A civ behind its Breakthrough can take a new civ at a world transition (the game's choice). It gets the new name, and the game converts some kept units to the new civ's unique versions. The new civ's unique civic tree, abilities and unique items without a base-game unlock wait for the civ's Breakthrough. | Mostly cosmetic. Avoid it by keeping your civ, or with the AI option Persistence ([Settings](settings.md)). |
| **Prereq in another tree** | The game never opens a prerequisite in another tree: a civic that needs a tech, or a civic of one civic tree that needs a civic of another, stays locked for all time. The base game has no such prerequisite (a query of the base data with all DLC finds 0). A tree's reveal requirement (`RevealRequirementSetId`) only adds a tree; it does not hide one. Evidence: iterations 20261029-141650 (civic needing a tech), 20261029-142802 (civic needing a civic of the main tree), 20261029-142316 (reveal sets). | The civic tree has its own Breakthroughs. Later-age civ trees have no prerequisite gate: unique trees show with the tech Breakthrough and Test of Time trees with the civic Breakthrough (gated reveal modifiers); branch trees keep their base-game conditions. Up to version 0.2.1, no civ could research an Exploration or Modern civic. |
| **U-CIVTREE** (lost own civics) | A civ that keeps its civ can lose 2 to 4 completed civics of its own Antiquity civ tree at the load (for example Egypt, Greece, Han; not Persia or Rome). They become researchable again. No cause was found, and the game has no call to grant them back. | A small reset: 150 to 250 culture per civic to research them again. |
| **U-UNIQUE-COMMANDER** | The game sometimes removes the previous civ's unique commander instead of converting it, with its promotions. | One commander lost in some transitions. |
| **Commander conversion** | The game converts kept commanders to the new civ's unique commander (for example Army Commander to Soltan). A script cannot change a unit's type. | Cosmetic for a civ behind its gate. |
| **U-POLICY-LOAD** | At the Modern load the game gives every civ the Exploration main-tree policies, earned or not; Levies and Divine Right then replace Conscription and Oratory. | Policies change, not lost. |
| **U-GREAT-PERSON**, **U-CRISIS-UNIT** | Egypt's Tjaty great people are removed at each load. Plague Physicians end with their crisis. | As in the base game. |
| **U-LEVY** | Independent powers research the joined tree at their own pace and can field later-age units, which a major civ can get by a levy before its own Breakthrough. | Rare (seen once, in a test with cheap techs). |

## Updating a game in progress (from 0.2.1)

Saves of 0.2.1 load with 0.3.0, and every civ keeps its state. Tested with five 0.2.1 saves (Antiquity
turns 100 and 135, Exploration turns 60 and 135, Modern turn 60), each played 20 turns with 0.3.0,
through the next world transition where there was one, and one 0.2.0 save of a human game
(`tools/savecompat.py` and the load test, see [Releasing](releasing.md#save-compatibility)):

- Cities, towns, units, traditions and policies are the same after the load. The stuck civics open
  at once: each civ can research its civic Breakthrough.
- One difference until the next world transition: a civ that kept its civ already shows the Test of
  Time tree of the current age (0.2.1 showed it but kept it locked). In 0.3.0 that tree has no locked
  first civics, so the civ can research it before its civic Breakthrough. The tree was revealed in
  the saved game, which the new rules cannot take back; the next world transition sets the trees
  again (iterations 20261029-184748, 184915, 185138).

## Not tested

- **Human play at a transition.** The test runs are AI-only (autoplay plays the human slot), so the
  screens a person uses at a world transition (civ choice, government choice, legacy cards) have not
  been used with the mod. Please report anything wrong there.
- Multiplayer.
- A game that starts in Exploration or Modern.
- Map scripts other than Continents and Earth.
- The **Catch-up Research** option (see [Settings](settings.md#catch-up-research-mod-option)): costs in
  the Modern world and of civ-specific civic trees were not measured.

## Open checks

- **Deep ocean for a civ behind its gate in the Antiquity world.** An engine query reported that such
  a civ's ships could path onto deep ocean, but no unit was ever seen there in the tests, and the
  paths went through plots the civ had not seen. The check was being made stricter when the work was
  paused.
- **Crashes at game start.** About 3 of 60 test games crashed in the first minutes, in the game's
  audio engine. A retry ran clean each time. No crash happened later in a game.
- **Extra units for a civ that keeps its civ (U-TOT-SHADOW).** A civ that keeps its civ can adopt a
  "legacy" civ of the new age with the Test of Time civic Syncretism (`MOD_SYNCRETISM`,
  `EFFECT_PLAYER_GRANT_SYNCRETIC_CHOICE`), with that civ's traits (`LegacyCivilizationTraits`), and
  can build that civ's unique units (rule 5j: after the civ's Breakthrough tech). New in version
  0.3.0: up to 0.2.1 the Test of Time tree was locked, so no civ got a legacy civ. At the
  next load the game converts those units to their base types and leaves two shadows for each. The
  mod's shadow step counts two shadows only for the unique units of the civ's own civs, so the extra
  shadows make new units. Iteration 20261029-150344: Rome (legacy Norman), 17 Chevaliers, then 15
  converted and 17 Swordsmen made (retagged to Rome's infantry class). Iteration 20261029-152811:
  Egypt (legacy Majapahit), 7 Cetbang converted to Cogs, and 6 Cogs made. A fix must know the
  legacy civ, or which units the game converted, at the load. The test report names it as
  `KNOWN LIMIT (U-TOT-SHADOW)`, only for a civ that kept its civ and only up to the number of legacy
  unique units gone, so any other duplicate still fails.

- **DLC content of an earlier age is not in the later worlds.** The mod copies the content of the
  other ages from the base game only (`other_age_groups(base_mods, ...)` in `build_mod.py`, the same
  since 0.1.0). A DLC civ's own content of an earlier age, for example Assyria's unique unit Magarru
  (`DLC/assyria`, `units.xml`, loaded in Antiquity only), is therefore not in the Exploration world.
  At the transition the game replaces such a unit, and an extra unit can come back. Iteration
  20261029-204508: Assyria (to Inca) had one Magarru and got a Courser and a Horseman. Other DLC
  content of an earlier age (unique buildings, civic trees) was not checked. To be fixed in a later
  version: copy the DLC content of the other ages too.

## Ideas not built

- **Cheap re-research for U-CIVTREE.** One modifier per Antiquity civ tree, with a large research
  speed-up (`EFFECT_PLAYER_ADJUST_PROGRESSION_TREE_EFFICIENCY`) for civs past the Exploration
  Breakthrough. Lost civics would come back in about a turn. Limit: the game keeps no record of which
  civics were lost, so a civ past its Breakthrough would get all its old civ-tree civics cheaply.
  The Catch-up Research option (off by default) covers this in part: with it on, lost civics of an
  earlier age cost half or two thirds of the turns.
