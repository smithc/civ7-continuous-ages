# Releasing

How to make a release of the mod: a zip on GitHub and an item on the Steam Workshop.

## Contents

- [Why each release names a game version](#why-each-release-names-a-game-version)
- [Release steps](#release-steps)
- [Steam Workshop](#steam-workshop)
- [Compatibility table](#compatibility-table)
- [Versions](#versions)

## Why each release names a game version

The mod is generated from the installed game files. Two parts depend on the exact game version:

- the copied content of the other ages and the rules that refer to it;
- the mod's transition script, which is a copy of the game's transition script with the reset steps
  removed.

A game patch can change either one. A release therefore says which game version it was built from
and tested with. After a game patch, build the mod again, run the tests, and make a new release (or
add the new game version to the table when the build has not changed).

The build also includes the DLC installed on the build machine. Players without some of that DLC
should still be able to load the mod (the rules that name DLC items change nothing when the DLC is
absent), but this has not been tested. Test it on a game without DLC before the first public release.

## Release steps

1. Update the game, and commit all changes.
2. Run the release tests (see [Development](development.md#automated-tests)):
   - the three-age test (`ContinuousAgesTransition.json`);
   - the stress test (`ContinuousAgesTransitionSeed777.json`);
   - one game played by hand through one age transition.
3. Set `MOD_VERSION` in `generator/build_mod.py` (see [Versions](#versions)) and commit.
4. Build the release:

   ```
   cd generator
   python build_mod.py --package
   ```

   This builds the mod without the test scripts, validates the three world ages, writes
   `build-info.json` into the mod (mod version, game version, Steam build, DLC list, git commit) and
   writes `build/dist/continuous-ages-<mod version>-civ7-<game version>.zip`. It refuses test
   settings (`--checks`, `--fast-test`, `--age-points`) and a build with validation issues.
   If `build-info.json` says `"git_dirty": true`, commit first and build again.
5. Make a GitHub release: tag `v<mod version>`, attach the zip, and in the notes give the game
   version from `build-info.json` and the main changes.
6. Upload the same mod folder (`build/continuous-ages`, or the zip's `continuous-ages` folder) to the
   Steam Workshop (below).
7. Add a row to the [compatibility table](#compatibility-table).

### Install from the zip (for players)

Unzip the `continuous-ages` folder into the game's Mods folder:
`%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VII\Mods\`. Then enable "Continuous Ages" in
the game's Additional Content (Mods) screen.

## Steam Workshop

Civilization VII has Steam Workshop support since game update 1.2.2 (June 2025): players subscribe
to an item, and Steam installs it at the next game start. Firaxis released a Modding SDK with the
same update.

Upload steps were not confirmed when this page was written. Expected steps, based on Civilization VI
and other Steam games:

1. In Steam, open Library, Tools, and install the Civilization VII development tools (the Modding
   SDK).
2. Use its Workshop upload tool. Give it the mod folder, a title, a description, a preview image and
   the visibility (start with Private or Friends only to test).
3. Subscribe to the item from a second account or after removing the local copy, and check that the
   game loads it.

Update this section with the real steps after the first upload.

Workshop description checklist:

- what the mod does (the first lines of the README);
- the game version it was built for;
- the recommended settings ([Settings](settings.md#summary));
- the known limits ([Known limits](known-limits.md));
- a link to this repository.

## Compatibility table

| Mod version | Game version (Steam build) | DLC at build | Tested | Notes |
| --- | --- | --- | --- | --- |
| 0.1.0 | 1.5.0.44 (25516395) | all (78 folders) | AI three-age tests, all game speeds; short human test | First release candidate |

## Versions

`MOD_VERSION` uses `major.minor.patch`:

- **patch:** a rebuild for a new game version, or a bug fix with no rule change;
- **minor:** a new or changed rule;
- **major:** a change that breaks saved games.

The mod affects saved games (`AffectsSavedGames`). Tell players when a release cannot continue a
game started with an earlier release.
