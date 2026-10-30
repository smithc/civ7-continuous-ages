# Civs and ages

This page explains how civilizations and ages work together in the mod: the civ choice at a world
transition, civ-specific content, and what each world age looks like for civs ahead of it or behind it.

## Contents

- [A civ's age and the world age](#a-civs-age-and-the-world-age)
- [The civ choice at a world transition](#the-civ-choice-at-a-world-transition)
  - [The half swap](#the-half-swap)
  - [Keeping your civ (Test of Time)](#keeping-your-civ-test-of-time)
  - [The AI's choice](#the-ais-choice)
- [Unique content, civ abilities and civic trees](#unique-content-civ-abilities-and-civic-trees)
- [Age by age](#age-by-age)
  - [Antiquity world](#antiquity-world)
  - [Exploration world](#exploration-world)
  - [Modern world](#modern-world)
- [Examples](#examples)

## A civ's age and the world age

Each civ has its own age (see [Vision](vision.md#core-concepts)). The world age and a civ's age can
differ in both directions:

| Case | Example | What the civ has |
| --- | --- | --- |
| **Ahead of the world** | A civ researches the Exploration Breakthrough while the world is in Antiquity | Exploration techs, units and buildings, ocean travel; not the Exploration world systems (treasure fleets, Distant Lands legacy paths) until the world gets there |
| **Same as the world** | The normal case | Everything of its age |
| **Behind the world** | The world enters Exploration, but the civ has not researched the Exploration Breakthrough | Its Antiquity content and everything it built; no Exploration content until its Breakthrough; the Exploration world systems run around it |

A civ behind the world can catch up at any time by researching the Breakthrough.

The civic tree has its own Breakthrough of each age, researched with culture (see
[Mechanics](mechanics.md#civics)). It opens that age's civics, and the content they unlock. So a civ
can also be ahead or behind in civics: a civ with strong culture and weak science can research
Exploration civics while its civ age is still Antiquity, and the opposite. "Civ age" on this page
means the tech Breakthroughs.

## The civ choice at a world transition

At a world transition, every civ can take a new civilization of the new age, or keep its current civ
(the base game's Test of Time option). The mod does not change this choice: the game makes it. There
is no way in the game's data or scripts to change a civ during an age, so a civ changes only at a
world transition, as in the base game.

### The half swap

A civ that is **behind** its Breakthrough can still take a new civ of the new age at the world
transition. The mod then locks the new civ's content until the civ's own Breakthrough:

- its unique civic tree (the tree shows with the Breakthrough);
- its unique units, buildings and improvements that have no unlock in the base game;
- its civ abilities (the modifiers of its civ traits);
- legacy cards that would grant a tech of the new age (a card that grants a civic waits for the
  civic Breakthrough of that age).

What the civ gets at once is the new civ's **name**, and the game converts some kept units to the new
civ's unique versions (for example Army Commander to Soltan). This is called the "half swap".

### Keeping your civ (Test of Time)

A civ can keep its civ at a world transition. It then gets the new age's Test of Time civic tree when
it researches the civic Breakthrough of that age. The tree stays in later worlds while the civ keeps
its civ, with its completed civics. This is the best choice for a civ that is behind its
Breakthrough: it avoids the half swap.

The Test of Time civic **Syncretism** lets the civ adopt a "legacy" civ of the new age, with its
traits (for example Rome takes the Norman traits), as in the base game. It can then build that
civ's unique units, buildings and improvements. A legacy civ is civ content, so the mod gives it
only when the civ also has the Breakthrough tech of that age. Syncretism works only in its own world
age: the old Test of Time tree stays in later worlds, but its Syncretism does not give a second
legacy civ there. So a civ gets at most one legacy civ per age, as in the base game. Up to version
0.2.1 the Test of Time tree was locked, so no civ got a legacy civ.
Known limit: at the next load the mod can give the civ extra units for its legacy unique units
(U-TOT-SHADOW, see [Known limits](known-limits.md)).

When you play, the civ choice screen lists your current civ as a valid choice.

Known limit: a civ that keeps its civ can lose some completed civics of its own civ tree at the load
(2 to 4 civics, for some civs). It must research them again. See [Known limits](known-limits.md).

### The AI's choice

The AI chooses by the game option **AI Civ selection, Age Transition** (Advanced Setup). See
[Settings](settings.md#ai-civ-selection-age-transition). The option applies to all AI civs; the game
has no choice for each civ. Tests showed that the AI ignores locks: locking every other civ made the
AI take a locked civ or a civ of another age, so the mod does not try this.

## Unique content, civ abilities and civic trees

A civ's unique content belongs to the civ's age:

- **Unique civic trees** of a later age show when the civ researches that age's Breakthrough tech
  (the game's reveal modifier of the civ's trait, gated like the civ abilities below). A civ gets a
  unique tree only with its civ, at a world transition.
- **Test of Time trees** of a later age show when the civ researches that age's civic Breakthrough,
  and they stay in later worlds while the civ keeps its civ.
- **Branch trees** keep their base-game conditions: the Theology tree needs a holy city, and the
  ideology trees need Political Theory (a Modern civic). Unlike the base game, the Theology tree
  stays after the Exploration world, so its civics and policies (for example Evangelism) are kept.
- Before version 0.2.2 the first civics of all these trees needed the Breakthrough tech, and the
  game never opened them: no civ could research them, not even an ideology.
- **Unique units, buildings and improvements** that have no unlock in the base game get the
  Breakthrough as their unlock.
- **Civ abilities**: each modifier of a trait that only one Exploration or Modern civ has (178
  modifiers) also needs that age's Breakthrough. Shared traits (attributes, the anachronistic trait)
  are not changed.
- In the Modern world, units and buildings of Exploration civ trees also need the Exploration
  Breakthrough (the game does not enforce unlocks of an older tree on its own).

A civ that starts the game as a civ of a later age (Test of Time at game setup) does not get that
civ's unique content in Antiquity. This matches the base game.

## Age by age

### Antiquity world

- Every civ starts in Antiquity.
- A civ that researches the Exploration Breakthrough gets Exploration techs, units and buildings,
  and ocean travel. The deep-ocean rule (ends the turn until Shipbuilding) applies. A civ that
  researches the Exploration civic Breakthrough gets the Exploration civics.
- Exploration world systems (treasure fleets, the Distant Lands, Exploration legacy paths) do not
  start. Antiquity legacy paths and crises run as in the base game.
- A civ can even research the Modern Breakthrough in the Antiquity world, if it gets that far.

### Exploration world

- Nothing resets at the transition (see [Mechanics](mechanics.md#the-world-transition-no-reset)).
- Civs behind their Exploration Breakthrough keep Antiquity content and research toward it. Deep
  ocean is open to every civ from the Exploration world on, as in the base game.
- Civs ahead of the world can research the Modern Breakthroughs and get Modern techs, civics, units
  and buildings. Modern world systems wait for the Modern world.
- The free ship of Exploration civs comes once per civ, at the later of its Exploration Breakthrough
  and the Exploration world.

### Modern world

- Nothing resets at the transition.
- Civs behind their Modern Breakthrough (or even behind the Exploration Breakthrough) keep their own
  age's content.
- The final victories run as in the base game.

## Examples

**A fast civ.** Rome researches the Exploration Breakthrough at turn 90 of Antiquity. It builds
Exploration units and buildings at once, and its ships can cross deep ocean. At the world transition
it keeps everything and continues.

**A slow civ.** Persia has not researched the Exploration Breakthrough when the world enters
Exploration. With the default AI setting, the AI may take a new civ, for example Abbasid. Persia's
units, cities and research stay. Abbasid's unique units and abilities stay locked until the civ
researches the Exploration Breakthrough. Abbasid's civic tree shows at that time too.

**A cultural civ.** Greece has strong culture but weak science. It finishes the Antiquity civics,
then researches the Exploration civic Breakthrough and the Exploration civics, while its techs are
still in Antiquity. Its Exploration techs, units and ocean travel wait for the Exploration
Breakthrough tech.

**Keeping the civ.** Egypt keeps its civ at the transition. It gets the Exploration Test of Time
tree when it researches the Exploration civic Breakthrough, and keeps that tree in the Modern world.
Some of its completed Antiquity Egyptian civics may need to be researched again (known limit).
