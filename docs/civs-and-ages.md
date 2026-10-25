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
| **Ahead of the world** | A civ researches the Exploration Breakthrough while the world is in Antiquity | Exploration techs, civics, units and buildings, ocean travel; not the Exploration world systems (treasure fleets, Distant Lands legacy paths) until the world gets there |
| **Same as the world** | The normal case | Everything of its age |
| **Behind the world** | The world enters Exploration, but the civ has not researched the Exploration Breakthrough | Its Antiquity content and everything it built; no Exploration content until its Breakthrough; the Exploration world systems run around it |

A civ behind the world can catch up at any time by researching the Breakthrough.

## The civ choice at a world transition

At a world transition, every civ can take a new civilization of the new age, or keep its current civ
(the base game's Test of Time option). The mod does not change this choice: the game makes it. There
is no way in the game's data or scripts to change a civ during an age, so a civ changes only at a
world transition, as in the base game.

### The half swap

A civ that is **behind** its Breakthrough can still take a new civ of the new age at the world
transition. The mod then locks the new civ's content until the civ's own Breakthrough:

- its unique civic tree, unique units, buildings and improvements;
- its civ abilities (the modifiers of its civ traits);
- legacy cards that would grant a node of the new age.

What the civ gets at once is the new civ's **name**, and the game converts some kept units to the new
civ's unique versions (for example Army Commander to Soltan). This is called the "half swap".

### Keeping your civ (Test of Time)

A civ can keep its civ at a world transition. It then gets the new age's Test of Time civic tree
(locked until its Breakthrough, like every later-age civic tree). This is the best choice for a civ
that is behind its Breakthrough: it avoids the half swap.

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

- **Unique civic trees** of Exploration and Modern civs need that age's Breakthrough (their first
  civics).
- **Test of Time trees** and **branch trees** of a later age need that age's Breakthrough.
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
- A civ that researches the Exploration Breakthrough gets Exploration techs, civics, units and
  buildings, and ocean travel. The deep-ocean rule (ends the turn until Shipbuilding) applies.
- Exploration world systems (treasure fleets, the Distant Lands, Exploration legacy paths) do not
  start. Antiquity legacy paths and crises run as in the base game.
- A civ can even research the Modern Breakthrough in the Antiquity world, if it gets that far.

### Exploration world

- Nothing resets at the transition (see [Mechanics](mechanics.md#the-world-transition-no-reset)).
- Civs behind their Exploration Breakthrough keep Antiquity content and research toward it. Deep
  ocean is open to every civ from the Exploration world on, as in the base game.
- Civs ahead of the world can research the Modern Breakthrough and get Modern techs, civics, units
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
units, cities and research stay. Abbasid's civic tree, unique units and abilities stay locked until
the civ researches the Exploration Breakthrough.

**Keeping the civ.** Egypt keeps its civ at the transition. It gets the Exploration Test of Time tree,
locked until its Breakthrough. Some of its completed Egyptian civics may need to be researched again
(known limit).
