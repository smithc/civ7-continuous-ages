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
| Units | Commanders are kept with their promotions (only commanders have promotions); other military units are remade as the new age's types, and units that the armies do not take back can be lost | Kept as they are: type and position; commanders with their promotions |
| Cities | All cities except the capital become towns | Cities stay cities |
| Gold and influence | Capped | Not capped |
| Buildings and improvements | Kept; the base game's rules for older-age buildings apply | Kept; the same rules apply |
| Old-age resources | Removed from the map | Stay on the map (lagging civs still use them) |
| Policies | The new age's trees replace the old ones | Every policy the civ has earned stays (see below) |
| Traditions | Kept | Kept |
| Civ | The civ takes a new civ (or keeps its civ with Test of Time) | Unchanged: the game still decides (see [Civs and ages](civs-and-ages.md)) |

### Units

- Every unit is kept as it is.
- The game also creates replacement units for some units ("shadows"). The mod uses a shadow only to
  replace a unit that the game removed (for example a unique unit of the civ's previous civ). The
  replacement keeps the removed unit's class, and it is the best unit of that class that the civ
  can build in its own age.

### Cities, gold and influence

No city becomes a town, and gold and influence are not capped.

### Resources

- Resources of an earlier age stay on the map.
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

At a world transition, the government choice lists the governments of the new world age, as in the
base game.

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

- techs of a later age, and units, buildings, improvements, wonders and projects that they unlock;
- civics of a later age, and what they unlock, need the civic Breakthrough of that age (see
  [Civics](#civics));
- "starter" units and buildings that a later age gives at its start;
- civ-specific content (see [Civs and ages](civs-and-ages.md)).

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
- The Exploration civs' free ship comes once per civ, at the later of its Exploration Breakthrough
  and the Exploration world.

## World systems

These systems stay with the world age and start at the world transition, as in the base game:

- crises;
- legacy paths, triumphs, and golden and dark ages;
- treasure fleets and the Distant Lands;
- independent powers and discoveries;
- the final victories (Modern world);
- religion steps and diplomacy actions of each age;
- the age's growth curve and balance values.

A leading civ therefore cannot score the next age's legacy paths before the world reaches that age.

## The civ age banner

A small banner at the top of the screen shows "Your age: X · World age: Y". It is the only new
interface element.
