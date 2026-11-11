# Mechanics: what changes

This page lists each game mechanic that the mod changes, compared with the base game.

## Contents

- [Research](#research)
  - [Joined tech and civic trees](#joined-tech-and-civic-trees)
  - [The Breakthrough techs](#the-breakthrough-techs)
  - [Civics](#civics)
- [The world transition: no reset](#the-world-transition-no-reset)
  - [What is kept](#what-is-kept)
  - [Units](#units)
  - [Cities, gold and influence](#cities-gold-and-influence)
  - [Resources](#resources)
  - [Policies and traditions](#policies-and-traditions)
  - [Governments](#governments)
  - [Legacy cards](#legacy-cards)
- [Content locked by civ age](#content-locked-by-civ-age)
- [Buildings across ages](#buildings-across-ages)
- [Unit upgrades across ages](#unit-upgrades-across-ages)
- [Ocean travel](#ocean-travel)
- [World systems](#world-systems)
- [The civ age banner](#the-civ-age-banner)

## Research

### Joined tech and civic trees

In the base game each age has its own tech tree and civic tree. In this mod:

- The main techs of all three ages form **one tech tree**.
- The main civics of all three ages form **one civic tree**.
- The trees have the same id in every world age, so completed research stays completed across world
  transitions.

A civ can research techs and civics of a later age before the world reaches that age, but only after
the Breakthrough of that tree (see below).

### The Breakthrough techs

Two techs are new:

| Tech | Requires | Cost (standard speed) | Opens |
| --- | --- | --- | --- |
| **Exploration Breakthrough** | Iron Working, Mathematics, Navigation | 885 | The first Exploration techs (Astronomy, Cartography, Machinery) |
| **Modern Breakthrough** | Gunpowder, Urban Planning | 4350 | The first Modern techs (Academics, Military Science, Steam Engine) |

A civ's age is the age of its last Breakthrough tech:

- no Breakthrough: Antiquity;
- Exploration Breakthrough: Exploration;
- Modern Breakthrough: Modern.

The civ's age controls its later-age content: units, buildings and improvements that techs unlock,
starter items, civ abilities, unique items, and ocean travel (see
[Content locked by civ age](#content-locked-by-civ-age)).

### Civics

The civic tree has its own Breakthrough of each age. A civ researches it with culture, as any civic:

| Civic | Requires | Cost (standard speed) | Opens |
| --- | --- | --- | --- |
| **Exploration Breakthrough** | Commerce, Entertainment, Organized Military, Philosophy (the last Antiquity civics) | 900 | Economics and Piety (the first Exploration civics) |
| **Modern Breakthrough** | Imperialism, Social Class, Sovereignty (the last Exploration civics) | 2520 | Modernization, Natural History, Social Question (the first Modern civics) |

- The two trees are independent. A civ with strong culture can research Exploration civics, and use
  what they unlock (policies, wonders, buildings), before its Exploration Breakthrough tech. A civ
  with strong science can be in a later age in techs than in civics.
- So culture always has a use: after the last civics of an age, the civ researches the next civic
  Breakthrough. Only the last age has the base game's repeatable Future Civic (and Future Tech).
- Civ-specific civic trees of a later age: a unique tree shows with the civ's Breakthrough tech, a
  Test of Time tree with its civic Breakthrough, and branch trees (Theology, ideologies) keep their
  base-game conditions. The Test of Time civic Syncretism (a legacy civ) also needs the Breakthrough
  tech, and works only in its own world age. See [Civs and ages](civs-and-ages.md#unique-content-civ-abilities-and-civic-trees).
- Why no tech prereq on a civic: the game never opens a prereq that is in another tree. Up to
  version 0.2.1 the first civics of each later age needed the Breakthrough tech, and no civ could ever
  research an Exploration or Modern civic (a player report; iterations 20261029-141650 and 142802).

Optional: with the **Catch-up Research** setup option, techs and civics of ages before the world age
are faster to research. See [Settings](settings.md#catch-up-research-mod-option).

## The world transition: no reset

The world transition happens as in the base game, when the world's age progress is complete. The mod
replaces the game's transition script with a copy that has the reset steps removed.

### What is kept

| Item | Base game | Continuous Ages |
| --- | --- | --- |
| Techs and civics | Each age has new trees | Kept (one joined tree) |
| Units | Commanders are kept with their promotions (only commanders have promotions); other military units are remade as the new age's types, and units that the armies do not take back can be lost | Kept as they are: type and position; commanders with their promotions. Religious units are removed at the Modern load (rule 2m) |
| Cities | All cities except the capital become towns | Cities stay cities |
| Gold and influence | Capped | Not capped |
| Buildings and improvements | Kept; the base game's rules for older-age buildings apply | Kept; the same rules apply |
| Old-age resources | Removed from the map | Stay on the map, with the effects of their last valid age |
| Policies | The new age's trees replace the old ones | Every policy the civ has earned stays (see below) |
| Traditions | Kept | Kept |
| Civ | The civ takes a new civ (or keeps its civ with Test of Time) | Unchanged: the game still decides (see [Civs and ages](civs-and-ages.md)) |

### Units

- Every unit is kept as it is, except religious units: the game removes them at the load into the Modern world
  (rule 2m, see [World systems](#world-systems)).
- The game also creates replacement units for some units ("shadows"). The mod uses a shadow only to
  replace a unit that the game removed (for example a unique unit of the civ's previous civ). The
  replacement keeps the removed unit's class, and it is the best unit of that class that the civ
  can build in its own age.

### Cities, gold and influence

No city becomes a town, and gold and influence are not capped.

### Resources

- Resources of an earlier age stay on the map. One exception, as in the base game: at the Exploration
  transition, the game replaces some resources on islands with treasure resources (1 to 18 plots in the
  test runs), because treasure fleets are a world system of the Exploration age. The test runs check that no
  other resource leaves the map (`RESOURCES` against `RELOADRES`).
- **A kept resource keeps its effects (rule 2j).** Some kept resources are not valid in the new world age
  (the base game removes them): Hides, Lapis Lazuli, Salt and Wool in the Exploration world, and 18 in the
  Modern world (build of 2026-11-07). A resource's effects belong to each age's data, so up to version 0.4.0 such a resource gave only
  its base yield, and its text described an effect it did not have (a player report). Now it has the effects
  of its last valid age: Salt in the Exploration world gives +20% Production towards units again, and Dates in the
  Modern world gives its Exploration +3 Food and +3 Happiness. Its text is the text of that age. The generator
  finds the resources and their effects in the game data (`kept_resources` in `build_mod.py`; the build report
  lists them). Camels needs no effect row: its extra resource slots are part of its own data. Each resource keeps
  the world's resource class. For example, Rubies is a Bonus resource in the Modern world, not a Treasure
  resource (that class does not exist there).
- As for any resource, an effect counts only for a resource that is assigned to a settlement and has its
  matching improvement (or for an empire resource such as Iron). In the Modern world, kept Iron gives its
  Exploration effect: +1 Combat Strength for infantry for each Iron, up to +6.
- New-age resources do not replace a tile that has a district or an improvement. Without this rule,
  the transition removed improvements and districts.
- On the Earth map, the generic resource step is used. The Earth map's own step removed rural
  districts.

### Policies and traditions

- Each main-tree and branch-tree policy (Theology, the ideologies) is unlocked again for every civ
  that has completed its civic (to the depth that the policy needs). A transition can therefore not
  remove an earned policy.
- Traditions are kept.

### Governments

At a world transition, every civ takes a government of the new world age, as in the base game: the
government choice lists only the world age's governments, and the AI takes one of them too. Up to version
0.3.0 the AI often kept or took a government of another age, because the mod loads the governments of all
ages and the AI follows its civ's favourite government (for example Egypt kept Oligarchy in the Modern
world, and a Time-Tested Mughal took Bureaucratic Monarchy in Antiquity). The test runs check it
(`GOV-AGE`).

### Legacy cards

Legacy cards are chosen at a world transition as in the base game. Some advanced start cards and
transition legacy cards grant a named tech or civic of the new age (for example the science legacy
card that unlocks Academics). For a civ behind its Breakthrough, that grant now waits: the civ gets
the tech when it researches the Breakthrough tech, and the civic when it researches the civic
Breakthrough (for example the Exploration Dedication that grants Piety). (18 card grants: 7 civics,
11 techs.)

## Content locked by civ age

A civ can use content of its own age and of earlier ages. Content of a later age needs that age's
Breakthrough. This applies even after the world has moved on:

- techs of a later age, and units, buildings, improvements, wonders and projects that they unlock (the projects
  that feed a world system, and religious units, have their own rules: see [World systems](#world-systems));
- civics of a later age, and what they unlock, need the civic Breakthrough of that age (see
  [Civics](#civics));
- "starter" units and buildings that a later age gives at its start;
- civ-specific content (see [Civs and ages](civs-and-ages.md)).

A lock never takes away what the base game gives. A unique unit of a later age that replaces a base
unit of an earlier age (for example Mughal's Zamindar, which replaces the Settler) does not block the
base unit before the civ's Breakthrough: the civ trains the Settler. After the Breakthrough the civ
trains the Zamindar and not the Settler, as in the base game. Up to version 0.3.0 such a civ could
train neither (a player report: Mughal had no Settlers in Antiquity). The rule covers 9 pairs: the
Settler (Norman, Dai Viet, Mughal), the Merchant (Ming, Songhai, England, Qing) and the Scout (Inca,
Nepal). The generator finds the pairs in the game data.

The unique army commanders (Mongolia, Bulgaria, Buganda, Joseon, Qajar) are left out. The game keeps
commanders at a world transition. When a civ takes a new civ, the game uses the same data row to
convert the old civ's unique commander to an Army Commander, with its promotions. Without the row,
the game removed the commander (iterations 20261031-155019 and 161244). So these civs have no Army
Commander before their Breakthrough, as in version 0.3.0 (see
[Known limits](known-limits.md#engine-limits)).

When a civ takes a new civ, a unit of one of the 9 pairs is not converted: the game removes it. Its
shadow then makes the base unit (a Sokeman comes back as a Settler, a Mandarin as a Merchant), as the
base game does for a removed unit.

## Buildings across ages

- The game offers only buildings of the current world age (and ageless ones). The mod sets each
  building's age to the earlier of its own age and the world age. So a leading civ can build
  later-age buildings, and in a later world all earlier buildings can still be built.
- Old buildings stay after a transition, and a civ can build over them by choice, as in the base game.

## Unit upgrades across ages

The base game has no upgrade from one age's units to the next age's units, because its transition
remakes armies. With every unit kept, the mod adds these upgrades:

| Class | Antiquity unit | Upgrades to (Exploration) | Exploration unit | Upgrades to (Modern) |
| --- | --- | --- | --- | --- |
| Infantry | Phalanx | Swordsman | Pikeman | Line Infantry |
| Ranged | Archer | Heavy Archer | Arquebusier | Field Cannon |
| Siege | Ballista | Catapult | Bombard | Mortar |
| Cavalry | Horseman | Courser | Lancer | Cuirassier |
| Naval | Quadrireme | Cog | Galleon | Frigate |

An upgrade needs the civ to be able to build the target unit, so the age gates apply.

## Ocean travel

- In the Antiquity world, deep ocean is closed, as in the base game. A civ that researches the
  Exploration Breakthrough gets ocean travel and the other Exploration "baseline" rules for itself
  (ocean travel, embarking, deep-ocean trade, and the Exploration age-balance rules).
- The Exploration rule that deep ocean ends a unit's turn until Shipbuilding is loaded, so
  Shipbuilding keeps its meaning for a leading civ.
- **Deep-ocean damage.** In the Antiquity world, a unit on deep ocean takes the Exploration damage (11
  to 20 each turn) until its civ has Shipbuilding, as in the Exploration world. The amount is a world
  value that only the Exploration data sets, so up to version 0.3.0 nothing took damage in the
  Antiquity world (a player report). Only civs past their gate can reach deep ocean there. A civ behind
  its gate is fully protected, as in the base game's Antiquity (Tonga's Tehina may enter deep ocean in
  Antiquity). The Modern world has no deep-ocean damage, as in the base game.
- **Meeting the civs of the Distant Lands.** In the Antiquity world the game does not let a civ meet
  the civs of the other hemisphere. The base game lifts this only for Tonga. A civ past its
  Exploration Breakthrough can meet them, because its ships can reach them. Up to version 0.3.0 such a
  civ saw their cities but never met them (a player report). Only one of the two civs needs the
  Breakthrough.
- Proof: the scenario tests `scenarios/ocean_damage.js` and `scenarios/meet_distant.js` (see
  [Testing](testing.md)). AI civs almost never sail deep ocean in Antiquity, so autoplay runs cannot show it.
- The Exploration civs' free ship comes once per civ, at the later of its Exploration Breakthrough
  and the Exploration world.

## World systems

These systems stay with the world age and start at the world transition, as in the base game:

- crises;
- legacy paths, triumphs, and golden and dark ages;
- treasure fleets and the Distant Lands;
- independent powers and discoveries. The base game replaces every city-state and independent at each world
  transition. In the `MINORS` records of game 1.5.1, the new world's independents have no tech and a starter army,
  with the mod (run 20261110-114253-w1) and with the control build (-w2). The `RELOADMINOR` record of the transition
  script (city-states only: the game's loop skips independents) found no city-state at either load of -w1. The mod
  keeps this. Independents never research (0 nodes all game, mod and base game), and their units do not follow their
  own techs: they get the units that enough major civs have unlocked. A world's starter units (Exploration: Swordsman,
  Heavy Archer, Courser, Catapult, Cog; Modern: Line Infantry, Cuirassier, Field Cannon, Mortar, Frigate) need no tech
  in the base game, and the Breakthrough in the mod, so early in a world the mod's independents field older units than the base
  game's (see U-INDEPENDENT-TIER in [Known limits](known-limits.md#engine-limits));
- the final victories (Modern world);
- religion steps and diplomacy actions of each age;
- the age's growth curve and balance values.

A leading civ therefore cannot score the next age's legacy paths before the world reaches that age.

**Projects that feed a world system (rules 2k and 2l).** 11 projects give victory points, or a legacy path or a
victory of their age requires them. The game forgets which projects a civ completed at each world transition, so up
to version 0.4.0 a civ built Chart the Stars and Spherical Earth again in each later world (a player report), with
their victory points, Altar purchases and attribute point each time. The mod now puts each project in one of two
groups, found in the game data (`project_groups` in `build_mod.py`):

- **Final projects (rule 2k): built only in their own world age, as in the base game.** A project is final when a
  victory requires it, when it grants legacy path points itself or needs a completed legacy path (a legacy path exists
  only in its world age), when it can be repeated, when it has no single tech unlock, or when a triumph of its age in
  the default triumph set needs it and has one winner (first player only). Today: Launch Rocket (the Modern science
  victory), Operation Ivy (the Modern military victory, and its triumph has one winner), Crewed Space Flight Prep
  (repeatable) and Break the Sound Barrier (its Modern science triumph has one winner). In other worlds a city cannot start them, and the tech tree does not show them.
  Why the one-winner rule: a tag has no date. Built early, every civ with the tag would qualify for the triumph on the
  same turn, at the world start, and the engine, not the first civ to complete the project, would pick the winner. As
  a final project, Break the Sound Barrier is a race in the Modern world, as in the base game.
- **Achievement projects (rule 2l): built at the civ's own age, in any world, once per game.** Today: Chart the
  Stars, Spherical Earth, Heliocentric Model, Invent Calculus, Trans-Oceanic Flight, Launch Satellite, Crewed Space
  Flight Research. A civ with the tech can build one in any world: a leading civ builds
  Heliocentric Model in the Antiquity world, and a lagging civ builds Chart the Stars in the Exploration world. When the
  project is complete, the civ gets a hidden narrative tag, and a civ with the tag cannot build the project again.
  Every check of the world age that a civ "completed" an achievement project reads "done": completed in this world,
  or the tag (`CA_ONCE_DONE_<project>`). The checks are the triumphs of the project's age and the Exploration science
  legacy card `CARD_AT_MO_SCIENTIFIC_4`, which pays economic points in the Modern world for each of Trans-Oceanic
  Flight, Launch Satellite and Crewed Space Flight Research. A project built early counts when the world reaches its
  age. For example, Heliocentric Model built in the Antiquity world and Invent Calculus built in the Exploration world
  earn the Exploration science triumph. The tag is an ordinary game mechanism (the base game's narrative chains read
  tags across ages), and no screen shows it.

Effect on play: a leading civ can collect an achievement's rewards early (victory points, the attribute point, naval
movement), and its triumph and card points count when the world reaches that age. No Modern triumph reads a tag. The
Modern science points of Trans-Oceanic Flight, Launch Satellite and Crewed Space Flight Research are kept from an
earlier world (the game keeps that score across ages: `StaticCarryover`; not tested in a game). The build finds the
checks in the game data, not by file name. It stops if an effect would unlock a gated project, or if a check cannot be
rewritten (a game patch). A check that only a DLC defines is not copied, because the mod's data also loads without
that DLC: today one Babylon narrative story about Chart the Stars, which keeps "completed in this world". The Race
triumph set, a setup option, is an open check (see [Known limits](known-limits.md#open-checks)).

**Religious units follow religion (rule 2m).** Religions are founded and spread, with their beliefs, only in the
Exploration world. The base game's Modern world has no beliefs and no religion screen; religion lives on there only in
the founder's legacy cards, which pay for each city that follows the religion. The religious units (the Missionary, and
the unique Kahuna, Pedanda and Hoceepkileni) are therefore trained, bought and kept only in the Exploration world: in the
Antiquity and Modern worlds a city cannot train or buy them, and the game removes them at the load into the Modern
world, as in the base game. Up to version 0.4.0 they were content of every world: a leading civ could train missionaries
in the Antiquity world before any religion could exist, and in the Modern world a missionary's conversions earned nothing
but changed the cities that the legacy cards count (a player report). The generator finds the units in the game data
(`religious_units` in `build_mod.py`).

Two Exploration rules are not world systems, because they follow from ocean travel, which a civ gets at
its own Breakthrough: deep-ocean damage and meeting the civs of the Distant Lands (see
[Ocean travel](#ocean-travel)).

## The civ age banner

A small banner at the top of the screen shows "Your age: X · World age: Y". It is the only new
interface element.
