# Known limits and open items

These limits come from the game engine. Each one is named in the test reports. None of them is a
reset of a civ's progress except where noted.

## Contents

- [Engine limits](#engine-limits)
- [Not tested](#not-tested)
- [Open checks](#open-checks)
- [Ideas not built](#ideas-not-built)

## Engine limits

| Name | What happens | Effect |
| --- | --- | --- |
| **Half swap** | A civ behind its Breakthrough can take a new civ at a world transition (the game's choice). It gets the new name, and the game converts some kept units to the new civ's unique versions. The new civ's content and abilities wait for the civ's Breakthrough. | Mostly cosmetic. Avoid it by keeping your civ, or with the AI option Persistence ([Settings](settings.md)). |
| **U-CIVTREE** (lost own civics) | A civ that keeps its civ can lose 2 to 4 completed civics of its own Antiquity civ tree at the load (for example Egypt, Greece, Han; not Persia or Rome). They become researchable again. No cause was found, and the game has no call to grant them back. | A small reset: 150 to 250 culture per civic to research them again. |
| **U-UNIQUE-COMMANDER** | The game sometimes removes the previous civ's unique commander instead of converting it, with its promotions. | One commander lost in some transitions. |
| **Commander conversion** | The game converts kept commanders to the new civ's unique commander (for example Army Commander to Soltan). A script cannot change a unit's type. | Cosmetic for a civ behind its gate. |
| **U-POLICY-LOAD** | At the Modern load the game gives every civ the Exploration main-tree policies, earned or not; Levies and Divine Right then replace Conscription and Oratory. | Policies change, not lost. |
| **U-GREAT-PERSON**, **U-CRISIS-UNIT** | Egypt's Tjaty great people are removed at each load. Plague Physicians end with their crisis. | As in the base game. |
| **U-LEVY** | Independent powers research the joined tree at their own pace and can field later-age units, which a major civ can get by a levy before its own Breakthrough. | Rare (seen once, in a test with cheap techs). |

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

## Ideas not built

- **Cheap re-research for U-CIVTREE.** One modifier per Antiquity civ tree, with a large research
  speed-up (`EFFECT_PLAYER_ADJUST_PROGRESSION_TREE_EFFICIENCY`) for civs past the Exploration
  Breakthrough. Lost civics would come back in about a turn. Limit: the game keeps no record of which
  civics were lost, so a civ past its Breakthrough would get all its old civ-tree civics cheaply.
  The Catch-up Research option (off by default) covers this in part: with it on, lost civics of an
  earlier age cost half or two thirds of the turns.
