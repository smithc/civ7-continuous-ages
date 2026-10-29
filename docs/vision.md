# Vision and design goals

Continuous Ages turns a Civilization VII game into one continuous game. Each civilization has its own
age. The world still goes through the base game's age transitions, but nothing resets.

## Contents

- [The idea](#the-idea)
- [Design goals](#design-goals)
- [Core concepts](#core-concepts)
- [What the mod does not change](#what-the-mod-does-not-change)
- [Effect on play](#effect-on-play)

## The idea

In the base game, every civilization moves to the next age at the same time, at a world-wide age
transition. At that moment many things reset: cities become towns, gold is capped, armies are
remade, and old resources leave the map. A leading civilization loses much of its lead. The next age
starts on a more equal footing.

Continuous Ages keeps the lead. A civilization enters the next age when it researches that age's
**Breakthrough** tech, at its own pace. The civic tree has its own Breakthroughs, researched with
culture, so science and culture each move a civ forward in their own tree. A strong civilization can
be in the Exploration Age while its neighbours are still in Antiquity. When the world transition
comes, nothing resets: units, techs, civics, cities, buildings, gold and policies all carry over.

## Design goals

1. **Full continuity.** No reset at an age transition. What a civ has built stays.
2. **Each civ has its own age.** A civ's age is set by its own research, not by the world.
3. **Snowballing is allowed.** A civ that plays well can stay ahead and grow its lead.
4. **The base game's age transitions stay.** The world still moves through Antiquity, Exploration and
   Modern. Each world age still starts its own systems: crises, legacy paths, treasure fleets, the
   Distant Lands, and the final victories.
5. **No content before its time.** A civ cannot build, research or use content of an age it has not
   entered, even after the world has moved on. Each tree has its own gate: tech content needs the
   tech Breakthrough, and civic content needs the civic Breakthrough.
6. **Both yields matter.** As in the base game, science and culture are equal. Neither one alone
   decides a civ's progress, and neither one is wasted while the other catches up.
7. **Robust to game patches.** The mod is generated from the installed game files. Content from new
   patches or DLC is picked up when the mod is built again, and a mechanic the generator does not
   know is left out instead of running in the wrong age.

## Core concepts

| Concept | Meaning |
| --- | --- |
| **World age** | The base game's age: Antiquity, Exploration or Modern. It changes at a world transition, as in the base game. |
| **Civ age** | Each civ's own age. It starts in Antiquity and moves forward when the civ researches a Breakthrough tech. It controls the civ's tech content, units, civ abilities and unique items. |
| **Breakthrough** | Two new techs in the joined tech tree (the Exploration Breakthrough and the Modern Breakthrough), and two new civics of the same names in the joined civic tree. A tech Breakthrough is the gate to the next age's techs and content; a civic Breakthrough is the gate to the next age's civics and what they unlock. |
| **Joined trees** | The techs of all three ages form one tech tree, and the main civics form one civic tree. Research is never reset, because the tree is the same in every world age. |
| **Content** | What a civ researches, builds or uses: techs, civics, units, buildings, improvements, governments, traditions, great people, civ abilities and unique items. Content from all ages is loaded in every world age and locked per civ by its Breakthroughs. |
| **Systems** | Mechanics that the world sets up: crises, legacy paths and triumphs, treasure fleets, the Distant Lands, independent powers, discoveries, victories. Systems stay with their world age. |

The split between content and systems is the core rule of the mod. Content follows the civ. Systems
follow the world. Systems need setup that the game does only at a world transition (for example the
Distant Lands for treasure fleets), so they cannot start early for one civ.

## What the mod does not change

- The world age, its age progress meter and the timing of world transitions.
- Crises, legacy paths, triumphs, golden and dark ages, and legacy cards (except the cards that would
  give a civ a node of an age it has not entered, see [Mechanics](mechanics.md#legacy-cards)).
- The civ choice at a world transition. The game still decides it (see
  [Civs and ages](civs-and-ages.md#the-civ-choice-at-a-world-transition)).
- Combat, yields, costs and the AI. The tech and civic costs are the base game's costs.

## Effect on play

- A leading civ gets its next age's techs, units, buildings and civ content as soon as it researches
  the Breakthrough, while the rest of the world is still in the earlier age.
- A civ with strong culture can lead in civics (policies, civic wonders and buildings) while its techs
  lag, and the opposite.
- A lagging civ keeps its own-age content and everything it has built. It can stay behind the world
  age for a long time. In tests, lagging civs stayed behind for 55 to 85 of the 140 turns of an age.
- Wars, buildings and armies carry from one age to the next, so long-term plans pay off.
- The world transition is still an event: new systems start, new resources appear, and civs can take
  a new civilization.

See [Mechanics](mechanics.md) for each rule in detail.
