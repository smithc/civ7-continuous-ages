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
| **U-TOWN-PURCHASE** | Base-game behavior: a town that may buy buildings of a tag (a town focus such as Factory Town or Fort Town, Augustus's ability, the civ abilities of Carthage, England, Gaul and Joseon, an Antiquity crisis story; `EFFECT_ADJUST_TOWN_CAN_PURCHASE_TAGGED_CONSTRUCTIBLES`) can buy a building of that tag without the building's own tech or civic. The engine names the missing unlock but allows the purchase. The base game has this within one age; the mod loads every age's content in every world, so a town can also buy buildings of a later age before its civ's Breakthrough. Evidence (game 1.5.1, scenario `town_purchase.js`): Augustus's new town bought the Amphitheater (Engineering), the Pavilion and the Kiln (Exploration techs) and the Opera House (Modern tech) at Antiquity turn 3, and the capital was refused each one (20261110-131632-w1); a town with no tag source (Hatshepsut) could not buy them (20261110-131714-w1); with the control build (base-game rules) Augustus's town bought the Amphitheater without Engineering (20261110-131854-w1). In run 20261110-114253-w1, Egypt (tech age Exploration) bought a Port (Steam Engine) in a Factory Town in the Modern world. The game has no effect that blocks one building for one player (the executable's strings have `EFFECT_PLAYER_DISABLE_BUILD_UNIT` only for units). | Towns with such a source can buy some later-age buildings early, with gold. The run analysis lists such purchases as this known limit: a town (no production row in that world up to the turn after the purchase; never turn 1) buys a building with a tag that a town's tagged purchase names. |
| **U-INDEPENDENT-TIER** | The base game replaces every independent and city-state at each world transition (see [Mechanics](mechanics.md#world-systems)). Independents never research (0 nodes all game, mod and control build), so their own techs do not choose their units: they get the units that enough major civs have unlocked. Evidence (2026-11-10): in the mod's Exploration world, independents made Phalanxes until a second civ of six passed its Exploration Breakthrough (about turn 10), and Swordsmen, Heavy Archers and Cogs from their next units on (turn 12; run 20261110-114253-w1, `Independents.csv`); in a live game, Bronze and Iron Working granted to slot 0 alone changed nothing in 40 turns (worker 4). The exact share is not known. A world's starter units need no tech in the base game, but the Breakthrough in the mod. First-turn `MINORS` records of game 1.5.1: Exploration world, mod `PHALANX, SCOUT`, control `SCOUT, SWORDSMAN`; Modern world, mod `MAN_AT_ARMS, SCOUT`, control `LINE_INFANTRY, SCOUT`; Rifleman at turn 80 in the mod, 60 in the control (runs 20261110-114253-w1 and -w2). | Early in a later world, independents are weaker than in the base game, until enough civs pass the world's Breakthrough. Open: a fix that gives independents the world's starter units (planned for 0.6.0). |
| **U-CAP-AGAIN** | The game carries a civ's settlement cap across a world transition by itself (the base game gives each age a minimum, `TRAIT_INITIAL_SETTLEMENT_CAP`: 8 and 16; it does not reset the cap). In this mod the trees stay completed, and at each load the game attaches again the modifier unlocks of each node's current depth. So a settlement cap unlock (`EFFECT_PLAYER_ADJUST_SETTLEMENT_CAP`, +1) at its node's current depth is added again at each transition, on top of the carried number. A cap unlock of depth 1 on a mastered node is not attached again: that node counts once. The joined trees have 14 such +1 unlocks: 3 on nodes with no mastery (Irrigation, Entertainment, Organized Military), 7 at depth 1 of a node with a mastery, and 4 that the mastery itself gives (Colonialism, Society, Mass Production, Urbanization); civ trees and attribute trees have more. Evidence (2026-11-11): `mastery_unlocks.js`, Feudalism at depth 1: cap +1 at the transition (20261111-143139-w1, 145002-w1); mastered: +0 (20261111-142758-w1, 144620-w1). `mastery_census.js`: the cap rose by exactly 1 at each of the two transitions in four runs, with one cap unlock at its node's depth in each (Hegemony at depth 1, or the mastery unlock of Mass Production; 20261111-144129-w1, 144323-w1, 145439-w1, 145631-w1), and by 8 and 7 per transition in two earlier runs with 8 and 7 such unlocks (20261111-130702-w1 and 130900-w1; these ran a probed form of rule 2n with cap copies). Whole games (settlement cap at the age's end and on the next world's first turn, `AGEEND` and `STATE` records): in the 0.5.1 game 20261110-114253-w1 the six civs gained 2 to 5 at the Exploration transition and 5 to 10 at the Modern transition; in the base-game control 20261110-114253-w2 a civ got the age's minimum (8, 16) or +1. The whole games do not separate the sources of the gain. Not tested: are other sources of settlement cap (attribute nodes, traditions, civ abilities) also applied again? Found while rule 2n was tested; rule 2n leaves these unlocks as they are. | Each civ gains settlement cap at each world transition: +1 for each cap unlock at its node's current depth, which is several per transition in a whole game. It favours every civ, and more so a civ with many cap techs and civics. In every version so far. Open: a decision and a fix (see [Open checks](#open-checks)). |

## Updating a game in progress

### From 0.5.1 to 0.6.0 (rule 2n)

Rule 2n keeps the first-level bonuses of a mastered tech or civic across a world transition (see
[Mechanics](mechanics.md#masteries)). It works through the unlocks of the tech itself, so a game saved with 0.5.1
gets it step by step (scenario `update_051.js`, 20261111-143506-w1, with a save made under the rules of 0.5.1):

- **A tech or civic that the civ researches or masters after the update works at once.** Tested: Shipbuilding
  researched after the update protects ships, and its mastery keeps the protection.
- **Bonuses that a civ lost before the update come back at its next world transition, not before.** A civ that
  mastered Shipbuilding in an earlier world and is in the Exploration world now keeps the deep-ocean damage until the
  Modern world (which has none). The saved game holds the attached bonuses, and a load does not attach new ones.
  Tested with another form of the fix (run 20261111-121754-w1: nothing came back at the load); for rule 2n itself it is
  inferred from the same engine fact, not run.
- **One bonus can count twice until the next world transition:** a specialist cap, a tradition slot or the combat bonus
  of the Pirate Republic civic, when the civ researched the first level before the update and masters the tech after it. The old bonus stays attached in the saved game, and the mastery adds the copy.
  Tested: Currency, +1 specialist cap once more, gone after the transition.
- The settlement cap does not change with the update (U-CAP-AGAIN above).
- `tools/savecompat.py v0.5.1` (2026-11-11): compatible, no saved id removed. The rule adds 33 to 37 modifiers per world
  and changes the target of 12 to 14 unlock rows.

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

### From 0.5.0 to 0.5.1

0.5.1 is 0.5.0 built for game update 1.5.1 (no rule change). Checks of 2026-11-10:

- `tools/savecompat.py v0.5.0` (v0.5.0 rebuilt on 1.5.1 with `oldversion.py`): the same tables in all three worlds.
- `tools/savecompat.py --old <the published 0.5.0 zip, built on 1.5.0>`: one saved id is gone,
  `262B_NARRATIVE_MODIFIER2`, in the Antiquity and Exploration worlds. Game update 1.5.1 deleted it from its own Modern
  data, which the mod copies into the other worlds; the base game lost it in the Modern world too. A save breaks there
  only if that narrative story had fired.
- The save test of the release set plays v0.5.0 rebuilt on 1.5.1 and loads its autosaves with 0.5.1. Those are not saves
  made on game 1.5.0. Five saves (Antiquity turns 100 and 135, Exploration turns 60 and 135, Modern turn 60) each played
  20 turns with 0.5.1: all passed (20261110-140830-w6, 141240-w6, 141337-w5, 141352-w1, 141407-w4).

- **The game update turns off every mod once.** At its first start on a new version the game disables every mod
  (`AppOptions.txt`, `[Modding] DisableModsOnStartupVersion`) and shows "Mod settings reset". A Continuous Ages save
  needs the mod: turn it on again in the Add-ons screen (Additional Content) before you load the game.
- **The great people that 1.5.1 moved into civ abilities wait for the next world transition.** Game update 1.5.1 grants
  the Alim, Conquistador, Saga Hero, Jacobin, Revolucionario and Uparat through new civ-ability modifiers
  (`TRAIT_MOD_GRANT_*`), and rule 5e gates them (`CA_GATE_TRAIT_MOD_GRANT_*`). A modifier that a new version adds does
  not attach when an older save loads (see the section below), so in a game continued from 1.5.0 these civs get none of
  these units until the next world transition (inferred from the engine fact of rule 2l; not seen in a game). The base
  game has the same issue for its own new modifiers.
- **Games of the published 0.5.0 on game 1.5.1** (offline check only, 2026-11-10: the 0.5.0 zip's database loaded into
  the 1.5.1 database with the `validate` steps of `build_mod.py`, and its transition script's imports compared with the
  1.5.1 files): no load issue in any world, and every import is still there. It keeps the 1.5.0 transition (without the
  1.5.1 loop over city-states, which found none in runs 20261110-114253-w1 and 121302-w1) and the 1.5.0 version of the
  content that it copies into other worlds.

### From 0.4.0 to 0.5.0

Tested with a 0.4.0 save that was made for this test (`make_save_040.js` with the v0.4.0 build: Chart the Stars
completed in the Antiquity world) and loaded with 0.5.0 (`update_040.js`, run 20261107-215829-w1). The save test of
the release set (five autosaves of a 0.4.0 game, 20 turns each) is in the release regression.

- **Achievement projects wait for the next world transition (rule 2l).** A modifier that a new version adds does not
  attach when an older save loads (engine fact: rule 2l's unlock, a `TraitModifiers` row, had no effect in the loaded
  world; a `GameModifiers` probe had none either). The rule's tables do apply at once (`RequiresUnlock`), so in the
  loaded world no achievement project can be started: Chart the Stars, Spherical Earth, Heliocentric Model, Invent
  Calculus, Trans-Oceanic Flight, Launch Satellite and Crewed Space Flight Research. At the next world transition the
  unlock attaches, and the projects and their tags work (same run). In a game updated during the Modern world, the
  three Modern achievements stay locked for the rest of the game: their rewards are lost (score points, a unit, a map
  reveal, the economic points of `CARD_AT_MO_SCIENTIFIC_4`). The Modern science victory does not need them: its
  legacy path points come from the Modern triumphs, and no Modern triumph reads an achievement project.
- **Completions of 0.4.0 left no tag.** A civ can build each achievement project that it completed under 0.4.0 once
  more in a later world (same run: Chart the Stars in the Exploration world).
- **Kept resources of an earlier age get their effects at the next world transition (rule 2j).** Their effects are
  new `GameModifiers` rows, so the same engine fact applies (inferred, not tested with a resource). Until then they
  give only their base yield, as in 0.4.0.
- **Religious units (rule 2m)** are SQL only and apply at once: see [Open checks](#open-checks) for a game saved in
  the Modern world.

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
  government choice, legacy cards) were used with the mod in one game only: a human game through the
  transition from Antiquity to Exploration, before the 0.4.0 release (2026-11-01). The transition to the
  Modern world was not played by hand. The live tests can play a human slot,
  but not these screens: in a test the game chooses the human's civ itself, at random (see
  [Testing](testing.md#live-tests)). Please report anything wrong there.
- Multiplayer.
- A whole game that starts in Exploration or Modern (some live scenarios use an Exploration start).
- Map scripts other than Continents and Earth.
- The **Catch-up Research** option (see [Settings](settings.md#catch-up-research-mod-option)): costs in
  the Modern world and of civ-specific civic trees were not measured.
- **The great people that game update 1.5.1 moved into civ abilities** (Alim, Conquistador, Saga Hero, Jacobin,
  Revolucionario, Uparat): the build gates their grant modifiers with rule 5e (`CA_GATE_TRAIT_MOD_GRANT_*`), and in run
  20261110-114253-w1 Abbasid (Persia's new civ, behind its gate) had 0 of 5 gated modifiers active at the Exploration
  load. No game has shown such a grant fire after the civ's Breakthrough.
- The new map **Randomized Earth** (game 1.5.1). Its transition takes the generic resource step, as on every map.

## Open checks

- **One-time grants of a tech or civic at each world load (found with rule 2n, 2026-11-11).** At a world load the game
  attaches again the modifier unlocks of each node's current depth (that is how U-CAP-AGAIN adds settlement cap again).
  Many unlocks are grants, on nodes with and without a mastery: free units (a Merchant from Code of Laws, an Army
  Commander from Discipline), great works (a Codex or Relic from 16 masteries), victory points (15 unlocks, for example
  the science points of Shipbuilding's mastery and of Social Class), one population (Urbanization). Not known: does a
  civ get such a grant again at each transition? One indication against it for units: in the census run
  20261111-134323-w1, slot 0 had Code of Laws at its first level and one Merchant at both loads (`RELOADUNITS`), so the
  first load gave no second Merchant. The unit grants are "run once" modifiers. The victory point unlocks are not (as
  the settlement cap unlock is not): they are the likely repeaters. Rule 2n leaves all grants as they are. Next: a
  scenario that reads the science points of the next age before and after a transition, with Social Class at its first
  level.
- **The settlement cap at a transition (U-CAP-AGAIN): a decision and a fix.** The limit is in every version, and whole
  games show +2 to +5 and +5 to +10 per civ at the two transitions (see [Engine limits](#engine-limits)). Open: does the
  mod want it (it was not designed), which sources add to it (only tree unlocks were varied), and how to stop an unlock
  from being attached again (not looked for yet).
- **Rule 2n: effects with no value test.** The scenarios read the value of specialist cap, tradition slots, deep-ocean
  protection and "deep ocean does not end the move". For the other kept effects on the joined trees (pantheon, unit
  flanking, archaeology, victory point trackers) the census shows only that the copy is active. For an on/off effect the original and the copy are both attached in the world of the mastery;
  that this does no harm is tested for the deep-ocean protection only. The 5 to 7 rows per world on civ trees (among
  them the Pirate Republic combat bonus) were not run in a game. Also not run: a game without the DLC of such a civ
  tree (Assyria, Pirate Republic). The mod then still defines the copies, and a copy's requirement names a tech or
  civic that the game does not load; the offline check loads every DLC set with no issue, and no unlock names such a
  copy. The copies are made at build time from the game's data, as all content of other ages is.
- **A crash when the AI plays a civ with many granted nodes (2026-11-11).** In `mastery_census.js`, slot 0 had every
  node of rule 2n's rows by debug grants (also Modern nodes, without their prerequisites). When the AI then played slot
  0 in the Exploration world, the game crashed as the civ completed a node (20261111-125357-w1; the same without rule
  2n, 20261111-125845-w1; dumps `2D65EF71DECAD46316` and `716F0AD5685EBDA716`: an access violation under "Progression
  Tree Node Depth Unlocked", "Attaching Modifier", in a function that reads `UnlockConfigurationValues` and names
  `EndAgeNextTurn` and `AgeOver`). A third run with `--set CAAuto=1` logged the research in progress (20261111-135548-w1,
  dump `FCE73B4B68DD7C4B16`): at the crash slot 0 was about to complete the Modern **Future Civic** (its only
  prerequisite is Hegemony, which the census grants). Future Civic unlocks `MOD_MO_FUTURE_CIVIC_AGE_PROGRESS`
  (`EFFECT_PLAYER_ADJUST_AGE_PROGRESS`). Two direct tests did not crash: slot 0, played by the script and not by the
  AI, researched Future Civic in the Exploration world with Hegemony granted. With the normal age length it completed,
  the age progress rose by 10 points, and the game played 23 more turns (20261111-140040-w1); with a 12-point age it
  completed and the age ended in its normal way (20261111-140352-w1). So far the crash needs the AI in the human slot
  with the census grants, which is a test condition. The cause is not known.
- **A later-age legacy civ's unique building before the civ's Breakthrough (regression 2026-11-07).** In the
  Time-Tested run 20261107-221556-w6, Inca (played from the Antiquity world, kept its civ into the Modern world, civ
  age Exploration) started Mexico's unique building Portal de Mercaderes in the Modern world on turn 18 (LEAK). Its
  civic records name Mexico's nodes (`MEXICO_ORIGINS`, `MEXICO_RENAISSANCE`) from the Antiquity world on: most
  likely its Antiquity Syncretism gave it Mexico, a Modern civ, as its legacy civ. The building is unlocked by a
  civic of Mexico's own tree (`NODE_CIVIC_MO_MEXICO_PLANES_POLITICOS`). Cause not proven; the 0.5.0 rules do not
  touch this path (the same suite passed in 0.4.0 with another game). Next: a scenario with a Time-Tested civ and
  that legacy choice.
- **A unique unit of the previous civ lost at a civ change (regression 2026-11-07).** In the Marathon run
  20261107-222452-w2, Abbasid changed to Qajar at the Modern load (civ age Exploration). Its one Mamluk was removed,
  and the game left no shadow for it, so the mod's shadow step made no replacement (`LOST UNITS FAIL`, one
  cavalry). In earlier runs Mamluks were converted to Coursers one for one. Cause not known (perhaps a unit in an
  army); the transition script did not change since 0.4.0.
  A second case on game 1.5.1 (0.5.1 regression, run 20261110-141728-w6, seed 2002): Mongolia changed to Qajar at
  the Modern load (civ age Modern). Its one Keshig was removed with no replacement (`LOST UNITS FAIL`, one cavalry).
  At the same load the game converted its 4 Cuirassiers to Qajar's Ghilman. Both cases are a change to Qajar, and
  both `SHADOWS` records have `made` 0, no `unmatched` shadow and `otherTag` 1. So the game did leave a shadow, and
  a kept unit took it. A likely cause (not proven): `caDoubleShadowTypes` counts two shadows for each unit of a
  unique type of the new civ, but a Ghilman that was a Cuirassier before the load left only one shadow. The 4
  Ghilman then take 8 cavalry shadows (`keptBy` cavalry 10 = 4 x 2 + Knight + Lancer), the Keshig's shadow among
  them. Next: a scenario with a civ that changes to Qajar while it holds Cuirassiers and a unique unit of its old civ.
- **Religious units in a game saved in the Modern world (rule 2m).** The game removes religious units at the load into
  the Modern world. A 0.4.0 game saved in the Modern world already holds its missionaries: they stay, and they can still
  convert cities, but no new one can be trained or bought. Not tested with a real 0.4.0 save.
- **The Race triumph set and rule 2l's tags.** In the default triumph set, a project whose triumph has one winner is
  final (Break the Sound Barrier and Operation Ivy), so its race happens in its own world, as in the base game. The Race triumph set
  (`LEGACY_SET_RACE`, a setup option) gives every triumph one winner, and its `_RACE` triumphs share their requirement
  set with the default triumphs. In such a game, the Antiquity and Exploration science `_RACE` triumphs read the tags:
  all civs that built the projects in an earlier world qualify on the same turn, at the world start, and the engine
  picks the winner. Not tested (the tests use the default set). A full fix needs rules per setup option, as Catch-up
  Research has; until players use the Race set, it stays an open check.
- **The AI's triumphs from tags (rule 2l).** The engine evaluates the same requirement for every player, and the
  scenarios prove it for slot 0. In the 3-world run 20261107-173221-w2 no AI built a project of a later age early, so no
  AI triumph from a tag was observed. The game's legacy log (`Player_Legacies.csv`) lists only some triumphs, also in
  0.4.0 runs, so it cannot show it.
- **Balance of kept military resources in the Modern world (rule 2j).** Kept Iron gives its Exploration effect in
  the Modern world: +1 Combat Strength for infantry for each Iron, up to +6, for every civ that holds Iron (an empire
  resource: no assignment is needed). Kept Salt gives +20% Production towards units. The base game removes Iron
  at the Modern transition and Salt at the Exploration transition. Not measured yet. If it is too strong, rule 2j can leave out or limit combat and unit
  effects.
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
- **A rare hang in the game's turn-start autosave (base game).** Iteration 20261031-162612 (one human
  slot, observed as player 0) stopped at the start of Modern turn 2, in the turn of player 0. No log
  changed for 26 minutes, no player had an active turn, the game used about 9 cores, and the UI still
  answered. An exact repeat (the same build and seed, iteration 20261031-174104 in a worktree at commit
  55a94c4) wrote the same logs line for line up to that point, then played on. So the game data and
  the mod's rules, which are deterministic, do not cause it; a timing race in the game is likely. Seen
  again three times on 2026-11-01 in GPU study games **without the mod** (base game, minimum graphics
  quality: Antiquity turns 68, 2 and 59, with 4 or 6 games at once; 3 of about 50 games at minimum quality,
  0 of 43 games at High that day; all three in worker 2). The game sets its own priority class
  (BelowNormal after its window loses the focus), and worker 2's game ran at BelowNormal each time it was
  checked, also at the third hang: at 100% CPU such a game gets much less CPU time than games at
  AboveNormal, which can make a timing race more likely (inferred). Since then a worker's runner holds its
  game at Normal (a job object; docs/development.md, Parallel games); no hang in the next 18 games. Then the
  release set 20261101-191259 (6 workers, minimum quality) had one more hang with the priority held: item
  default1001 in worker 5 stopped at the start of Antiquity turn 31 (iteration 20261101-193700-w5; the runner
  printed `Game priority held at Normal (job object).`), and the repeat (20261101-194356-w5) played on. So
  the priority hold does not stop the hang, and the hang is not special to worker 2. Each time
  the game stopped inside the autosave at the start of a turn, with the same log lines:
  `Serializer.log` ends with `writing Game State to buffer` and `waiting for request of type SAVE` (no
  `Game State to storage`), and `net_message_debug.log` ends with `Queuing Messages Start, State =
  kReceiveAppMessage_SaveInProgress`. A hang farm (6 workers, 2026-11-01, `build/hang-study/farm.py`) had one
  more in 12 games (iteration 20261101-211645-w6, Antiquity turn 35): 6 hangs in more than 280 test games.
  - **Detection and close.** The test builds' hang watchdog (`checks/ca-automation.js`) writes
    `[CA-CHECK][HANG] {"event":"detected",...}` in `UI.log` when a save has been open for 20 seconds with no turn
    event (a normal save takes 0.3 to 0.5 seconds). The runner (`run_autoplay.ps1`) reads it at its next check
    and closes the game at once (in the farm hang the watchdog found the hang 21 seconds after the save
    started). The report says `HANG FAIL`; repeat the run (`regression.py` runs a hung item once more by itself).
    Without the record (an older build, or a stop that is not this hang) the runner closes a game whose logs
    have not changed for 10 minutes (5 in a parallel worker). The suite parameter `CAHangSimulate=<turn>` writes
    the record in a healthy game, to test the close (iteration 20261101-215137-w1: the game closed 2 seconds
    after the record).
  - **No release from a script.** In the farm hang the watchdog tried each runtime call that the game's own
    scripts use near saves and the network, one at a time with 20 seconds each: `setSnapshotEnabled` off and on,
    `Automation.pause`, `Network.saveGame` (it returned `false`), `Network.triggerNetworkCheck`
    (`Network.forceResync` is not a function in a single-player game). None released the save or the turn.
  - **No continue from the last autosave.** A test continued a run in a new game process from the last
    autosave that completed (iteration 20261101-214426-w1 against the same seed without a stop,
    20261101-214446-w2). `Player_Stats.csv`, `CityBuildQueue.csv`, `CombatLog.csv` and the other compared CSV
    files were identical up to turn 41, but `RandCalls.csv` was not: after the load the game picks volcano and
    river plots from other candidate lists (the same seeds, other ranges, for example 176 against 4). So the
    rest of a continued game is not the game of its seed. Also the checks write their "first check after a
    load" records again, which the analysis would add to the real age-start records. A hung run therefore
    starts again from the start.
  - Workers save without the minimap picture (`AddMinimapSnapshotToSaves 0`), which the game draws on the GPU
    for each save; whether that makes the hang rarer is not known yet. Open: does the CPU load at minimum
    quality make the hang more likely? (The priority hold does not stop it: set 20261101-191259.)
- **Extra units from legacy-civ unique units (U-TOT-SHADOW).** A civ that keeps its civ can adopt a
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
  Archers and 4 Warakaq made. Such a Time-Tested civ can then change civ at the transition and has
  the same extra shadows: iteration 20261107-221556-w6, Norman (legacy Rome) to Ming, 2 Legions
  converted to Spearmen and 2 Coursers made. A fix must know the
  legacy civ, or which units the game converted, at the load. The test report names it as
  `KNOWN LIMIT (U-TOT-SHADOW)`, only up to the number of legacy unique units gone (for a civ that
  changed civ, not counting its previous civ's own unique units), so any other duplicate still fails.

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
