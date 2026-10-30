# Releasing

How to make a release of the mod: a zip on GitHub and an item on the Steam Workshop.

## Contents

- [Why each release names a game version](#why-each-release-names-a-game-version)
- [Release steps](#release-steps)
- [Steam Workshop](#steam-workshop)
- [Save compatibility](#save-compatibility)
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
3. Check that saved games of the previous release still load (see
   [Save compatibility](#save-compatibility)).
4. Set `MOD_VERSION` in `generator/build_mod.py` (see [Versions](#versions)) and commit.
5. Build the release:

   ```
   cd generator
   python build_mod.py --package
   ```

   This builds the mod without the test scripts, validates the three world ages, writes
   `build-info.json` into the mod (mod version, game version, Steam build, DLC list, git commit) and
   writes `build/dist/continuous-ages-<mod version>-civ7-<game version>.zip`. It refuses test
   settings (`--checks`, `--fast-test`, `--age-points`) and a build with validation issues.
   If `build-info.json` says `"git_dirty": true`, commit first and build again.
6. Make a GitHub release: tag `v<mod version>`, attach the zip, and in the notes give the game
   version from `build-info.json` and the main changes.
7. Upload the same mod folder (`build/continuous-ages`, or the zip's `continuous-ages` folder) to the
   Steam Workshop (below).
8. Add a row to the [compatibility table](#compatibility-table).

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
2. Use its Workshop upload tool. Give it the mod folder, a title, a description, the preview image
   (`workshop/preview.jpg`) and the visibility (start with Private or Friends only to test).
3. Subscribe to the item from a second account or after removing the local copy, and check that the
   game loads it.

Update this section with the real steps after the first upload.

The uploader takes the first description from the modinfo (plain text, because the game's Mods
screen shows the same text). After the upload, replace the Workshop description with
`workshop/description.bbcode` (Steam formatting). Update its version line for each release.

The preview image is `workshop/preview.jpg`: a square JPEG, 1254 x 1254, 708 KB. Steam needs a preview
image under 1 MB. It is not part of the mod or the release zip.

Workshop description checklist:

- what the mod does (the first lines of the README);
- the game version it was built for;
- the recommended settings ([Settings](settings.md#summary));
- the known limits ([Known limits](known-limits.md));
- a link to this repository.

## Save compatibility

A player can update the mod in the middle of a game. A saved game records the mod's id and name, not
its version, so the game loads it with whatever version is installed. The modinfo's `version`
attribute is always `1`. A save refers to game objects by their type and modifier ids, so a new
version must not remove or rename an id that an earlier version created.

Two checks, before each release:

1. **Database check** (about 2 minutes; build the current version first):

   ```
   cd generator
   python build_mod.py
   python tools/savecompat.py v<previous version>
   ```

   It builds the previous release in a temporary git worktree and compares both databases (base
   game, DLC and mod) for each world age. It fails if a `Types` row or a modifier id was removed.
   Other changes are listed for review. Ids that come from a list position (for example rule 5c's
   `CA_KEEP_TRADITION_<policy>_<n>`) must keep their positions: add new rows after the old ones.
2. **Load test** of real saves of the previous version: play the previous version (its worktree's
   `iterate.py`) and keep some autosaves, at least one per world age and one just before each world
   transition. Copy each one to `CA_COMPAT.Civ7Save` in the `Saves/Single` folder and run:

   ```
   python iterate.py --suite ContinuousAgesFromSaveCompat.json --no-fast-test --turns 20 --observe NONE --timeout 25
   ```

   Each run must pass. Also compare each civ's state at the save with its first state after the
   load (cities, towns, units, policies and traditions equal; techs and civics not lower).

## Compatibility table

| Mod version | Game version (Steam build) | DLC at build | Tested | Notes |
| --- | --- | --- | --- | --- |
| 0.2.1 | 1.5.0.44 (25516395) | all (78 folders) | 0.2.0 tests (game rules unchanged: UI fix only); UI test (`ui_test.py`) with two Antiquity saves; civic tree checked in a human game | Civic tree: no empty columns or stray lines at the age borders; hover highlight past the Breakthrough techs |
| 0.2.0 | 1.5.0.44 (25516395) | all (78 folders) | 0.1.0 tests (rules unchanged with the option off); AI three-age test with Catch-up +100%; Catch-up +50% and +100% to the Exploration transition | Adds the Catch-up Research setup option |
| 0.1.0 | 1.5.0.44 (25516395) | all (78 folders) | AI three-age tests, all game speeds; short human test | First release candidate |

## Versions

`MOD_VERSION` uses `major.minor.patch`:

- **patch:** a rebuild for a new game version, or a bug fix with no rule change;
- **minor:** a new or changed rule;
- **major:** a change that breaks saved games.

The mod affects saved games (`AffectsSavedGames`). Tell players when a release cannot continue a
game started with an earlier release.
