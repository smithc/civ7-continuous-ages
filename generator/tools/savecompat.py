"""Save compatibility check: compare the game database of an earlier release with the current build.

A saved game refers to game objects by their type and modifier ids. If a new version removes or
renames one that an old save uses, the save can fail to load or lose state without an error (in
0.3.0 a renumbering renamed 42 game modifiers of rule 5c; this check found it). For each world age it
loads the base game, the DLC and each mod build into the offline database, and compares every table.

Usage (in generator/, after `python build_mod.py` for the current build):
    python tools/savecompat.py v0.2.1          # builds that git ref in a temporary worktree
    python tools/savecompat.py --old <mod dir> # or compare with a mod folder already built
Exit code 0: nothing that a save can refer to was removed (Types, Modifiers). 1: something was.
Other changed rows are listed for review: they change what opens or applies, not what a save names.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import civ7data as c  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent
AGES = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
# Ids a saved game stores: a row removed from these tables can break an old save.
SAVED_IDS = {"Types": 0, "Modifiers": 0}


def tables(mod_dir: Path, age: str) -> dict:
    mods = c.load_base_modules(include_dlc=True) + [c.parse_modinfo(mod_dir / "continuous-ages.modinfo")]
    sim = c.Simulator()
    for path in c.database_items(c.applicable_groups(mods, age)):
        sim.apply_file(path)
    names = [r[0] for r in sim.db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {t: set(sim.db.execute(f'SELECT * FROM "{t}"').fetchall()) for t in names}


def build_ref(ref: str, where: Path) -> Path:
    subprocess.run(["git", "-C", str(REPO), "worktree", "add", "-q", "--detach", str(where), ref], check=True)
    subprocess.run([sys.executable, "build_mod.py"], cwd=where / "generator", check=True, stdout=subprocess.DEVNULL)
    return where / "build" / "continuous-ages"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref", nargs="?", help="git ref of the earlier release (for example v0.2.1)")
    ap.add_argument("--old", type=Path, help="an earlier mod folder instead of a git ref")
    ap.add_argument("--new", type=Path, default=REPO / "build" / "continuous-ages")
    args = ap.parse_args()
    tmp = None
    if args.old is None:
        if not args.ref:
            ap.error("give a git ref or --old")
        tmp = Path(tempfile.mkdtemp(prefix="savecompat-"))
        args.old = build_ref(args.ref, tmp / "old")
    broken = []
    try:
        for age in AGES:
            old, new = tables(args.old, age), tables(args.new, age)
            print(f"== {age}")
            for t in sorted(set(old) | set(new)):
                a, b = old.get(t, set()), new.get(t, set())
                if a == b:
                    continue
                removed, added = a - b, b - a
                if t in SAVED_IDS:
                    key = SAVED_IDS[t]
                    gone = sorted({r[key] for r in removed} - {r[key] for r in b})
                    if gone:
                        broken += [(age, t, x) for x in gone]
                        print(f"  BREAKS SAVES: {t} removed {gone[:10]}{' ...' if len(gone) > 10 else ''}")
                print(f"  {t}: -{len(removed)} +{len(added)}")
    finally:
        if tmp is not None:
            subprocess.run(["git", "-C", str(REPO), "worktree", "remove", "--force", str(tmp / "old")], check=False)
            shutil.rmtree(tmp, ignore_errors=True)
    print("RESULT:", "compatible (no saved id removed)" if not broken else f"{len(broken)} saved ids removed")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
