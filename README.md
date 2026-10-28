# Continuous Ages (Civilization VII mod)

One continuous game. Each civilization has its own age, set by two Breakthrough techs in one joined
tech tree. The world still goes through the base game's age transitions, but nothing resets: units,
techs, civics, cities, buildings, policies and gold are kept, so a strong civilization can keep its
lead and snowball.

> **Status: playable, in testing.** Full AI games pass through all three ages at all four game speeds
> in the automated tests. Human play through an age transition has had little testing so far. See
> [Known limits](docs/known-limits.md).

## Contents

- [What changes, in short](#what-changes-in-short)
- [Documentation](#documentation)
- [Install](#install)
- [Recommended settings](#recommended-settings)
- [Compatibility](#compatibility)
- [Development](#development)
- [License](#license)

## What changes, in short

- **Your own age.** Research the Exploration Breakthrough and the Modern Breakthrough to enter the
  next age, at your own pace. The world age still changes at the normal time.
- **No reset at an age transition.** Cities stay cities, armies keep all their units, gold is
  not capped, old resources stay, and earned policies stay.
- **Content waits for your age.** Later-age techs, civics, units, buildings, unique items and civ
  abilities need that age's Breakthrough, even after the world has moved on.
- **World systems stay with the world age.** Crises, legacy paths, treasure fleets, the Distant Lands
  and victories start at the world transition, as in the base game.
- **Units upgrade across ages.** For example Phalanx to Swordsman, and Pikeman to Line Infantry.
- **A small banner** shows "Your age · World age".

## Documentation

| Page | Read it for |
| --- | --- |
| [Vision and design goals](docs/vision.md) | Why the mod exists, its goals, and the core concepts (civ age, world age, Breakthroughs, content and systems) |
| [Mechanics](docs/mechanics.md) | Each game mechanic the mod changes: research, the transition, units, buildings, policies, legacy cards, ocean travel, world systems |
| [Civs and ages](docs/civs-and-ages.md) | The civ choice at a transition (the "half swap", Test of Time), unique content and civ abilities, and what each world age is like for civs ahead or behind |
| [Settings](docs/settings.md) | How game setup options affect the mod: Age Transition Impact (Continuity or Regroup), AI civ selection, game speed, maps |
| [Known limits](docs/known-limits.md) | Engine limits, what is not tested, open checks |
| [Development](docs/development.md) | How the mod is generated, how to build it, and the automated tests |
| [Releasing](docs/releasing.md) | How to make a release (zip and Steam Workshop), and which game versions each release supports |

## Install

### From a release zip

1. Download the zip of the latest release. Check that its game version matches your game (see the
   [compatibility table](docs/releasing.md#compatibility-table)).
2. Unzip the `continuous-ages` folder into
   `%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VII\Mods\`.
3. Start the game and enable **Continuous Ages** in the Additional Content (Mods) screen.
4. Start a new game in Antiquity.

### Build from your own game files

The generator builds the mod from your installed game, so it always matches your game version and
DLC.

1. Install Python 3.10 or later.
2. Build and install the mod:

   ```
   cd generator
   python build_mod.py --install
   ```

   If the game is not in the default Steam folder, add `--game-dir "<your game folder>"`.
3. Start the game and enable **Continuous Ages** in the Additional Content (Mods) screen.
4. Start a new game in Antiquity.

Build the mod again after each game patch or DLC (see
[Development](docs/development.md#after-a-game-patch-or-dlc)).

## Recommended settings

- **Age Transition Impact:** Continuity.
- **AI Civ selection, Age Transition:** Mirroring (default), or Current Civilization Persistence if
  you do not want AI civs to take a new civ before their Breakthrough.
- **Start age:** Antiquity.
- **Catch-up Research** (the mod's own option): Off for full snowballing, or +50% / +100% to make
  techs and civics of earlier ages faster to research after each world transition.

See [Settings](docs/settings.md) for details.

## Compatibility

- Tested with the base game and DLC civs, on Continents and Earth maps, in single player.
- The mod replaces the game's age transition script. Other mods that change that script will
  conflict.
- Multiplayer is not tested.

## Development

The mod is built by a generator and checked by automated AI games. See
[Development](docs/development.md) and [Releasing](docs/releasing.md).

## License

The code in this repository is under the [MIT License](LICENSE).

This is a fan-made mod. It is not made, endorsed or supported by Firaxis Games or 2K. Sid Meier's
Civilization VII is a trademark of Take-Two Interactive Software, Inc. The repository contains no
game files. The release zips contain data generated from the game's files, for use with the game.
