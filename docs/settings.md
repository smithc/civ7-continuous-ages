# Game settings and the mod

This page lists the game setup options that change how the mod plays, and what was tested.

## Contents

- [Age Transition Impact (Continuity or Regroup)](#age-transition-impact-continuity-or-regroup)
- [AI Civ selection, Age Transition](#ai-civ-selection-age-transition)
- [Game speed](#game-speed)
- [Map type and size](#map-type-and-size)
- [Start age and civ selection at game start](#start-age-and-civ-selection-at-game-start)
- [Other settings](#other-settings)
- [Summary](#summary)

## Age Transition Impact (Continuity or Regroup)

The base game's option **Age Transition Impact** has two values:

- **Continuity** (default): "Retain most of your empire, units, and Alliances with other Leaders at
  Age Transition."
- **Regroup**: "Reset your empire, units, and relationships more aggressively on Age Transition."

With the mod, the unit steps of the transition are the same for both values: every unit is kept, and
the steps that Regroup adds for units (commanders moved to cities, free defenders) are not used. The
mod's other no-reset steps (no city becomes a town, no gold or influence cap, old resources stay)
also apply to both. Both values passed the full three-age test.

What Regroup still changes is engine behaviour outside the transition script, for example how
relationships between leaders reset. The mod does not change that, and it was not measured. Use
**Continuity** for the intended experience.

## AI Civ selection, Age Transition

This Advanced Setup option sets how AI civs choose their civ at a world transition. It is the only
control over the AI's choice; the game has no setting for each civ, and it cannot change during a game.

| Value | AI behaviour | Effect with the mod |
| --- | --- | --- |
| **Mirroring** (default) | AI civs copy the human player's choice (switch or keep) | Some AI civs behind their Breakthrough take a new civ (the [half swap](civs-and-ages.md#the-half-swap)); their new civ's content and abilities wait for their Breakthrough |
| **Current Civilization Persistence** | Every AI civ keeps its civ | No half swap for AI civs. Cost: no AI civ ever takes a new civ, even one far ahead; more civs hit the lost-civics limit ([Known limits](known-limits.md)) |
| **Apex Civilization Transition** | Every AI civ takes a new civ | Every AI civ behind its Breakthrough gets a half swap. Not tested |
| **Random** | Each AI civ 50/50 | Mixed. Not tested |

The mod keeps the game's default (Mirroring). Persistence passed the full three-age test.

## Game speed

All four speeds passed the full three-age test: Quick (ages end around turn 93), Standard (140),
Epic (210) and Marathon (420). The Breakthrough costs scale with game speed like other techs.

## Map type and size

Tested: Continents on a standard map (two seeds), a Huge map with 13 civs, and the Earth map (Huge, 10
civs). On the Earth map the mod uses the generic resource step at a transition, because the Earth
map's own step removed rural districts. Other map scripts were not tested.

## Start age and civ selection at game start

- The tests start in Antiquity. A game that starts in Exploration or Modern was not tested.
- **Civ selection at game start** (Time-Tested or Apex only) works as in the base game. A civ of a
  later age at the start does not get its unique content in Antiquity, as in the base game.

## Other settings

- **Difficulty, legacy paths, victories, crises, disasters:** unchanged by the mod, not tested
  separately.
- **Single age game:** not tested; the mod is meant for full games.
- **Multiplayer:** not tested.

## Summary

| Setting | Recommended | Tested |
| --- | --- | --- |
| Age Transition Impact | Continuity | Continuity and Regroup |
| AI Civ selection, Age Transition | Mirroring (default) or Persistence | Mirroring, Persistence |
| Game speed | Any | Quick, Standard, Epic, Marathon |
| Map | Any; Continents and Earth tested | Continents (standard, huge), Earth (huge) |
| Start age | Antiquity | Antiquity |
| Players | Single player | Single player (AI autoplay); human play only briefly |
