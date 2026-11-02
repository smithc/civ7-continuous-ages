"""One test iteration: build, validate, install, autoplay, analyze.

  1. Build the test mod with the in-game checks (build_mod.py --install --checks).
     Stop if the simulator finds load issues, broken references or unclassified tables.
  2. Run an AI-only autoplay game (run_autoplay.ps1). The game must be closed first.
  3. Analyze: automation result, crash dumps (tools/crashstack.py), database and mod
     errors, the [CA-CHECK] lines of checks/ca-checks.js, and the CSV logs.
  4. Write build/iterations/<time>/REPORT.md and keep a copy of the logs.

Usage: python iterate.py [--turns 60] [--fast-test 0.1 | --no-fast-test] [--timeout 75] [--worker N]
Exit code: 0 = pass, 1 = fail, 2 = could not run.

--worker N runs the game as worker N (gamepool.py): its own user folders, Mods, Logs and Saves, a build in
build/workers/w<N>/build, and the run folder build/iterations/<time>-w<N>. Several workers can run at once.
Without --worker, the run uses the real user folders and starts the game through Steam (one game at a time).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import hashlib
import shutil
from collections import Counter as _C
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import civ7data as c
import gamepool

# --worker N: this process and its child processes (build, runner, game) use worker N's user folders. It must run
# before the paths below, which follow Path.home() (USERPROFILE).
WORKER = gamepool.activate_from_argv()
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MOD_DIR = (gamepool.worker_dir(WORKER) / "build" if WORKER else REPO / "build") / "continuous-ages"
USER_DATA = Path.home() / "AppData" / "Local" / "Firaxis Games" / "Sid Meier's Civilization VII"
LOGS = USER_DATA / "Logs"
DUMP_DIRS = [USER_DATA / "packagedDumps", USER_DATA / "dumps", Path.home() / "AppData" / "Local" / "CrashDumps"]
# Windows Error Reporting writes every game's dumps to the real user's CrashDumps folder. A worker run reads there
# only its own game's dumps: the process id (runner line "Game process: <pid>") is in the file name.
REAL_CRASHDUMPS = gamepool.REAL_LOCALAPPDATA / "CrashDumps"
TEST_SAVES = ("CA_*.Civ7Save",)  # the named test saves (from-save suites, save compatibility), copied into a worker
TOOLS_PY = HERE / ".venv" / "Scripts" / "python.exe"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def game_running() -> bool:
    """A worker run: its own worker's game. A run without a worker: any game (also a worker's: Steam starts no
    second game, and the runner follows the first game process it finds)."""
    if WORKER:
        return bool(gamepool.game_pids(WORKER))
    out = run(["tasklist", "/FI", "IMAGENAME eq Civ7_Win64_DX12_FinalRelease.exe", "/NH"]).stdout
    return "Civ7_Win64" in out


def build(fast: float | None, age_points: int | None = None, extra: list | None = None) -> tuple[bool, str]:
    cmd = [sys.executable, str(HERE / "build_mod.py"), "--install", "--checks"] + (extra or [])
    if WORKER:
        cmd += ["--out", str(MOD_DIR.parent)]
    if age_points:
        cmd += ["--age-points", str(age_points)]
    if fast is not None:
        cmd += ["--fast-test", str(fast)]
    res = run(cmd, cwd=HERE)
    out = res.stdout + res.stderr
    # One validation line per world age; all must be clean.
    checks = re.findall(r"validation: (\d+) load issues, (\d+) new foreign-key violations", out)
    unclassified = re.findall(r"unclassified tables: (.*)", out)
    ok = (res.returncode == 0 and len(checks) == 3 and all(m == ("0", "0") for m in checks)
          and len(unclassified) == 3 and all(u.strip() == "none" for u in unclassified))
    return bool(ok), out


def exploration_items() -> tuple[set, set]:
    """Exploration units and buildings, from a simulation of the built mod."""
    mods = c.load_base_modules(include_dlc=True) + [c.parse_modinfo(MOD_DIR / "continuous-ages.modinfo")]
    sim = c.Simulator()
    for path in c.database_items(c.applicable_groups(mods, "AGE_ANTIQUITY")):
        sim.apply_file(path)
    units = {r[0] for r in sim.db.execute(
        "SELECT TargetType FROM ProgressionTreeNodeUnlocks WHERE TargetKind='KIND_UNIT' "
        "AND ProgressionTreeNodeType LIKE 'NODE_TECH_EX_%'")}
    # By the unlocking node: the generator sets Age to the world age, so Age cannot tell.
    buildings = {r[0] for r in sim.db.execute(
        "SELECT TargetType FROM ProgressionTreeNodeUnlocks WHERE TargetKind='KIND_CONSTRUCTIBLE' "
        "AND (ProgressionTreeNodeType LIKE 'NODE_TECH_EX_%' OR ProgressionTreeNodeType LIKE 'NODE_CIVIC_EX_%')")}
    return units, buildings


def civic_trees() -> dict:
    """Short civic node name -> short tree name, as the checks write them."""
    mods = c.load_base_modules(include_dlc=True) + [c.parse_modinfo(MOD_DIR / "continuous-ages.modinfo")]
    sim = c.Simulator()
    for path in c.database_items(c.applicable_groups(mods, "AGE_MODERN")):
        sim.apply_file(path)
    return {n.replace("NODE_CIVIC_", ""): t.replace("TREE_CIVICS_", "") for n, t in sim.db.execute(
        "SELECT ProgressionTreeNodeType, ProgressionTree FROM ProgressionTreeNodes")}


def native_ages() -> dict:
    """Unit or constructible type -> its native age, from the base game without the mod
    ("common" when the base game loads it in more than one age)."""
    seen = {}
    for age in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"):
        sim = c.simulate(c.DEFAULT_GAME_DIR, age, include_dlc=True)
        for (t,) in sim.db.execute("SELECT UnitType FROM Units UNION SELECT ConstructibleType FROM Constructibles"):
            seen.setdefault(t, []).append(age)
    return {t: a[0] if len(a) == 1 else "common" for t, a in seen.items()}


AGE_RANK = {"AQ": 0, "EX": 1, "MO": 2}


def too_early(req, civ_age: str | None, civic_age: str | None = None) -> bool:
    """True when a civ has reached none of an item's unlock tracks (required_ages() value). Two gates:
    the tech track needs the civ age (tech Breakthrough), the civic track (main-tree civics) the civic
    age (civic Breakthrough). Records without a civic age (older runs) use the civ age for both."""
    if req is None or civ_age not in AGE_RANK:
        return False
    tech, civic = (req, None) if isinstance(req, int) else req
    civic_rank = AGE_RANK.get(civic_age if civic_age in AGE_RANK else civ_age)
    return not ((tech is not None and tech <= AGE_RANK[civ_age]) or (civic is not None and civic <= civic_rank))


_WORLD_UNITS = {}


def world_unit_types(world: str) -> set:
    """Unit types in the built mod's data for this world (U-DLC-EARLIER: a DLC civ's earlier-age units are not
    copied into the later worlds)."""
    if world not in _WORLD_UNITS:
        mods = c.load_base_modules(include_dlc=True) + [c.parse_modinfo(MOD_DIR / "continuous-ages.modinfo")]
        sim = c.Simulator()
        for path in c.database_items(c.applicable_groups(mods, world)):
            sim.apply_file(path)
        _WORLD_UNITS[world] = {u for (u,) in sim.db.execute("SELECT UnitType FROM Units")}
    return _WORLD_UNITS[world]


def required_ages(world: str) -> dict:
    """Item -> the age it needs in the built mod for this world (0 Antiquity, 1 Exploration, 2 Modern),
    from its unlock rows; the unlocks are OR, so the earliest counts. An int is the civ age (tech
    track); a pair (tech or None, civic) also counts the civic age, for items of main-tree, Test of
    Time and branch civics (see too_early and node_track). A civ-unique item with no unlock row needs
    the age of its civ (the age of the civ's unique tree)."""
    mods = c.load_base_modules(include_dlc=True) + [c.parse_modinfo(MOD_DIR / "continuous-ages.modinfo")]
    sim = c.Simulator()
    for path in c.database_items(c.applicable_groups(mods, world)):
        sim.apply_file(path)
    q = lambda sql: sim.db.execute(sql).fetchall()
    short = {"AQ": 0, "EX": 1, "MO": 2}
    tree_of = dict(q("SELECT ProgressionTreeNodeType, ProgressionTree FROM ProgressionTreeNodes"))
    world_rank = short[{"AGE_ANTIQUITY": "AQ", "AGE_EXPLORATION": "EX", "AGE_MODERN": "MO"}[world]]
    def node_track(n):
        """(track, age): tech or civic. A later-age civ tree's node: a unique tree shows with the tech
        gate (rule 5e), a Test of Time tree with the civic gate (rule 5i); branch trees (Theology,
        ideologies) count as civic (they need civics of that age). In a later world, rule 2f: tech."""
        for age, tech, civic in ((0, ("NODE_TECH_AQ_",), ("NODE_CIVIC_AQ_MAIN_",)),
                                 (1, ("NODE_TECH_EX_", "NODE_TECH_CA_EXPLORATION_"), ("NODE_CIVIC_EX_MAIN_", "NODE_CIVIC_CA_EXPLORATION_")),
                                 (2, ("NODE_TECH_MO_", "NODE_TECH_CA_MODERN_"), ("NODE_CIVIC_MO_MAIN_", "NODE_CIVIC_CA_MODERN_"))):
            if n.startswith(tech):
                return "tech", age
            if n.startswith(civic):
                return "civic", age
        tree = tree_of.get(n) or ""
        parts = tree.split("_")  # TREE_CIVICS_<age>_<name>
        age = short.get(parts[2]) if len(parts) > 2 else None
        if age is None:
            return None, None
        if age < world_rank or not (tree.endswith("_TEST_OF_TIME") or "_BRANCH_" in tree):
            return "tech", age
        return "civic", age
    rows = {}
    for node, target in q("SELECT ProgressionTreeNodeType, TargetType FROM ProgressionTreeNodeUnlocks "
                          "WHERE TargetKind IN ('KIND_UNIT', 'KIND_CONSTRUCTIBLE')"):
        track, age = node_track(node)
        if track:
            rows.setdefault(target, []).append((track, age))
    need = {}
    for t, alts in rows.items():
        tech = min((a for track, a in alts if track == "tech"), default=None)
        civic = min((a for track, a in alts if track == "civic"), default=None)
        need[t] = tech if civic is None else (tech, civic)
    # Civ age: the age of the civ's unique tree.
    civ_age = {}
    for (tree,) in q("SELECT ProgressionTreeType FROM ProgressionTrees WHERE ProgressionTreeType LIKE 'TREE_CIVICS_%'"):
        parts = tree.split("_", 3)
        if len(parts) == 4 and parts[2] in short:
            civ_age["CIVILIZATION_" + parts[3]] = short[parts[2]]
    trait_civ = {}
    for trait, civ in q("SELECT TraitType, CivilizationType FROM CivilizationTraits"):
        trait_civ.setdefault(trait, set()).add(civ)
    for t, trait in q("SELECT UnitType, TraitType FROM Units WHERE TraitType IS NOT NULL UNION "
                      "SELECT ConstructibleType, TraitType FROM Buildings WHERE TraitType IS NOT NULL UNION "
                      "SELECT ConstructibleType, TraitType FROM Improvements WHERE TraitType IS NOT NULL"):
        civs = trait_civ.get(trait, set())
        if t not in rows and len(civs) == 1 and next(iter(civs)) in civ_age:
            need[t] = civ_age[next(iter(civs))]
    return need


def item_names() -> dict:
    """Text key (LOC_..._NAME, as the purchase log writes items) -> unit or constructible type."""
    out = {}
    for w in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"):
        sim = c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True)
        for name, typ in sim.db.execute("SELECT Name, UnitType FROM Units UNION ALL SELECT Name, ConstructibleType FROM Constructibles"):
            out.setdefault(name, typ)
    return out


def production_leaks(qfile: Path, players: list, item_col: int = 4, names: dict | None = None) -> list[tuple]:
    """Items that a civ started (or, with the purchase log, bought) before it reached the civ age
    that the item's unlocks need (the unlocks are OR: the earliest one counts). players: PLAYER
    check records. item_col and names: the purchase log has the item's text key in column 3."""
    worlds = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
    need = {w: required_ages(w) for w in worlds}
    timeline = {}
    for p in players:
        if "civAge" in p and p.get("age") in worlds:
            timeline.setdefault((p["age"], p["id"]), []).append((p["turn"], (p["civAge"], p.get("civicAge"))))
    # The world of the log's first segment: a run from a save does not start in Antiquity.
    base = worlds.index(players[0]["age"]) if players and players[0].get("age") in worlds else 0
    seg, last_turn, seen, leaks = 0, 0, set(), []
    for row in csv.reader(qfile.open(encoding="utf-8", errors="replace")):
        if len(row) <= item_col or not row[0].strip().isdigit():
            continue
        turn, pid, item = int(row[0]), int(row[1]), row[item_col].strip()
        if names is not None:
            item = names.get(item, item)
        if turn < last_turn:
            seg += 1
        last_turn = turn
        world = worlds[min(base + seg, 2)]
        key = (seg, pid, row[2].strip(), item, turn if names is not None else None)
        if key in seen:
            continue
        seen.add(key)
        required = need[world].get(item)
        if required is None or required == 0:
            continue
        # The civ's age at the first check at or after this turn. Checks run every few turns, so a
        # civ can pass its gate between two checks; only a later check that still shows the lower
        # age proves a leak.
        later = [ages for t, ages in sorted(timeline.get((world, pid), []), key=lambda x: x[0]) if t >= turn]
        civ_age, civic_age = later[0] if later else (None, None)
        if too_early(required, civ_age, civic_age):
            leaks.append((world, turn, pid, row[2].strip(), item, civ_age if civic_age is None else f"{civ_age}/civic {civic_age}"))
    return leaks


def replace_starts(qfile: Path, players: list) -> tuple[list[str], bool]:
    """Rule 2i on the production log (the ground truth; UI queries answer only for the observed player).
    For each gap pair (a unique unit that waits for its Breakthrough, and the base unit of an earlier age it
    replaces; the list the build wrote into ca-checks.js) and each civ of that pair's trait: base units
    started before the civ's gate (the rule works: in 0.3.0 such a civ could not train them), base units
    started after the gate (FAIL: the base game's replacement must hold), and unique units after the gate."""
    worlds = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
    m = re.search(r"const CA_REPLACE_GAPS = (\[.*?\]);", (MOD_DIR / "ui" / "ca-checks.js").read_text(encoding="utf-8"))
    gaps = json.loads(m.group(1)) if m else []
    if not gaps:
        return ["## Unique units and their base units (rule 2i)", "", "- no gap pairs in this build", ""], False
    civs_of = {}
    for w in worlds:
        for civ, trait in c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True).db.execute(
                "SELECT CivilizationType, TraitType FROM CivilizationTraits"):
            civs_of.setdefault(trait, set()).add(civ.replace("CIVILIZATION_", ""))
    rank = {"AQ": 0, "EX": 1, "MO": 2}
    gate_rank = {"AGE_EXPLORATION": 1, "AGE_MODERN": 2}
    timeline = {}
    for p in players:
        if p.get("age") in worlds and "civAge" in p:
            timeline.setdefault((p["age"], p["id"]), []).append((p["turn"], p["civ"], p["civAge"]))
    base_world = worlds.index(players[0]["age"]) if players and players[0].get("age") in worlds else 0
    by_item = {}
    for g in gaps:
        by_item.setdefault(g[0], []).append(("uu", g))
        by_item.setdefault(g[1], []).append(("base", g))
    counts, seg, last_turn, prev = {}, 0, 0, {}
    for row in csv.reader(qfile.open(encoding="utf-8", errors="replace")):
        if len(row) < 6 or not row[0].strip().isdigit():
            continue
        turn, pid, city, item = int(row[0]), int(row[1]), row[2].strip(), row[4].strip()
        try:
            progress = float(row[5])
        except ValueError:
            progress = 0.0
        if turn < last_turn:
            seg += 1
            prev = {}
        last_turn = turn
        last = prev.get((pid, city))
        prev[(pid, city)] = (item, progress)
        if last is not None and last[0] == item and progress >= last[1]:
            continue  # the same item still in production
        world = worlds[min(base_world + seg, 2)]
        checks = sorted(timeline.get((world, pid), []))
        if not checks or item not in by_item:
            continue
        civ = checks[0][1]
        before_turn = [a for t, _, a in checks if t <= turn]
        after_turn = [a for t, _, a in checks if t >= turn]
        for role, (uu, base, trait, age) in by_item[item]:
            if civ not in civs_of.get(trait, ()):
                continue
            if before_turn and rank[before_turn[-1]] >= gate_rank[age]:
                when = "after"
            elif after_turn and rank[after_turn[0]] < gate_rank[age]:
                when = "before"
            else:
                when = "unknown"
            e = counts.setdefault((world, pid, civ, uu, base), _C())
            e[f"{role}_{when}"] += 1
    lines = ["## Unique units and their base units (rule 2i)", "",
             f"Gap pairs in the build: {len(gaps)}. A civ of the pair's trait must be able to train the base unit "
             "before its Breakthrough tech, and only the unique unit after it (production log; 'unknown' = between two checks).", ""]
    failed = False
    if not counts:
        lines += ["- no civ of a gap pair's trait started either unit", ""]
        return lines, False
    lines += ["| World age | Player | Civ | Pair | Base before gate | Base after gate | Base unknown | Unique after gate |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for (world, pid, civ, uu, base), e in sorted(counts.items()):
        bad = e["base_after"] > 0
        failed |= bad
        lines.append(f"| {world} | {pid} | {civ} | {uu.replace('UNIT_', '')} > {base.replace('UNIT_', '')} | {e['base_before']} | "
                     f"{e['base_after']}{' FAIL' if bad else ''} | {e['base_unknown']} | {e['uu_after']} |")
    return lines + [""], failed


def gov_report(players: list, transitions: list | None = None, entered_unseen: list | None = None) -> tuple[list[str], bool]:
    """Rule 3: a civ's government is one of the world age's (as in the base game, where each world offers only its
    own; the base game's StartingGovernments of each world give a government's age). Governments that no world
    offers at the start (Revolución and others set by effects) are not checked. Before the fix of the AI's
    government biases, every run had a civ with an older-age government (105 of 105 runs; 20261029-202958:
    Egypt kept Oligarchy in the Modern world)."""
    age_of = {}  # government -> the worlds that offer it (one government can be offered in more than one)
    for w in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"):
        for (g,) in c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True).db.execute(
                "SELECT GovernmentType FROM StartingGovernments WHERE AgeType = ?", (w,)):
            age_of.setdefault(g.replace("GOVERNMENT_", ""), set()).add(w)
    wrong = {}
    for p in players:
        gov, world = p.get("gov"), p.get("age")
        if gov and world and gov in age_of and world not in age_of[gov]:
            wrong.setdefault((world, p["id"], p.get("civ"), gov), p["turn"])
    lines = ["## Governments of the world age (rule 3)", ""]
    if not wrong:
        return lines + ["- every civ has a government of its world age (or one set by an effect)", ""], False
    # A run from a save starts in a world without a transition in this run: a government that the civ had at its
    # first record there came with the save (a save of 0.3.0, before rule 3: iterations 20261101-010042 to
    # 010428). Rule 3 acts at the next world transition (20261101-010214: none wrong after it).
    order = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
    entered = {order[order.index(t["from"]) + 1] for t in (transitions or []) if t.get("from") in order[:-1]}
    entered |= set(entered_unseen or [])
    first = {}
    for p in players:
        if p.get("age"):
            first.setdefault((p["age"], p["id"]), p)
    failed = False
    for (w, pid, civ, gov), t in sorted(wrong.items(), key=lambda x: (str(x[0][0]), x[0][1]))[:20]:
        f = first.get((w, pid), {})
        if w not in entered and f.get("turn", 1) > 1 and f.get("gov") == gov:
            lines.append(f"- KNOWN LIMIT (U-GOV-SAVE): {w}, player {pid} ({civ}) has {gov} ({', '.join(sorted(age_of[gov]))}) "
                         f"since the load of the save (turn {f.get('turn')}); rule 3 acts at the next world transition")
        else:
            failed = True
            lines.append(f"- GOV-AGE FAIL: {w}, player {pid} ({civ}) has {gov} ({', '.join(sorted(age_of[gov]))}) from turn {t}")
    return lines + [""], failed


def bank_report(banks: list) -> tuple[list[str], bool]:
    """Hidden culture and science (BANK records): yield that no node took, paid out one node per turn. A bank
    that grows at 3 checks in a row past 3 turns of yield means a tree with no next node for the civ (the
    0.2.1 civic dead end): FAIL (design goal 6). A bank from an earlier version's save only shrinks."""
    series = {}
    for r in banks:
        for kind in ("culture", "science"):
            e = r.get(kind) or {}
            if "lo" in e:
                series.setdefault((r.get("age"), r["id"], kind), []).append((r["turn"], e["lo"], max(1, e.get("rate") or 1)))
    if not series:
        return [], False
    lines = ["## Hidden culture and science (yield no node took; design goal 6)", "",
             "| World age | Player | Yield | Largest bank (turns of yield) | At turn | Growing at 3 checks in a row |",
             "| --- | --- | --- | --- | --- | --- |"]
    failed = False
    for (age, pid, kind), s in sorted(series.items(), key=lambda x: (str(x[0][0]), x[0][1], x[0][2])):
        s.sort()
        top = max(s, key=lambda x: x[1] / x[2])
        grow = any(all(s[i + k + 1][1] > s[i + k][1] for k in range(3)) and s[i + 3][1] > 3 * s[i + 3][2]
                   for i in range(len(s) - 3))
        failed |= grow
        if top[1] > top[2] or grow:
            lines.append(f"| {age} | {pid} | {kind} | {top[1]} ({top[1] / top[2]:.1f}) | {top[0]} | {'FAIL' if grow else 'no'} |")
    if len(lines) == 4:
        lines.append("| all | - | - | under one turn of yield | - | no |")
    return lines + [""], failed


# Catch-up Research (CATCHUP records): the bonus of each setting, the window around the expected speed and the
# samples a group needs. Medians of the 33 runs with node records (20261025-170959 to 20261031-132723, 217 groups
# of 5 samples or more): speed 0.98 to 1.08 where 1x is
# expected (option off, and nodes of the world age), 2.05 and 2.12 at +100%, 1.52 and 1.56 at +50%; costs exactly
# 0.50, 0.67 or 1.00 of the base. The window keeps every real group and fails a wrong level: 1.5x where 2x is
# expected is 0.75, 2x where 1.5x is expected 1.33, 1.5x where 1x is expected 1.5. Groups of 3 samples were
# dominated by a hidden culture bank (7.58 in 20261029-141650, a 0.2.1 save), so a group needs 5.
CATCHUP_BONUS = {"CA_CATCHUP_100": 1.0, "CA_CATCHUP_50": 0.5, "CA_CATCHUP_OFF": 0.0, "null": 0.0, "None": 0.0}
CATCHUP_WINDOW = (0.85, 1.20)
CATCHUP_MIN_SAMPLES = 5


def catchup_report(recs: list) -> tuple[list[str], bool]:
    """Catch-up Research (docs/settings.md), from the CATCHUP records (one per civ, check and node group). The game
    shows the bonus in the cost (getNodeCost; the effect of System of Ideas), not in the turns, so each sample gives:
      rate:  (cost - progress) / (turns - 0.5) / yield, about 1: the turns follow the cost shown. getTurnsForNode is
             a ceiling, so the true turns lie in (turns - 1, turns]; the midpoint removes the bias (the plain ratio
             had medians 0.84 to 1.03, the midpoint 0.97 to 1.11, in 227 groups of 33 runs). Turns 0 and 1 say
             nothing of the rate (a hidden bank, docs/known-limits.md, or the last turn): left out.
      cost:  cost / base cost; the base is the node's cost in this run where no bonus applies (a world of the
             node's age or earlier), by tree and node: the tech and civic Breakthroughs have the same name in the
             records (CA_MODERN_BREAKTHROUGH) and different costs (1740 and 1008, 20261031-152452). Depth 0 only:
             mastery costs differ between civs (79 and 93 with the option off, 20261029-142802). Future Tech is
             left out: its cost grows with each repeat.
      speed: rate * base / cost, the research speed against the base cost. Expected: 1 + bonus for nodes of the
             earlier ages and the Breakthroughs into the world age (they count as the age before), else 1.
    FAIL when a group's median speed is outside CATCHUP_WINDOW times the expected speed. A group without a base
    cost in the run (a run from a save) is listed, not judged."""
    worlds = {"AGE_ANTIQUITY": 0, "AGE_EXPLORATION": 1, "AGE_MODERN": 2}
    med = lambda v: (sorted(v)[(len(v) - 1) // 2] + sorted(v)[len(v) // 2]) / 2
    def node_age(group, n):
        if group.endswith(" gate"):
            return 0 if "EXPLORATION" in n else 1  # a Breakthrough belongs to the age before it
        return AGE_RANK.get(group.split()[-1])
    samples = []
    for r in recs:
        w = worlds.get(r.get("age"))
        if w is None or not isinstance(r.get("nodes"), dict):
            continue  # older format (a cut line, or no node list)
        for group, items in r["nodes"].items():
            kind = group.split()[0]
            y = r.get("science") if kind == "tech" else r.get("culture")
            for s in items if isinstance(items, list) else []:
                a = node_age(group, s.get("n", ""))
                if a is None or "FUTURE" in s.get("n", "") or not isinstance(s.get("cost"), (int, float)) or s["cost"] <= 0:
                    continue
                samples.append((r["age"], w, kind, a, s, y, str(r.get("setting"))))
    if not samples:
        return ["## Catch-up Research (CATCHUP)", "", "- no CATCHUP records with node lists: not checked", ""], False
    base = {}
    for _, w, kind, a, s, _, _ in samples:
        if a >= w and s.get("d") == 0:
            base.setdefault((kind, s["n"]), []).append(s["cost"])
    base = {n: med(v) for n, v in base.items()}
    groups = {}
    for age, w, kind, a, s, y, setting in samples:
        e = groups.setdefault((w, age, a < w, kind), {"settings": set(), "rate": [], "cost": [], "speed": []})
        e["settings"].add(setting)
        turns = s.get("turns")
        rate = None
        if isinstance(turns, (int, float)) and turns >= 2 and isinstance(y, (int, float)) and y > 0:
            rate = (s["cost"] - (s.get("prog") or 0)) / (turns - 0.5) / y
            e["rate"].append(rate)
        b = base.get((kind, s["n"])) if s.get("d") == 0 else None
        if b:
            e["cost"].append(s["cost"] / b)
            if rate is not None:
                e["speed"].append(rate * b / s["cost"])
    lines = ["## Catch-up Research (CATCHUP)", "",
             "Research speed against the base cost, by node group (medians). Rate: (cost - progress) / (turns - 0.5) / yield; "
             "cost: against the node's cost where no bonus applies; speed: rate times base / cost. Expected: 1 + bonus "
             f"for earlier-age nodes and the Breakthroughs into the world age, else 1; window {CATCHUP_WINDOW[0]} to "
             f"{CATCHUP_WINDOW[1]} of the expected value, at least {CATCHUP_MIN_SAMPLES} samples.", "",
             "| World age | Nodes | Setting | Expected | Samples (rate, speed) | Rate | Cost / base | Speed | Result |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    failed = False
    for (w, age, earlier, kind), e in sorted(groups.items(), key=lambda x: (x[0][0], not x[0][2], x[0][3])):
        bonuses = {CATCHUP_BONUS.get(s) for s in e["settings"]}
        bonus = next(iter(bonuses)) if len(bonuses) == 1 else None
        nodes = f"{kind}s of earlier ages, Breakthroughs into this age" if earlier else f"{kind}s of this age and later"
        want = None if bonus is None else (1 + bonus if earlier else 1.0)
        fmt = lambda v, d=2: f"{med(v):.{d}f}" if v else "-"
        if want is None:
            result = f"not judged (setting {', '.join(sorted(e['settings']))})"
        elif len(e["speed"]) < CATCHUP_MIN_SAMPLES:
            result = "not judged (" + ("no base cost in this run" if e["rate"] and not e["cost"] else "too few samples") + ")"
        else:
            ratio = med(e["speed"]) / want
            bad = not (CATCHUP_WINDOW[0] <= ratio <= CATCHUP_WINDOW[1])
            failed |= bad
            result = f"FAIL ({ratio:.2f} of expected)" if bad else "ok"
        lines.append(f"| {age} | {nodes} | {', '.join(sorted(e['settings']))} | {want if want is not None else '-'} | "
                     f"{len(e['rate'])}, {len(e['speed'])} | {fmt(e['rate'])} | {fmt(e['cost'])} | {fmt(e['speed'])} | {result} |")
    return lines + [""], failed


# The civ age banner's age names (English text of GameInfo.Ages; another language is listed, not compared).
BANNER_AGES = {"Antiquity": "AQ", "Exploration": "EX", "Modern": "MO"}


def banner_report(checks: list[str]) -> tuple[list[str], bool]:
    """The civ age banner (ui/ca-civ-age.js) shows the local player's civ age and the world age, and logs a line
    when its text changes. Each shown text is compared with that player's PLAYER records while it is shown; when the
    banner is hidden at once (autoplay: the observer, local player -1, takes over a moment after each load) it is
    compared with the player's next check in the same world. A mismatch at two comparisons in a row fails; one
    alone is a lag (the banner updates every 3 seconds and at each turn, the checks every 5 turns)."""
    rx = re.compile(r"civ age banner(?:, player (\d+): [^:]*: (.+?) \S [^:]*: (.+?)\s*$| hidden)")
    worlds = {"AQ": "AGE_ANTIQUITY", "EX": "AGE_EXPLORATION", "MO": "AGE_MODERN"}
    events, hidden, unknown = [], 0, 0
    for l in checks:
        if not l.startswith("UI.log: "):
            continue
        m = rx.search(l) if "[CA-CHECK][UI] civ age banner" in l else None
        if m and m.group(1) is None:
            hidden += 1
            events.append(("hidden",))
        elif m:
            civ, world = BANNER_AGES.get(m.group(2)), BANNER_AGES.get(m.group(3))
            unknown += civ is None or world is None
            events.append(("banner", int(m.group(1)), civ, world))
        elif "[CA-CHECK][PLAYER] " in l:
            try:
                events.append(("player", json.loads(l.split("[CA-CHECK][PLAYER] ", 1)[1], strict=False)))
            except json.JSONDecodeError:
                pass
    shown = [(i, e) for i, e in enumerate(events) if e[0] == "banner"]
    lines = ["## Civ age banner (local player)", ""]
    if not shown:
        return lines + ["- no banner text in this run (no local player)", ""], False
    comps, inside_n, after_n = {}, 0, 0
    for i, (_, pid, civ, world) in shown:
        if civ is None or world is None:
            continue
        inside = []
        for f in events[i + 1:]:
            if f[0] != "player":
                break
            if f[1].get("id") == pid:
                inside.append(f[1])
        inside_n += len(inside)
        if not inside:
            nxt = next((f[1] for f in events[i + 1:] if f[0] == "player" and f[1].get("id") == pid), None)
            if nxt and nxt.get("age") == worlds[world]:
                inside, after_n = [nxt], after_n + 1
        for p in inside:
            ok = p.get("civAge") == civ and p.get("age") == worlds[world]
            comps.setdefault(pid, []).append((ok, p.get("age"), p.get("turn"), p.get("civAge"), civ, world))
    failed = False
    mism = []
    for pid, cs in comps.items():
        for k, (ok, age, turn, civ_age, civ, world) in enumerate(cs):
            if ok:
                continue
            twice = (k > 0 and not cs[k - 1][0]) or (k + 1 < len(cs) and not cs[k + 1][0])
            failed |= twice
            mism.append(f"- {'BANNER FAIL' if twice else 'banner lag'}: player {pid}, {age} turn {turn}: the check says civ age "
                        f"{civ_age}; the banner shows civ age {civ}, world {world}")
    total = sum(len(cs) for cs in comps.values())
    lines += [f"- banner texts: {len(shown)} (players {', '.join(str(p) for p in sorted({e[1] for _, e in shown}))}); "
              f"hidden for the observer: {hidden} times" + (f"; {unknown} with age names not in English, not compared" if unknown else ""),
              f"- compared with the player's checks: {total} ({inside_n} while shown, {after_n} at the next check after a "
              f"text that was hidden at once); mismatches: {len(mism)}"]
    return lines + mism[:10] + [""], failed


def gate_report(kind: str, recs: list) -> tuple[list[str], bool]:
    """Later-age civics (CIVICGATE) or techs (TECHGATE) that the engine refuses although their prereqs and gate are
    complete (stuck), or allows before the gate (leak), per world age. The in-game check logs a FAIL line too; this
    reads the records, so that the report has the table. Stuck counts at two checks in a row of the same player in
    one world, a record only when its control node was allowed (trusted). Runs before TECHGATE: skipped."""
    what = {"CIVICGATE": "civics", "TECHGATE": "techs"}[kind]
    title = f"## Later-age {what}: the engine's verdict ({kind})"
    if not recs:
        return [title, "", f"- no {kind} records in this run (older build): not checked", ""], False
    order = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
    series = {}
    for r in recs:
        series.setdefault((r.get("age"), r["id"]), []).append(r)
    by_world = {}
    for (age, pid), s in series.items():
        s.sort(key=lambda r: r["turn"])
        e = by_world.setdefault(age, {"players": set(), "checks": 0, "trusted": 0, "open": 0, "stuck": {}, "leak": {}})
        e["players"].add(pid)
        e["checks"] += len(s)
        e["trusted"] += sum(1 for r in s if r.get("trusted", True))
        e["open"] = max([e["open"]] + [max(len(r.get("open", [])), r.get("nOpen", 0)) for r in s])
        # Each player and node once, with the first turn seen.
        for a, b in zip(s, s[1:]):
            both = {x["n"] for x in a.get("stuck", [])} & {x["n"] for x in b.get("stuck", [])}
            for n in sorted(both) if b.get("trusted", True) else []:
                e["stuck"].setdefault(f"player {pid} {n}", f"turns {a['turn']}, {b['turn']}")
        for r in s:
            leak = list(r.get("leak", [])) if r.get("trusted", True) else []
            leak += [r["researching"]] if r.get("researching") else []
            for n in leak:
                e["leak"].setdefault(f"player {pid} {n}", f"turn {r['turn']}")
    lines = [title, "", "| World age | Players | Checks (trusted) | Open later-age nodes (most at one check) | "
                        "Stuck at two checks in a row | Leaks |", "| --- | --- | --- | --- | --- | --- |"]
    failed = False
    for age, e in sorted(by_world.items(), key=lambda x: order.index(x[0]) if x[0] in order else 9):
        failed |= bool(e["stuck"] or e["leak"])
        cell = lambda d: (f"FAIL: {'; '.join(f'{k} ({t})' for k, t in list(d.items())[:4])}"
                          + (f" (+{len(d) - 4})" if len(d) > 4 else "")) if d else "none"
        lines.append(f"| {age} | {len(e['players'])} | {e['checks']} ({e['trusted']}) | {e['open']} | {cell(e['stuck'])} | {cell(e['leak'])} |")
    return lines + [""], failed


def transition_count_report(transitions: list, expect: int | None) -> tuple[list[str], bool]:
    """Design goal 4: the world still goes through its ages. With --expect-transitions N, a run long enough
    for N age ends must have N TRANSITION records (the Modern age end writes one too)."""
    n = len(transitions)
    if expect is None:
        return [f"- world transitions: {n} (no expected count; iterate.py --expect-transitions N)"], False
    if n < expect:
        return [f"- TRANSITION COUNT FAIL: {n} world transitions, expected at least {expect}"], True
    return [f"- world transitions: {n}, expected at least {expect}"], False


def reload_resource_batches() -> list[dict]:
    """RELOADRES records of the transition script (Scripting.log), one batch per transition: age (the new
    world), before (after the load) and after (after the transition step), each {type: [plots, island
    plots]}, and the island plots that the base game's Exploration step logged as replaced in between."""
    out = []
    script = LOGS / "Scripting.log"
    if not script.exists():
        return out
    for line in script.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[CA-CHECK][RELOADRES] " in line:
            try:
                r = json.loads(line.split("[CA-CHECK][RELOADRES] ", 1)[1], strict=False)
            except json.JSONDecodeError:
                continue  # a line cut by the log
            when = r.get("when")
            if when not in ("before", "after"):
                continue
            # A batch starts at 'before'; an 'after' without its 'before' starts one too.
            if r.get("part", 0) == 0 and (when == "before" or not out or out[-1]["after"] is not None):
                out.append({"age": r.get("age"), "before": None, "after": None, "replaced": 0})
            if not out:
                continue
            b = out[-1]
            b["age"] = b["age"] or r.get("age")
            if b[when] is None:
                b[when] = {}
            b[when].update({p[0]: list(p[1:]) for p in r.get("plots", []) if p})
        elif "replaceIslandResources():" in line and out and out[-1]["after"] is None:
            # The base game's line (maps/map-utilities.js), between this transition's two records.
            m = re.search(r"Replaced=(\d+)", line)
            if m:
                out[-1]["replaced"] += int(m.group(1))
    return out


def reload_slots(transitions: list, res_batches: list, n_batches: int) -> tuple[list, list[str]]:
    """The reload batch of each TRANSITION record (None for the last age), and the new world ages of the
    reloads that have no TRANSITION record. The batches (RELOAD, RELOADUNITS, RELOADCONS, GATEMODS,
    RELOADRES) are one per world transition, in order. A transition can lack its TRANSITION and AGEEND
    records: in 20261031-214228 the game started the Antiquity transition before the UI handled GameAgeEnded,
    so the test's handler never ran, and the next TRANSITION record was paired with the wrong batch. So
    match by the new world age of the RELOADRES batch; older runs without it use the position."""
    order = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
    ages = [b.get("age") for b in res_batches]
    by_age = len(ages) == n_batches and all(ages)
    slots, seen = [], set()
    for ti, t in enumerate(transitions):
        if t.get("from") not in order[:-1]:
            slots.append(None)
            continue
        nxt = order[order.index(t["from"]) + 1]
        seen.add(nxt)
        slots.append((ages.index(nxt) if nxt in ages else None) if by_age else ti)
    return slots, [a for a in ages if by_age and a not in seen]


def reload_reset_report(transitions: list, ends: list, reload_batches: list, ui_resources: list,
                        res_batches: list, slots: list | None = None) -> tuple[list[str], bool]:
    """Design goal 1, the base game's headline resets: at each world transition, the age end (AGEEND and
    RESOURCES, UI.log) against the reload (RELOAD and RELOADRES, written by the transition script before any
    civ plays, so a civ's first turn cannot hide a reset). FAIL on fewer cities (a city made a town), less
    gold or influence (a cap), or fewer plots of a resource type that was on the map (old resources removed;
    the new age's resources only add). Fields that older runs lack are skipped."""
    order = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
    lines, failed = ["## No reset at the reload (design goal 1: cities, gold, influence, resources)", ""], False
    # Both records round the balance. In the 806 civ transitions of build/iterations up to 20261031-125020,
    # gold after the reload was never lower than at the age end (803 equal, 3 higher by 200), so 1 allows for
    # rounding only. A cap cuts a balance to 6000 gold and 800 influence into Exploration (base game,
    # Continuity setting, standard speed), so it shows only for a civ above that: the report gives the largest.
    tol = 1
    end_res = {}
    for r in ui_resources:
        if r.get("when") != "end":
            continue
        if r.get("part", 0) == 0:
            end_res[r.get("age")] = {}
        end_res.setdefault(r.get("age"), {}).update({p[0]: p[1] for p in r.get("plots", []) if len(p) > 1})
    have_res = bool(ui_resources or res_batches)
    if not have_res:
        lines.append("- resource plots: not recorded in this run (older run)")

    def plots(d, k, island=False):
        v = d.get(k) or [0, 0]
        return (v[1] if len(v) > 1 else 0) if island else v[0]
    for ti, t in enumerate(transitions):
        if t.get("from") not in order[:-1]:
            continue  # the game ends after the last age
        nxt = order[order.index(t["from"]) + 1]
        lines.append(f"- {t['from']} -> {nxt}:")
        before = {e["id"]: e for e in ends if e.get("age") == t["from"]}
        si = slots[ti] if slots is not None else ti
        reload = reload_batches[si] if si is not None and si < len(reload_batches) else {}
        n_city, n_money, top = 0, {"gold": 0, "influence": 0}, {"gold": 0, "influence": 0}
        for pid in sorted(before):
            b, r = before[pid], reload.get(pid)
            if r is None:
                continue  # the age transitions section fails a missing RELOAD record
            if isinstance(b.get("cities"), int) and isinstance(r.get("cities"), int):
                n_city += 1
                cb, ca, tb, ta = b["cities"], r["cities"], b.get("towns", 0), r.get("towns", 0)
                if ca < cb:
                    failed = True
                    lines.append(f"  - CITY FAIL: player {pid} cities {cb} -> {ca}, towns {tb} -> {ta} at the reload"
                                 + (" (cities made towns)" if ta > tb else ""))
                elif (ca, ta) != (cb, tb):
                    what = ("new settlements" if ca + ta > cb + tb else "towns made cities" if ca + ta == cb + tb
                            else "fewer settlements")
                    lines.append(f"  - player {pid}: cities {cb} -> {ca}, towns {tb} -> {ta} at the reload ({what})")
            for k in ("gold", "influence"):
                vb, vr = b.get(k), r.get(k)
                # -1 is the records' value when the call gave none.
                if not isinstance(vb, (int, float)) or not isinstance(vr, (int, float)) or -1 in (vb, vr):
                    continue
                n_money[k] += 1
                top[k] = max(top[k], vb)
                if vr < vb - tol:
                    failed = True
                    lines.append(f"  - {k.upper()} CAP FAIL: player {pid} {k} {vb} at the age end, {vr} after the reload")
        lines.append(f"  - cities and towns compared for {n_city} civs"
                     + ("" if n_city else " (not in the RELOAD record: older run)"))
        lines.append(f"  - gold compared for {n_money['gold']} civs, influence for {n_money['influence']} "
                     f"(largest at the age end: gold {top['gold']}, influence {top['influence']})")
        if not have_res:
            continue
        er = end_res.get(t["from"])
        rb = next((x for x in res_batches if x["age"] == nxt), None)
        if rb is None and ti < len(res_batches) and res_batches[ti]["age"] is None:
            rb = res_batches[ti]
        if er is None or rb is None or rb["before"] is None or rb["after"] is None:
            failed = True
            lines.append(f"  - RESOURCE FAIL: records missing (age end {er is not None}, after the load "
                         f"{bool(rb and rb['before'] is not None)}, after the transition step {bool(rb and rb['after'] is not None)})")
            continue
        bef, aft, rep = rb["before"], rb["after"], rb["replaced"]
        load_gone = {k: f"{v} -> {plots(bef, k)}" for k, v in er.items() if plots(bef, k) < v}
        land = lambda d, k: plots(d, k) - plots(d, k, True)
        land_gone = {k: f"{land(bef, k)} -> {land(aft, k)}" for k in bef if land(aft, k) < land(bef, k)}
        island_gone = {k: plots(bef, k, True) - plots(aft, k, True) for k in bef if plots(aft, k, True) < plots(bef, k, True)}
        if load_gone:
            failed = True
            lines.append(f"  - RESOURCE FAIL: fewer plots after the load than at the age end: {load_gone}")
        if land_gone:
            failed = True
            lines.append(f"  - RESOURCE FAIL: fewer plots off islands after the transition step: {land_gone}")
        # The base game's Exploration step (replaceIslandResources, MapIslandBehavior) replaces island resources
        # with treasure resources for the treasure fleets; its log line gives how many (1 to 18 in 95 runs).
        if island_gone and sum(island_gone.values()) <= rep:
            lines.append(f"  - island resources: the base game's Exploration step replaced {rep} with treasure resources "
                         f"(a world system); fewer on islands: {island_gone}")
        elif island_gone:
            failed = True
            lines.append(f"  - RESOURCE FAIL: {sum(island_gone.values())} fewer island plots, the base game's step "
                         f"replaced {rep}: {island_gone}")
        new = sorted(set(aft) - set(er))
        lines.append(f"  - resources: {len(er)} types, {sum(er.values())} plots at the age end; {len(aft)} types, "
                     f"{sum(plots(aft, k) for k in aft)} plots after the reload; new types: {', '.join(new) or 'none'}")
    return lines + [""], failed


_LEGACY_AGES = None


def legacy_ages() -> dict:
    """Legacy type -> its age (Legacies.Age; each world loads only its own age's legacies)."""
    global _LEGACY_AGES
    if _LEGACY_AGES is None:
        _LEGACY_AGES = {}
        for w in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"):
            sim = c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True)
            _LEGACY_AGES.update(dict(sim.db.execute("SELECT LegacyType, Age FROM Legacies")))
    return _LEGACY_AGES


def legacy_report(lfile: Path, worlds: list) -> tuple[list[str], bool]:
    """Design goal 4, world systems wait for the world: legacies (each age's legacy rewards; Player_Legacies.csv:
    player, turn, legacy) of a later age than the world they came in. The CSV has no age, and its turn restarts in
    each world, so a world boundary shows only where the turn goes down: the i-th part of the log is world i or
    a later one, up to i + (worlds - parts). A legacy fails only when it is later than every world its part can
    be; when it is later than some of them, it is listed as not judged."""
    if not lfile.exists() or not worlds:
        return [], False
    rank = {"AGE_ANTIQUITY": 0, "AGE_EXPLORATION": 1, "AGE_MODERN": 2}
    prefix = {"LEGACY_AQ_": "AGE_ANTIQUITY", "LEGACY_EX_": "AGE_EXPLORATION", "LEGACY_MO_": "AGE_MODERN"}
    parts, last = [], None
    for row in csv.reader(lfile.open(encoding="utf-8", errors="replace")):
        if len(row) < 3 or not row[1].strip().isdigit():
            continue
        turn, legacy = int(row[1]), re.sub(r"\(\d+\)$", "", row[2].strip())  # "LEGACY_AQ_SCIENTIFIC_4(28)"
        if not parts or turn < last:
            parts.append([])
        last = turn
        parts[-1].append((row[0].strip(), turn, legacy))
    head = ["## Legacies by world age (design goal 4: world systems wait for the world)", ""]
    slack = len(worlds) - len(parts)
    if slack < 0:
        return head + [f"- {len(parts)} parts in Player_Legacies.csv for {len(worlds)} worlds: not judged", ""], False
    lines = head + ["| Part of the log | World | Legacies | By age |", "| --- | --- | --- | --- |"]
    fails, unsure = [], []
    for i, part in enumerate(parts):
        lo, hi = worlds[i], worlds[min(len(worlds) - 1, i + slack)]
        ages = _C()
        for pid, turn, legacy in part:
            a = legacy_ages().get(legacy) or next((v for p, v in prefix.items() if legacy.startswith(p)), None)
            ages[a or "unknown"] += 1
            if a not in rank:
                continue
            note = f"part {i} ({lo if lo == hi else lo + ' to ' + hi}), player {pid}, turn {turn}: {legacy}"
            if rank[a] > rank.get(hi, 2):
                fails.append(note)
            elif rank[a] > rank.get(lo, 2):
                unsure.append(note)
        lines.append(f"| {i} | {lo if lo == hi else lo + ' to ' + hi} | {len(part)} | "
                     f"{', '.join(f'{a} {n}' for a, n in sorted(ages.items()))} |")
    if not parts:
        lines.append("| - | - | 0 | - |")
    lines.append("")
    lines += [f"- LEGACY FAIL: a legacy of a later age than its world, {n}" for n in fails[:20]]
    lines += [f"- not judged (the part of the log may be a later world): {n}" for n in unsure[:20]]
    return lines + ([""] if fails or unsure else []), bool(fails)


def production_by_world(qfile: Path, base: int = 0) -> list[str]:
    """Items started in production, per world age (the turn number restarts in each age),
    grouped by the item's native age. Shows whether a civ can still use earlier-age content."""
    worlds = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
    native = native_ages()
    seg, last_turn, started = 0, 0, {}
    for row in csv.reader(qfile.open(encoding="utf-8", errors="replace")):
        if len(row) < 5 or not row[0].strip().isdigit():
            continue
        turn = int(row[0])
        if turn < last_turn:
            seg += 1
        last_turn = turn
        key = (seg, row[1].strip(), row[2].strip(), row[4].strip())
        started.setdefault(key, turn)
    counts = {}
    for (sg, _, _, item) in started:
        w = worlds[min(base + sg, 2)]  # base: the world of the first record (a run from a save)
        counts.setdefault(w, {}).setdefault(native.get(item, "unknown"), set()).add(item)
    out = ["| World age | Native age of item | Distinct items | Examples |", "| --- | --- | --- | --- |"]
    for w in worlds:
        for a in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN", "common", "unknown"):
            items = sorted(counts.get(w, {}).get(a, ()))
            if items:
                out.append(f"| {w} | {a} | {len(items)} | {', '.join(items[:6])} |")
    return out


def log_lines(pattern: str) -> list[str]:
    rx = re.compile(pattern)
    out = []
    for f in sorted(LOGS.glob("*.log")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if rx.search(line):
                out.append(f"{f.name}: {line.strip()}")
    return out


_CIV_UNITS = None


_LEGACY_UNITS = None


def legacy_unique_units() -> set:
    """Unique unit types (without UNIT_) of the legacy civs (LegacyCivilizationTraits): the units a civ
    that keeps its civ can build through its legacy civ's traits (U-TOT-SHADOW)."""
    global _LEGACY_UNITS
    if _LEGACY_UNITS is None:
        _LEGACY_UNITS = set()
        # Antiquity too: a civ of a later age played from the start (Time-Tested) has the Antiquity Test of
        # Time tree, and its Syncretism gives an Antiquity legacy civ (iteration 20261031-125020: Inca took
        # Mississippian, and 4 Burning Arrows came back as Archers plus 4 new units at the load).
        for w in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"):
            sim = c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True)
            _LEGACY_UNITS |= {u.replace("UNIT_", "") for (u,) in sim.db.execute(
                "SELECT UnitType FROM Units WHERE TraitType IN (SELECT TraitType FROM LegacyCivilizationTraits)")}
    return _LEGACY_UNITS


def civ_unique_units(civ: str | None) -> set:
    """Unique unit types (without UNIT_) of a civ, by its short name (as the PLAYER record writes it)."""
    global _CIV_UNITS
    if _CIV_UNITS is None:
        _CIV_UNITS = {}
        for w in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"):
            sim = c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True)
            trait_civ = {}
            for trait, cv in sim.db.execute("SELECT TraitType, CivilizationType FROM CivilizationTraits"):
                trait_civ.setdefault(trait, set()).add(cv.replace("CIVILIZATION_", ""))
            for unit, trait in sim.db.execute("SELECT UnitType, TraitType FROM Units WHERE TraitType IS NOT NULL"):
                for cv in trait_civ.get(trait, ()):
                    _CIV_UNITS.setdefault(cv, set()).add(unit.replace("UNIT_", ""))
    return _CIV_UNITS.get(civ or "", set())


_CIV_AGES = None


def civ_ages():
    """Civ type -> its age (LegacyCivilizations, all worlds with DLC)."""
    global _CIV_AGES
    if _CIV_AGES is None:
        _CIV_AGES = {}
        for w in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"):
            sim = c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True)
            _CIV_AGES.update(dict(sim.db.execute("SELECT CivilizationType, Age FROM LegacyCivilizations")))
    return _CIV_AGES


_UNIT_CLASSES = None


def unit_classes():
    """Unit type -> its shadow class tag (from the tags of all worlds: the Antiquity data has only
    the civilian and recon ones), and unit type -> core class."""
    global _UNIT_CLASSES
    if _UNIT_CLASSES is None:
        sims = [c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True) for w in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN")]
        shadow_tags = {r[0] for sim in sims for r in sim.db.execute("SELECT Tag FROM Unit_ShadowReplacements")}
        class_of, core_of = {}, {}
        for sim in sims:
            core_of.update(dict(sim.db.execute("SELECT UnitType, CoreClass FROM Units")))
            for typ, tag in sim.db.execute("SELECT Type, Tag FROM TypeTags ORDER BY Tag"):
                if tag in shadow_tags:
                    class_of.setdefault(typ, tag)
        _UNIT_CLASSES = (class_of, core_of)
    return _UNIT_CLASSES


def analyze(start: datetime, autoplay_out: str, workdir: Path, expect_transitions: int | None = None) -> tuple[bool, list[str]]:
    lines, failed = [], False
    # Automation result
    results = log_lines(r"\[PASS\]|\[FAIL\]|Autoplay Turn Limit Hit")
    lines += ["## Automation", ""] + [f"- {r}" for r in results] + [""]
    if not any("[PASS]" in r for r in results) or any("[FAIL]" in r for r in results):
        failed = True
    # The runner closes a game whose logs stop (run_autoplay.ps1 -StallMinutes) or that runs past the timeout.
    for l in autoplay_out.splitlines():
        if l.startswith("HANG:") or "Timed out: True" in l:
            failed = True
            lines += [f"- HANG FAIL: {l.strip()}" if l.startswith("HANG:") else f"- TIMEOUT FAIL: {l.strip()}", ""]
    # Speed: seconds per turn, from the turn-start times in the network log
    stamps = []
    net = LOGS / "net_message_debug.log"
    if net.exists():
        for line in net.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]\s+Game Turn: (\d+)", line)
            if m:
                stamps.append((int(m.group(2)), datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")))
    if len(stamps) > 1:
        # The turn counter restarts in each age: add the turns and the time of each age.
        turns, seconds, ages = 0, 0.0, 1
        for (ta, sa), (tb, sb) in zip(stamps, stamps[1:]):
            if tb > ta:
                turns += tb - ta
                seconds += (sb - sa).total_seconds()
            elif tb < ta:
                ages += 1
        lines += ["## Speed", "", f"- {turns} turns in {ages} age(s): {seconds / max(1, turns):.1f} seconds per turn "
                  "on average (age transitions not included)", ""]
    # Crash dumps
    dumps = [p for d in DUMP_DIRS if d.exists() for p in d.rglob("*")
             if p.is_file() and p.stat().st_mtime > start.timestamp()  # epoch: safe across a daylight saving change
             and ("Civ7" in p.name or p.name == "submission.pkg")]
    game_pid = re.search(r"^Game process: (\d+)", autoplay_out, re.M)
    if WORKER and game_pid and REAL_CRASHDUMPS.exists():
        dumps += [p for p in REAL_CRASHDUMPS.glob(f"Civ7*.{game_pid.group(1)}.dmp") if p.stat().st_mtime > start.timestamp()]
    lines += ["## Crashes", ""]
    for d in dumps:
        lines.append(f"- {d}")
        if TOOLS_PY.exists() and d.suffix.lower() in (".dmp", ".pkg"):
            res = run([str(TOOLS_PY), str(HERE / "tools" / "crashstack.py"), str(d)])
            out = (res.stdout + res.stderr).strip()
            lines += ["", "```", out[:6000], "```"]
            # The audio engine thread can crash while the application exits (seen after a clean
            # "Logging Shutdown"). Report it, but it is not a failure of the game under test.
            if "EXIT CRASH (audio thread)" in out:
                lines.append("- exit crash in the audio thread after shutdown: reported, not counted as a failure")
                continue
        failed = True
    if not dumps:
        lines.append("- none")
    lines.append("")
    # Database and mod errors
    db_errors = [l for l in log_lines(r"(?i)error|fail") if l.startswith(("Database.log", "Modding.log"))
                 and "StartupErrorMessages" not in l]
    # Script errors in the mod's transition script (Scripting.log, after its "loaded" line), and the
    # mod's own error records ([CA] ... errors are written with console.log there).
    script = LOGS / "Scripting.log"
    if script.exists() and script.stat().st_mtime >= start.timestamp():
        loaded = False
        for l in script.read_text(encoding="utf-8", errors="replace").splitlines():
            if "[CA] continuous transition script loaded" in l:
                loaded = True
            elif loaded and re.search(r"JS Error|TypeError|ReferenceError|RangeError|SyntaxError|\[CA\].*error", l):
                db_errors.append(f"Scripting.log: {l.strip()}")
    lines += ["## Database and mod errors", ""] + ([f"- {l}" for l in db_errors[:40]] or ["- none"]) + [""]
    if db_errors:
        failed = True
    # In-game checks
    checks = log_lines(r"\[CA-CHECK\]")
    fails = [l for l in checks if "[CA-CHECK][FAIL]" in l or "[CA-CHECK][ERROR]" in l]
    snaps = [l for l in checks if "[CA-CHECK][SNAPSHOT]" in l]
    lines += ["## In-game checks", "", f"- loaded: {any('checks loaded' in l for l in checks)}",
              f"- snapshots: {len(snaps)}", f"- failures: {len(fails)}"]
    lines += [f"  - {l}" for l in fails[:30]]
    if fails or not snaps:
        failed = True
    def records(kind):
        out = []
        for l in checks:
            if f"[CA-CHECK][{kind}] " in l:
                try:
                    out.append(json.loads(l.split(f"[CA-CHECK][{kind}] ", 1)[1], strict=False))
                except json.JSONDecodeError:
                    pass  # a line cut by the log
        return out
    snap_recs, players, builds = records("SNAPSHOT"), records("PLAYER"), records("BUILD")
    probe = {}
    if snap_recs:
        last = snap_recs[-1]
        max_ocean, max_build, probe = {}, {}, {}
        for p in players:
            max_ocean[p["id"]] = max(max_ocean.get(p["id"], 0), p["unitsOnOcean"])
            max_build[p["id"]] = max(max_build.get(p["id"], 0), p["exBuildings"])
            pr = p.get("oceanProbe")
            if pr and pr["probed"]:
                key = "past gate" if p["gate"] else "before gate"
                s = probe.setdefault((p["id"], key), [0, 0])
                s[0] += pr["probed"]
                s[1] += pr["allowed"]
        lines += ["", f"Last snapshot (turn {last['turn']}, age {last['age']}, "
                      f"age progress {last['ageProgress']}/{last['ageMax']}):", "",
                  "| Player | Civ | Civ age | Ocean tech | EX techs | EX buildings (max in run) | "
                  "Units on ocean (max in run) | Government |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for p in (p for p in players if p["turn"] == last["turn"] and p.get("age") == last["age"]):
            lines.append(f"| {p['id']} | {p['civ']} | {p.get('civAge', p['gate'])} | {p['oceanTech']} | {p['exTechs']} | "
                         f"{p['exBuildings']} ({max_build[p['id']]}) {p['exBuildingTypes']} | "
                         f"{p['unitsOnOcean']} ({max_ocean[p['id']]}) | {p['gov']} |")
    # Age transitions: each civ's state at the age end against the first check of the next age.
    ends, states = records("AGEEND"), records("STATE")
    transitions = records("TRANSITION")
    lines += ["", "## Age transitions", "", f"- transitions started: {len(transitions)} "
              + ", ".join(f"{t['from']} (turn {t['turn']})" for t in transitions)]
    # Gold after each reload, before any civ plays (written by the transition script, one batch per transition).
    reload_batches, cur = [], {}
    for r in records("RELOAD"):
        if r["id"] in cur:
            reload_batches.append(cur)
            cur = {}
        cur[r["id"]] = r
    if cur:
        reload_batches.append(cur)
    res_batches = reload_resource_batches()
    slots, unseen = reload_slots(transitions, res_batches, len(reload_batches))
    for age in unseen:
        # The transition script ran (a reload batch), but the test's age-end handler did not: the game started
        # the transition before the UI handled GameAgeEnded. Counted as a transition; its age-end checks cannot run.
        lines.append(f"- KNOWN LIMIT (U-AGEEND-MISSED): the transition into {age} has its reload records but no "
                     f"TRANSITION or AGEEND record (the test's GameAgeEnded handler did not run); its age-end checks could not run")
    count_lines, count_failed = transition_count_report(transitions + [{"from": None}] * len(unseen), expect_transitions)
    lines += count_lines
    failed |= count_failed
    order = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
    tree_of = civic_trees() if transitions else {}
    civ_nodes = {}
    for r in records("CIVICS"):
        civ_nodes.setdefault((r["when"], r["age"], r["id"]), []).extend(r["nodes"])
    policies = {}
    for r in records("POLICIES"):
        policies.setdefault((r["when"], r["age"], r["id"]), []).extend(r["types"])
    unit_lists = {}
    for r in records("UNITS"):
        unit_lists.setdefault((r["when"], r["age"], r["id"]), []).extend(r["types"])
    # Discoveries of any age (Ruins are a discovery until the Modern data makes them archaeology sites).
    discoveries = set()
    if transitions:
        for age in order:
            sim = c.simulate(c.DEFAULT_GAME_DIR, age, include_dlc=True)
            discoveries |= {r[0].replace("IMPROVEMENT_", "") for r in sim.db.execute(
                "SELECT ConstructibleType FROM Constructibles WHERE Discovery = 1")}
    need_cache = {}
    cons = {}
    for r in records("CONS"):
        cons.setdefault((r["when"], r["age"], r["id"]), []).extend(r["types"])
    def type_batches(kind):
        """Per transition: player -> {types, source}; a new batch starts when a player's part 0 repeats."""
        out, cur = [], {}
        for r in records(kind):
            if r.get("part", 0) == 0 and r["id"] in cur:
                out.append(cur)
                cur = {}
            cur.setdefault(r["id"], {"types": [], "source": r.get("source")})["types"].extend(r["types"])
        if cur:
            out.append(cur)
        return out
    reload_units, reload_cons = type_batches("RELOADUNITS"), type_batches("RELOADCONS")
    # The last OPTIONS record: the first one is written before the test applies CATransitionSetting.
    transition_setting = ([r.get("transition") for r in records("OPTIONS") if r.get("transition")] or [None])[-1]
    keys = ["gold", "cities", "towns", "units", "techs", "civics", "traditions", "policies", "cap", "pop", "buildings", "promotions", "levels", "sci", "cul"]
    load_gifts = {}  # player -> policies the engine gave at the previous load (U-POLICY-LOAD)
    # Rule 5e: CA_GATE_ ability modifiers per civ after each reload (transition script, GATEMODS).
    gate_mods, cur = [], {}
    for r in records("GATEMODS"):
        if r["id"] in cur:
            gate_mods.append(cur)
            cur = {}
        cur[r["id"]] = r.get("counts", {})
    if cur:
        gate_mods.append(cur)
    civ_choices = records("CIVCHOICE")
    civ_mode = (records("CIVMODE") or [{}])[-1].get("mode")  # a game option: the same at every age end
    def civ_choices_world(w):
        return any(r.get("world") == w for r in civ_choices)
    if civ_choices and civ_mode not in ("AGE_TRANSITION_CIV_SELECTION_MODE_MIRRORING", "AGE_TRANSITION_CIV_SELECTION_MODE_PERSISTENCE",
                                         "AGE_TRANSITION_CIV_SELECTION_MODE_SWITCHING", "AGE_TRANSITION_CIV_SELECTION_MODE_RANDOM"):
        failed = True
        lines.append(f"- CIV CHOICE FAIL: unknown AI civ choice mode {civ_mode}")
    for ti, t in enumerate(transitions):
        if t["from"] == order[-1]:
            continue  # the game ends after the last age
        si = slots[ti]  # this transition's reload batch (reload_slots)
        reload = reload_batches[si] if si is not None and si < len(reload_batches) else {}
        nxt = order[order.index(t["from"]) + 1]
        before = {e["id"]: e for e in ends if e["age"] == t["from"]}
        after = {}
        for st in states:
            if st.get("age") == nxt and (st["id"] not in after or st["turn"] < after[st["id"]]["turn"]):
                after[st["id"]] = st
        if not after:
            lines.append(f"- {t['from']} -> {nxt}: no check records in the new age")
            failed = True
            continue
        lines += ["", f"{t['from']} -> {nxt} (age end against the first turn checked in the new age):", "",
                  "| Player | Civ age | " + " | ".join(keys) + " |", "| --- | --- | " + " | ".join("---" for _ in keys) + " |"]
        for pid in sorted(before):
            b, a = before[pid], after.get(pid)
            if a is None:
                lines.append(f"| {pid} | {b.get('civAge')} | (no record in the new age) |")
                continue
            lines.append(f"| {pid} | {b.get('civAge')} -> {a.get('civAge')} (turn {a['turn']}) | "
                         + " | ".join(f"{b.get(k)} -> {a.get(k)}" for k in keys) + " |")
            # Civ choice (ui/ca-civ-age.js): a civ behind the new age's gate keeps its civ; a civ past it
            # takes a new civ. Checked when the age end has a CIVCHOICE record for the civ.
            choice = next((r for r in reversed(civ_choices) if r.get("world") == t["from"] and r.get("id") == pid), None)
            civ_b = next((p.get("civ") for p in reversed(players) if p.get("age") == t["from"] and p.get("id") == pid), None)
            civ_a = next((p.get("civ") for p in players if p.get("age") == nxt and p.get("id") == pid), None)
            if civ_choices_world(t["from"]) and not choice:
                failed = True
                lines.append(f"  - CIV CHOICE FAIL: no CIVCHOICE record at the age end for player {pid}")
            if choice and civ_b and not civ_a:
                lines.append(f"  - civ choice: {civ_b} -> (no PLAYER record in the new age)")
            if choice and civ_b and civ_a and civ_a != civ_b and civ_ages().get("CIVILIZATION_" + civ_a) != nxt:
                failed = True
                lines.append(f"  - CIV CHOICE FAIL: {civ_b} -> {civ_a}, a civ of {civ_ages().get('CIVILIZATION_' + civ_a)} in the {nxt} world")
            if choice and civ_b and civ_a:
                # The game's mode decides (no per-civ choice exists): Persistence keeps every AI civ,
                # Switching changes every AI civ; Mirroring and Random have no fixed result.
                kept = civ_a == civ_b
                want = {"AGE_TRANSITION_CIV_SELECTION_MODE_PERSISTENCE": True,
                        "AGE_TRANSITION_CIV_SELECTION_MODE_SWITCHING": False}.get(civ_mode)
                note = f"{civ_b} -> {civ_a} (civ age {b.get('civAge')}, {'behind' if choice.get('behind') else 'past'} the gate, mode {civ_mode})"
                if want is not None and kept != want and not choice.get("human"):
                    failed = True
                    lines.append(f"  - CIV CHOICE FAIL: {note}")
                elif choice.get("behind") and not kept:
                    lines.append(f"  - KNOWN LIMIT (half swap): {note}")
                else:
                    lines.append(f"  - civ choice: {note}")
            gm = (gate_mods[si] if si is not None and si < len(gate_mods) else {}).get(pid)
            if gm is not None:
                n, act = (gm.get("CA_GATE_") or [0, 0])
                # The civ's abilities wait for the gate of the civ's own age, not the world's: an Exploration civ
                # kept into the Modern world (a Time-Tested start, iteration 20261031-121009: Mongolia, civ age
                # EX) rightly has its Exploration abilities.
                own = civ_ages().get("CIVILIZATION_" + civ_a) if civ_a else None
                behind = {"AQ": 0, "EX": 1, "MO": 2}.get(b.get("civAge"), 0) < order.index(own if own in order else nxt)
                if behind and act:
                    failed = True
                    lines.append(f"  - ABILITY LEAK FAIL: {act} of {n} later-age civ ability modifiers active before the civ's gate")
                else:
                    lines.append(f"  - civ abilities (rule 5e): {act} of {n} gated modifiers active ({'behind' if behind else 'past'} the gate)")
            if pid not in reload:
                # The transition script writes one RELOAD record per civ; none means it failed for this civ.
                failed = True
                lines.append(f"  - TRANSITION FAIL: no RELOAD record for player {pid}")
            if pid in reload:
                lines.append(f"  - gold: {b['gold']} at the age end, {reload[pid]['gold']} after the reload, "
                             f"{a['gold']} at the first check")
                lines.append(f"  - units: {b['units']} at the age end, {reload[pid].get('units')} after the reload "
                             f"(shadows: {reload[pid].get('shadows')}), {a['units']} at the first check")
            # Unit and constructible types after the reload (before any civ plays). Without them, the first
            # check (after each civ's first turn) is used, and the report says so.
            r_units = reload_units[si].get(pid) if si is not None and si < len(reload_units) else None
            r_cons = reload_cons[si].get(pid) if si is not None and si < len(reload_cons) else None
            ub = unit_lists.get(("end", t["from"], pid))
            ua = r_units["types"] if r_units else unit_lists.get(("start", nxt, pid))
            when = "after the reload" if r_units else "at the first check (no reload record)"
            if ub is not None and ua is not None:
                class_of, core_of = unit_classes()
                # Every unit is kept, so the military units by class must match. Allowed: one naval unit
                # more at the Exploration world (the free ship of a civ past its gate).
                def mil(types):
                    return _C(class_of.get("UNIT_" + u, "none") for u in types if core_of.get("UNIT_" + u) == "CORE_CLASS_MILITARY")
                # The engine converts a removed civ's unique unit to its base type (UnitReplaces, for
                # example Keshig -> Heavy Archer); a unique unit can carry several class tags, so compare
                # it as its base type (iteration 20261025-012845).
                if "replaces" not in need_cache:
                    need_cache["replaces"] = {}
                    for w in order:
                        sim = c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True)
                        need_cache["replaces"].update(dict(sim.db.execute(
                            "SELECT CivUniqueUnitType, ReplacesUnitType FROM UnitReplaces")))
                gone0, new0 = _C(ub) - _C(ua), _C(ua) - _C(ub)
                ub_as = list(ub)
                # Only with reload records: at the first check a unit built in turn 1 could pass for a
                # conversion and hide a real loss (gotcha checker review 4).
                for u, n in (gone0.items() if r_units else []):
                    base = need_cache["replaces"].get("UNIT_" + u, "").replace("UNIT_", "")
                    k = min(n, new0.get(base, 0))
                    for _ in range(k):
                        ub_as[ub_as.index(u)] = base
                    if k:
                        new0[base] -= k
                end_tags, now_tags = mil(ub_as), mil(ua)
                more, fewer = dict(now_tags - end_tags), dict(end_tags - now_tags)
                if nxt == "AGE_EXPLORATION" and more.get("UNIT_CLASS_NAVAL") == 1:
                    del more["UNIT_CLASS_NAVAL"]
                # Known limit (U-SHADOW-CLASS): the shadow of a removed unique unit does not carry its class,
                # so a unit made from a leftover shadow can have another class (iteration 20261025-005832:
                # Medjay -> Catapult). At most as many swaps as units made from shadows, totals equal.
                made = ((reload.get(pid) or {}).get("shadows") or {}).get("made", 0) if r_units else 0
                swaps = sum(more.values())
                if more and swaps == sum(fewer.values()) and swaps <= made:
                    lines.append(f"  - KNOWN LIMIT (U-SHADOW-CLASS): units made from leftover shadows with another class: "
                                 f"{dict(fewer)} -> {dict(more)}")
                    more, fewer = {}, {}
                # Known limit (U-TOT-SHADOW, docs/known-limits.md): a civ that keeps its civ can adopt a legacy
                # civ (Syncretism) and build its unique units; at the load the engine converts or removes them, and
                # their extra shadows make units (iterations 20261029-150344, 152811). Only for such a civ, and
                # at most as many units off, each way, as legacy unique units gone.
                legacy_gone = sum(n for u, n in gone0.items() if u in legacy_unique_units()) if r_units else 0
                if ((more or fewer) and civ_a and civ_a == civ_b and legacy_gone
                        and sum(more.values()) <= legacy_gone and sum(fewer.values()) <= legacy_gone):
                    lines.append(f"  - KNOWN LIMIT (U-TOT-SHADOW): {legacy_gone} legacy-civ unique units gone, "
                                 f"units off by class: more {dict(more)}, fewer {dict(fewer)}")
                    more, fewer = {}, {}
                # Known limit (U-DLC-EARLIER, docs/known-limits.md): a DLC civ's unique units of an earlier age are
                # not in the later worlds' data. At a civ change the game converts or removes them, and the shadow
                # step does not see them as unique, so units come back extra (iteration 20261031-152452: Bulgaria
                # to Prussia, 7 Boyars, 5 extra units; 121009). Only for a civ that changed, and at most as many
                # units off, each way, as such units gone.
                if (more or fewer) and r_units and civ_a and civ_b and civ_a != civ_b:
                    absent = {u for u in civ_unique_units(civ_b) if "UNIT_" + u not in world_unit_types(nxt)}
                    dlc_gone = sum(n for u, n in gone0.items() if u in absent)
                    if dlc_gone and sum(more.values()) <= dlc_gone and sum(fewer.values()) <= dlc_gone:
                        lines.append(f"  - KNOWN LIMIT (U-DLC-EARLIER): {dlc_gone} unique units of {civ_b} not in the "
                                     f"{nxt} data gone, units off by class: more {dict(more)}, fewer {dict(fewer)}")
                        more, fewer = {}, {}
                if more:
                    failed = True
                    lines.append(f"  - DUPLICATE FAIL: military units more {when}, by class: {more}")
                if fewer:
                    failed = True
                    lines.append(f"  - LOST UNITS FAIL: military units fewer {when}, by class: {fewer}")
                if not more and not fewer:
                    lines.append(f"  - military units by class: same at the age end and {when} ({sum(end_tags.values())})")
                lost_u, new_u = _C(ub) - _C(ua), _C(ua) - _C(ub)
                if lost_u:
                    lines.append(f"  - units gone {when}: {dict(lost_u)}")
                # Civilian and support units by type too. Known limit (U-GREAT-PERSON): the engine removes
                # every great person at each load (TypeTags UNIT_CLASS_GREATPERSON; Unit_TransitionRetains keeps
                # commanders only): Egypt's Tjaty (iterations 20261025-012715, 012845, 010211), Pizarro and
                # Cortes (20261031-153836, 155019), Alim al-Shaybani for a civ that kept its civ (155901).
                # Not a loss: a base unit converted to the new civ's unique version (Army Commander -> Soltan).
                converted_from = _C()
                for v, n in new_u.items():
                    base = need_cache["replaces"].get("UNIT_" + v, "").replace("UNIT_", "")
                    if base:
                        converted_from[base] += n
                lost_civil = {u: n - converted_from.get(u, 0) for u, n in lost_u.items()
                              if core_of.get("UNIT_" + u) != "CORE_CLASS_MILITARY"
                              and need_cache["replaces"].get("UNIT_" + u, "").replace("UNIT_", "") not in new_u
                              and n - converted_from.get(u, 0) > 0}
                # U-CRISIS-UNIT: crisis units (plague Physicians) end with the world age's crisis.
                # U-UNIQUE-COMMANDER: the engine sometimes removes the previous civ's unique commander without
                # converting it to the base commander, with both transition settings (iterations
                # 20261025-020933 and 023852: Noyan, with its promotion; in others it became an Army Commander).
                commanders = {"ARMY_COMMANDER", "FLEET_COMMANDER", "AERODROME_COMMANDER", "SQUADRON_COMMANDER"}
                if "great_people" not in need_cache:
                    need_cache["great_people"] = set()
                    for w in order:
                        sim = c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True)
                        need_cache["great_people"] |= {t.replace("UNIT_", "", 1) for (t,) in sim.db.execute(
                            "SELECT Type FROM TypeTags WHERE Tag = 'UNIT_CLASS_GREATPERSON'")}
                known_civil = {u: n for u, n in lost_civil.items() if u in need_cache["great_people"] or u == "PHYSICIAN"
                               or need_cache["replaces"].get("UNIT_" + u, "").replace("UNIT_", "") in commanders}
                rest_civil = {u: n for u, n in lost_civil.items() if u not in known_civil}
                if known_civil:
                    lines.append(f"  - KNOWN LIMIT (U-GREAT-PERSON, U-CRISIS-UNIT, U-UNIQUE-COMMANDER): removed {when}: {known_civil}")
                if rest_civil and r_units:
                    failed = True
                    lines.append(f"  - LOST UNITS FAIL: civilian or support units gone {when}: {rest_civil}")
                elif rest_civil:
                    lines.append(f"  - civilian or support units gone {when} (turn 1 included, not judged): {rest_civil}")
                if new_u:
                    lines.append(f"  - units new {when}: {dict(new_u)}")
                    # Units the transition made count as leaks too, when the civ has not reached their age:
                    # the production log does not show them.
                    if nxt not in need_cache:
                        need_cache[nxt] = required_ages(nxt)
                    early = {u: n for u, n in new_u.items()
                             if too_early(need_cache[nxt].get("UNIT_" + u), a.get("civAge"), a.get("civicAge"))}
                    # The engine converts a kept unit to the new civ's unique version (UnitReplaces), for
                    # example Army Commander -> Soltan: a known limit of the world-transition swap (U2/U3).
                    if early:
                        if "replaces" not in need_cache:
                            need_cache["replaces"] = {}
                            for w in order:
                                sim = c.simulate(c.DEFAULT_GAME_DIR, w, include_dlc=True)
                                need_cache["replaces"].update(dict(sim.db.execute(
                                    "SELECT CivUniqueUnitType, ReplacesUnitType FROM UnitReplaces")))
                        left = _C(lost_u)
                        converted = {}
                        # Rule 2i removes the replace rows of its gap pairs, so the engine must not convert a kept base
                        # unit to such a unique unit: a conversion there stays a leak (FAIL), not this known limit.
                        if "gap_uus" not in need_cache:
                            m_ = re.search(r"const CA_REPLACE_GAPS = (\[.*?\]);", (MOD_DIR / "ui" / "ca-checks.js").read_text(encoding="utf-8"))
                            need_cache["gap_uus"] = {g[0].replace("UNIT_", "") for g in (json.loads(m_.group(1)) if m_ else [])}
                        for u in list(early):
                            if u in need_cache["gap_uus"]:
                                continue
                            base = need_cache["replaces"].get("UNIT_" + u, "").replace("UNIT_", "")
                            if not base:
                                continue
                            # The kept unit is the base unit, or the previous civ's unique version of it (Noyan ->
                            # Soltan: both replace the Army Commander, iteration 20261031-214228).
                            for src in [base] + [l for l in left if l != base and left[l] > 0 and
                                                 need_cache["replaces"].get("UNIT_" + l, "").replace("UNIT_", "") == base]:
                                k = min(early[u], left.get(src, 0))
                                if k:
                                    converted[f"{src} -> {u}"] = converted.get(f"{src} -> {u}", 0) + k
                                    left[src] -= k
                                    early[u] -= k
                                if not early[u]:
                                    del early[u]
                                    break
                        if converted:
                            lines.append(f"  - KNOWN LIMIT: the engine converted kept units to the new civ's unique units "
                                         f"(civ age {a.get('civAge')}): {converted}")
                    if early:
                        failed = True
                        lines.append(f"  - LEAK FAIL: the transition gave units of a later age (civ age {a.get('civAge')}): {early}")
            # The first turn after the reload (age-start grants, AI builds, buys and losses), listed; units
            # of a later age than the civ's are leaks there too (for example a free Cog for a civ still in
            # Antiquity; gotcha checker review 4).
            us = unit_lists.get(("start", nxt, pid))
            if r_units and us is not None:
                t1_new, t1_gone = _C(us) - _C(r_units["types"]), _C(r_units["types"]) - _C(us)
                if t1_new or t1_gone:
                    lines.append(f"  - units in the first turn after the reload: new {dict(t1_new)}, gone {dict(t1_gone)}")
                if t1_new:
                    if nxt not in need_cache:
                        need_cache[nxt] = required_ages(nxt)
                    early1 = {u: n for u, n in t1_new.items()
                              if too_early(need_cache[nxt].get("UNIT_" + u), a.get("civAge"), a.get("civicAge"))}
                    # Known limit (half swap, U2): a civ that takes a new civ at the world transition gets that
                    # civ's age-start unique units in its first turn (Norman: 2 Sokemen; iterations
                    # 20261025-011516, 014531), even when it is behind its gate.
                    civ_now = next((p.get("civ") for p in players if p.get("age") == nxt and p.get("id") == pid), None)
                    own = civ_unique_units(civ_now)
                    half = {u: n for u, n in early1.items() if u in own}
                    early1 = {u: n for u, n in early1.items() if u not in own}
                    if half:
                        lines.append(f"  - KNOWN LIMIT (half swap): the new civ's age-start unique units in the first turn "
                                     f"(civ age {a.get('civAge')}, civ {civ_now}): {half}")
                    if early1:
                        failed = True
                        lines.append(f"  - LEAK FAIL: units of a later age in the first turn (civ age {a.get('civAge')}): {early1}")
            cons_b, cons_a = cons.get(("end", t["from"], pid)), cons.get(("start", nxt, pid))
            if cons_b is not None and r_cons is not None and r_cons.get("source") == "city":
                # By type at the reload; changes after it (turn 1: overbuild, war) are listed only.
                lost_c = _C(cons_b) - _C(r_cons["types"])
                for k in [k for k in lost_c if k in discoveries]:
                    del lost_c[k]  # discoveries are a world system, made again for each age
                if lost_c:
                    failed = True
                    lines.append(f"  - CONTINUITY FAIL: constructibles gone at the reload: {dict(lost_c)}")
                new_c = _C(r_cons["types"]) - _C(cons_b)
                if new_c:
                    lines.append(f"  - constructibles new at the reload: {dict(new_c)}")
                if cons_a is not None:
                    later = _C(r_cons["types"]) - _C(cons_a)
                    if later:
                        lines.append(f"  - constructibles gone in the first turn after the reload (AI overbuild or war): {dict(later)}")
            elif cons_b is not None and cons_a is not None:
                lost_c, new_c = _C(cons_b) - _C(cons_a), _C(cons_a) - _C(cons_b)
                for k in [k for k in lost_c if k in discoveries]:
                    del lost_c[k]
                if lost_c:
                    failed = True
                    lines.append(f"  - CONTINUITY FAIL: constructibles gone at the first check (no reload type record): {dict(lost_c)}")
                if new_c:
                    lines.append(f"  - constructibles new at the first check: {dict(new_c)}")
            gone = sorted(set(b.get("trees", [])) - set(a.get("trees", [])))
            if gone:
                lines.append(f"  - civic trees no longer available: {', '.join(gone)}")
            # Known engine limits (U-EGYPT, U-POLICY in the design doc), listed but not counted. Named
            # exactly, so any other lost civic or policy still fails the run.
            known_lost_tree = "AQ_EGYPT"
            if a.get("traditions") is not None and b.get("traditions") is not None and a["traditions"] < b["traditions"]:
                failed = True
                lines.append(f"  - CONTINUITY FAIL: player {pid} traditions {b['traditions']} -> {a['traditions']}")
            # Policies by name (a count hides a loss when new policies appear). Rule 5c unlocks every
            # main-tree policy again, so a lost policy fails, except the base game's upgrade: its successor
            # (Traditions.ObsoletesTraditionType, transitive) was held at the age end.
            pol_b, pol_a = policies.get(("end", t["from"], pid)), policies.get(("start", nxt, pid))
            if pol_b is not None and pol_a is not None:
                if "obsoletes" not in need_cache:
                    sim = c.simulate(c.DEFAULT_GAME_DIR, "AGE_MODERN", include_dlc=True)
                    need_cache["obsoletes"] = {}
                    for new_t, old_t in sim.db.execute("SELECT TraditionType, ObsoletesTraditionType FROM Traditions "
                                                       "WHERE ObsoletesTraditionType IS NOT NULL"):
                        need_cache["obsoletes"].setdefault(old_t.replace("TRADITION_", ""), set()).add(new_t.replace("TRADITION_", ""))
                lost_p = sorted(set(pol_b) - set(pol_a))
                def successors(x, seen=None):
                    seen = set() if seen is None else seen
                    for n in need_cache["obsoletes"].get(x, set()) - seen:
                        seen.add(n)
                        successors(n, seen)
                    return seen
                upgraded = [x for x in lost_p if successors(x) & set(pol_b)]
                # Known limit (U-POLICY-LOAD): at the Modern load the engine gives every civ the Exploration
                # main-tree policies, earned or not (Bourgeoisie, Commune, Constitution, Divine Right,
                # Levies, Metropole, Yeomanry), and Levies and Divine Right then replace Conscription and
                # Oratory. Named exactly; a successor counts only when it came at this load.
                gained_now = set(pol_a) - set(pol_b)
                load_pairs = {"CONSCRIPTION": "LEVIES", "ORATORY": "DIVINE_RIGHT"}
                load_known = [x for x in lost_p if x not in upgraded and nxt == "AGE_MODERN"
                              and load_pairs.get(x) in gained_now]
                # The other side of the same engine grant: a policy given free at the previous load, whose
                # civic the civ never completed, goes away at the next load (Earth run 20261025-030928 with
                # 30-point ages: Castes and Rites and Rituals). Rule 5c keeps only earned policies.
                load_known += [x for x in lost_p if x not in upgraded and x not in load_known
                               and x in load_gifts.get(pid, set())]
                rest = [x for x in lost_p if x not in upgraded and x not in load_known]
                if upgraded:
                    lines.append(f"  - policies replaced by successors held at the age end (base upgrade): {', '.join(upgraded)}")
                if load_known:
                    lines.append(f"  - KNOWN LIMIT (U-POLICY-LOAD): player {pid} lost {', '.join(load_known)} "
                                 f"(replaced by a policy given at this load, or given free at the previous load)")
                if rest:
                    failed = True
                    lines.append(f"  - CONTINUITY FAIL: player {pid} lost policies {', '.join(rest)}")
                gained = sorted(set(pol_a) - set(pol_b))
                load_gifts[pid] = set(gained)
                if gained:
                    lines.append(f"  - policies new at the load: {', '.join(gained)}")
            elif a.get("policies") is not None and b.get("policies") is not None and a["policies"] < b["policies"]:
                failed = True
                lines.append(f"  - CONTINUITY FAIL: player {pid} policies {b['policies']} -> {a['policies']} (no names recorded)")
            # Continuity (design rule: no reset). Completed techs and civics must not be lost.
            if a["techs"] < b["techs"]:
                failed = True
                lines.append(f"  - CONTINUITY FAIL: player {pid} techs {b['techs']} -> {a['techs']}")
            # Civics: a node counts as lost only if its tree is still available. The engine gives each
            # player the trees of its current civ and age (as in the base game); a tree the player no
            # longer has shows its nodes as not unlocked, and the traditions it gave stay.
            kept_trees = set(a.get("trees", []))
            nodes_b = civ_nodes.get(("end", t["from"], pid), b.get("civicNodes", []))
            nodes_a = civ_nodes.get(("start", nxt, pid), a.get("civicNodes", []))
            lost = sorted(set(nodes_b) - set(nodes_a))
            lost_kept = [n for n in lost if tree_of.get(n) in kept_trees]
            # U-CIVTREE (was U-EGYPT): some civs that keep their civ lose their own Antiquity tree at the load
            # (Egypt; Han in 20261025-014531; Rome and Maya keep theirs). Only the current civ's own tree.
            civ_now = next((p.get("civ") for p in players if p.get("age") == nxt and p.get("id") == pid), None)
            own_tree = f"AQ_{civ_now}" if civ_now else known_lost_tree
            if lost_kept and all(tree_of.get(n) == own_tree for n in lost_kept):
                lines.append(f"  - KNOWN LIMIT (U-CIVTREE): player {pid} lost civics of its own civ's tree: {', '.join(lost_kept)}")
            elif lost_kept:
                failed = True
                lines.append(f"  - CONTINUITY FAIL: player {pid} lost civics in trees it still has: {', '.join(lost_kept)}")
            if len(lost) > len(lost_kept):
                lines.append(f"  - civics in trees no longer available: {', '.join(n for n in lost if n not in lost_kept)}")
            for k in ("buildings", "cap", "promotions"):
                if isinstance(a.get(k), int) and isinstance(b.get(k), int) and a[k] < b[k]:
                    lines.append(f"  - lower after the transition: {k} {b[k]} -> {a[k]}")
    lines.append("")
    # Design goal 1: the base game's resets (cities to towns, gold and influence caps, old resources removed).
    reset_lines, reset_failed = reload_reset_report(transitions, ends, reload_batches, records("RESOURCES"),
                                                    res_batches, slots)
    lines += reset_lines
    failed |= reset_failed
    # Units held at each age end, against the civ's age then: covers every way to get a unit,
    # including upgrades (rule 2g), which the production, purchase and transition checks do not see.
    # Unique units of the civ's current civ are the half swap's conversions (known limit).
    held_lines, rank3 = [], {"AQ": 0, "EX": 1, "MO": 2}
    for e in ends:
        types = unit_lists.get(("end", e["age"], e["id"]))
        if types is None or e.get("civAge") not in rank3:
            continue
        if e["age"] not in need_cache:
            need_cache[e["age"]] = required_ages(e["age"])
        civ_now = next((p.get("civ") for p in reversed(players) if p.get("age") == e["age"] and p.get("id") == e["id"]), None)
        own = civ_unique_units(civ_now)
        late = _C(u for u in types if too_early(need_cache[e["age"]].get("UNIT_" + u), e["civAge"], e.get("civicAge")))
        half = {u: n for u, n in late.items() if u in own}
        bad = {u: n for u, n in late.items() if u not in own}
        if half:
            held_lines.append(f"- KNOWN LIMIT (half swap): {e['age']} end, player {e['id']} (civ age {e['civAge']}, {civ_now}) holds its civ's later-age unique units: {half}")
        if bad:
            failed = True
            held_lines.append(f"- LEAK FAIL: {e['age']} end, player {e['id']} (civ age {e['civAge']}) holds units of a later age: {bad}")
    lines += ["## Units held at each age end, against the civ's age (all sources, upgrades included)", ""]
    lines += held_lines or ["- none of a later age"]
    lines.append("")
    # Civ age against world age: how long each civ stays behind the world (expected; a leading
    # civ can run away from the pack). Measured for balance tuning.
    order_short = {"AGE_ANTIQUITY": "AQ", "AGE_EXPLORATION": "EX", "AGE_MODERN": "MO"}
    rank_s = {"AQ": 0, "EX": 1, "MO": 2}
    lag = {}
    for p in players:
        w = p.get("age")
        if w in order_short and "civAge" in p:
            e = lag.setdefault((w, p["id"]), {"civ": p.get("civ"), "start": None, "caught": None, "ahead": None, "last": 0,
                                              "civic": {}})
            if e["start"] is None:
                e["start"] = p["civAge"]
            # The civic age (civic Breakthroughs): the first turn of each civic age in this world.
            if p.get("civicAge") in rank_s:
                e["civic"].setdefault(p["civicAge"], p["turn"])
            if e["caught"] is None and rank_s[p["civAge"]] >= rank_s[order_short[w]]:
                e["caught"] = p["turn"]
            if e["ahead"] is None and rank_s[p["civAge"]] > rank_s[order_short[w]]:
                e["ahead"] = p["turn"]
            e["last"] = max(e["last"], p["turn"])
    if lag:
        lines += ["", "Civ age against world age (turn of the first check at or above the world's age; "
                      "'ahead' = first check past it):", "",
                  "| World age | Player | Civ | Civ age at start | Reached world age | Ahead of world | Civic age (first turn) | Last turn checked |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for (w, pid), e in sorted(lag.items(), key=lambda x: (["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"].index(x[0][0]), x[0][1])):
            civic = ", ".join(f"{a} {t}" for a, t in sorted(e["civic"].items(), key=lambda x: rank_s[x[0]])) or "-"
            lines.append(f"| {w} | {pid} | {e['civ']} | {e['start']} | {e['caught'] if e['caught'] is not None else 'never'} | "
                         f"{e['ahead'] if e['ahead'] is not None else '-'} | {civic} | {e['last']} |")
    gates = records("GATE")
    if gates:
        agg = {}
        for g in gates:
            k = (g.get("age"), g["civAge"])
            a = agg.setdefault(k, [0, 0, 0, 0, set()])
            a[0] += g["ok"]["n"]; a[1] += g["needUnlock"]; a[2] += g["other"]; a[3] += g["notListed"]
            a[4].update(g["ok"]["sample"])
        lines += ["", "NOT RELIABLE: engine queries from the UI context answer for few (turn, player) pairs (most answers are empty refusals); the production log is the ground truth for leaks. Gate check (capital; items of an age the civ has not entered; the engine should refuse them):", "",
                  "| World age | Civ age | May start (leak) | Refused: needs unlock | Refused: other | Not listed | Leaked items |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for (w, ca), a in sorted(agg.items(), key=lambda x: (str(x[0][0]), x[0][1])):
            lines.append(f"| {w} | {ca} | {a[0]} | {a[1]} | {a[2]} | {a[3]} | {', '.join(sorted(a[4])[:10])} |")
    probes = records("PROBE")
    if probes:
        lines += ["", f"## Probe {probes[0].get('probe')} (test modifiers; local player's capital each turn)", "",
                  "| Turn | Modifier | Unit | From turn | Query | canStart | isBuildDisabled | isBuildPermanentlyDisabled |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for p in probes:
            lines.append(f"| {p['turn']} | {p['modifier']} | {p['unit']} | {p['fromTurn']} | {json.dumps(p['query'])} | "
                         f"{json.dumps(p['canStart'])} | {p['disabled']} | {p['permanentlyDisabled']} |")
    if players:
        gov_lines, gov_failed = gov_report(players, transitions, unseen)
        lines += [""] + gov_lines
        failed |= gov_failed
    bank_lines, bank_failed = bank_report(records("BANK"))
    lines += [""] + bank_lines if bank_lines else []
    failed |= bank_failed
    # Design goal 4: legacies of a later age than the world (the worlds in the order the checks saw them).
    worlds_seen = list(dict.fromkeys(p.get("age") for p in players if p.get("age") in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN")))
    legacy_lines, legacy_failed = legacy_report(LOGS / "Player_Legacies.csv", worlds_seen)
    lines += [""] + legacy_lines if legacy_lines else []
    failed |= legacy_failed
    upgrades = records("UPGRADE")
    up_ok = {}
    for p in players:
        u = p.get("upgrade")
        if u:
            s_ = up_ok.setdefault(p["id"], [0, 0])
            s_[0] = max(s_[0], u["eligible"])
            s_[1] = max(s_[1], u["allowed"])
    lines += ["", f"Unit upgrades observed (same unit id, new type): {len(upgrades)}; "
                  f"to an Exploration unit: {sum(1 for u in upgrades if u['toExploration'])}"]
    lines += [f"- turn {u['turn']}, player {u['id']}: {u['from']} -> {u['to']}" for u in upgrades[:12]]
    if up_ok:
        lines += ["", "NOT RELIABLE: engine queries from the UI context answer for few (turn, player) pairs (most answers are empty refusals); the production log is the ground truth for leaks. Units with an Exploration successor (most in one snapshot) and how many the engine let upgrade: "
                  + ", ".join(f"player {k}: {v[1]}/{v[0]}" for k, v in sorted(up_ok.items()))]
    if probe:
        lines += ["", "NOT RELIABLE: engine queries from the UI context answer for few (turn, player) pairs (most answers are empty refusals); the production log is the ground truth for leaks. Ocean probe over the run (engine asked whether ships may move onto nearby deep ocean; "
                      "only civs past their Exploration Breakthrough may):", "",
                  "| Player | Gate | Ocean plots probed | Moves allowed |", "| --- | --- | --- | --- |"]
        for (pid, key), (n, ok) in sorted(probe.items()):
            lines.append(f"| {pid} | {key} | {n} | {ok} |")
    if builds:
        bturn = builds[-1]["turn"]
        lines += ["", f"NOT RELIABLE: engine queries from the UI context answer for few (turn, player) pairs (most answers are empty refusals); the production log is the ground truth for leaks. Capital build check, turn {bturn} (Exploration buildings; engine answer as the "
                      "production screen gets it):", "",
                  "| Player | Can build | Needs tech/civic | No valid plot | Already built | Other | Not listed | "
                  "Antiquity buildings not yet built: ok / no plot / need tech | Constructibles in capital |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for b in (b for b in builds if b["turn"] == bturn):
            cell = lambda k: f"{b[k]['n']} {b[k]['sample']}"
            aq = b.get("aq", {})
            lines.append(f"| {b['id']} | {cell('ok')} | {cell('needUnlock')} | {cell('noPlot')} | "
                         f"{cell('exists')} | {cell('other')} | {b['notListed']} | "
                         f"{aq.get('ok')} / {aq.get('noPlot')} / {aq.get('needUnlock')} | {b.get('cityBuildings')} |")
    lines.append("")
    # Gates never stuck (CIVICGATE, TECHGATE), Catch-up Research speeds (CATCHUP), the civ age banner (UI lines).
    for part, part_failed in (gate_report("CIVICGATE", records("CIVICGATE")), gate_report("TECHGATE", records("TECHGATE")),
                              catchup_report(records("CATCHUP")), banner_report(checks)):
        lines += part
        failed |= part_failed
    # Production log: Exploration items that the AI produced
    units, buildings = exploration_items()
    first = {}
    qfile = LOGS / "CityBuildQueue.csv"
    if qfile.exists():
        for row in csv.reader(qfile.open(encoding="utf-8", errors="replace")):
            if len(row) > 4 and row[0].strip().isdigit():
                item = row[4].strip()
                if item in units or item in buildings:
                    first.setdefault(item, int(row[0]))
    if qfile.exists():
        lines += ["## Production by world age and native age", ""] + production_by_world(qfile, ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"].index(players[0]["age"]) if players and players[0].get("age") in ("AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN") else 0) + [""]
        leaks = production_leaks(qfile, players)
        lines += ["## Later-age items started before the civ's gate (leaks)", ""]
        lines += [f"- {w}, turn {t}, player {p} ({city}): {item} with civ age {ca}" for w, t, p, city, item, ca in leaks[:25]]
        if leaks:
            failed = True
        else:
            lines.append("- none")
        lines.append("")
        # Purchases with gold or faith (CityPurchase.csv), the same rule (gotcha checker review 1, #7).
        pfile = LOGS / "CityPurchase.csv"
        if pfile.exists():
            bought = production_leaks(pfile, players, item_col=3, names=item_names())
            lines += ["## Later-age items bought before the civ's gate (leaks)", ""]
            lines += [f"- {w}, turn {t}, player {p} ({city}): {item} with civ age {ca}" for w, t, p, city, item, ca in bought[:25]]
            if bought:
                failed = True
            else:
                lines.append("- none")
            lines.append("")
        replace_lines, replace_failed = replace_starts(qfile, players)
        lines += replace_lines
        failed |= replace_failed
    lines += ["## Exploration items produced (first turn in production)", ""]
    lines += [f"- {k}: turn {v}" for k, v in sorted(first.items(), key=lambda x: x[1])] or ["- none"]
    lines += ["", "## Autoplay runner output", "", "```", autoplay_out.strip(), "```", ""]
    # Keep the logs of this iteration
    shutil.copytree(LOGS, workdir / "logs", dirs_exist_ok=True)

    return not failed, lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=60)
    ap.add_argument("--fast-test", type=float, default=0.1)
    ap.add_argument("--no-fast-test", action="store_true")
    ap.add_argument("--timeout", type=int, default=75, help="minutes")
    ap.add_argument("--suite", default="ContinuousAgesAutoplay.json",
                    help="suite in autoplay/; ContinuousAgesTransition.json continues through age transitions")
    ap.add_argument("--age-points", type=int, default=None, help="test setting: each world age ends at N age-progress points (default: the base game's age length)")
    ap.add_argument("--observe", choices=["OBSERVER", "NONE", "0"], default="OBSERVER",
                    help="NONE sees nothing, so the engine shows fewer moves (faster; you cannot watch)")
    ap.add_argument("--probe", default=None, help="test build with the probe's test modifiers (build_mod.py PROBES); use --observe 0")
    ap.add_argument("--control", action="store_true",
                    help="control run: the base game with the mod's logging only (build_mod.py --control); most checks then fail")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="a test parameter in the suite's first test, for example --set MapSeed=11 --set GameSeed=11")
    ap.add_argument("--disable-rule", action="append", default=[],
                    help="negative control: build without this rule (build_mod.py DISABLE_RULES); the run should fail")
    ap.add_argument("--expect-transitions", type=int, default=None,
                    help="fail with fewer world transitions (TRANSITION records; the Modern age end counts), "
                         "for example 3 for the three-age suites at 700 turns")
    ap.add_argument("--worker", type=int, default=None, metavar="N",
                    help="run as worker N (parallel games; gamepool.py): own user folders, Mods, Logs and Saves")
    args = ap.parse_args()
    fast = None if args.no_fast_test else args.fast_test

    if WORKER:
        # Before anything else: a parallel game needs its own Saves folder (a Windows setting outside the repo) and
        # the Steam client. No run folder for a run that cannot start.
        problem = gamepool.require_documents(WORKER)
        if not problem and not gamepool.steam_running():
            problem = "NOT READY: the Steam client does not run (the game needs it; start Steam and log in)."
        if problem:
            print(f"Worker {WORKER}: {problem}")
            return 2
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-w{WORKER}" if WORKER else "")
    workdir = REPO / "build" / "iterations" / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    if game_running():
        print(f"Civilization VII is running{f' in worker {WORKER}' if WORKER else ''}. Close it first.")
        return 2
    if WORKER:
        info = gamepool.prepare(WORKER, live=False, copy_saves=TEST_SAVES)
        print(f"Worker {WORKER}: {info['user_data']}; saves {info['saves']}")
    # The generator source of this run, copied before the build (edits made during a run must not
    # end up in it), with a hash for the report header.
    shutil.copytree(HERE, workdir / "source", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))
    digest = hashlib.sha256()
    for f in sorted((workdir / "source").rglob("*")):
        if f.is_file():
            digest.update(f.relative_to(workdir / "source").as_posix().encode() + b"\0" + f.read_bytes())
    source_hash = digest.hexdigest()[:12]
    head = run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"]).stdout.strip()
    dirty = bool(run(["git", "-C", str(REPO), "status", "--porcelain", "generator"]).stdout.strip())
    print("1/3 Build and validate ...")
    extra = (["--probe", args.probe] if args.probe else []) + [x for r in args.disable_rule for x in ("--disable-rule", r)] \
        + (["--control"] if args.control else [])
    ok, build_out = build(fast, args.age_points, extra or None)
    (workdir / "build.txt").write_text(build_out, encoding="utf-8")
    if not ok:
        print("Build or validation failed:\n" + build_out[-2000:])
        return 1

    print(f"2/3 Autoplay {args.turns} turns ...")
    # About 3 of 60 games crashed in the game's audio engine in the first minutes, and a retry always ran clean
    # (docs/known-limits.md, Open checks). A crash before turn 5 of the first world age is retried once; the report
    # names the retry, and a second early crash counts.
    retried = None
    for attempt in range(2):
        start = datetime.now()
        res = run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "run_autoplay.ps1"),
                   "-Turns", str(args.turns), "-TimeoutMinutes", str(args.timeout), "-ObserveAs", args.observe, "-Suite", args.suite]
                  + (["-Set", ";".join(args.set)] if args.set else []))
        autoplay_out = res.stdout + res.stderr
        snaps = [l for l in (LOGS / "UI.log").read_text(encoding="utf-8", errors="replace").splitlines()
                 if "[CA-CHECK][SNAPSHOT]" in l] if (LOGS / "UI.log").exists() else []
        turns = [int(m.group(1)) for l in snaps for m in [re.search(r'"turn":(\d+)', l)] if m]
        early_crash = "CRASH" in autoplay_out and (not turns or max(turns) < 5) and len(snaps) < 3
        if attempt == 0 and early_crash:
            retried = f"the first attempt crashed before turn 5 (runner output: {autoplay_out.strip().splitlines()[-1][:200] if autoplay_out.strip() else ''})"
            print(f"Early crash: retrying once ({retried})")
            continue
        break
    if retried:
        autoplay_out = f"RETRIED: {retried}\n\n" + autoplay_out
    ui_log = LOGS / "UI.log"
    if res.returncode == 2 or not ui_log.exists() or ui_log.stat().st_mtime < start.timestamp():
        # No game ran (the runner timed out waiting for the game to start): the logs are an older run's.
        report = f"# Iteration {stamp}: COULD NOT RUN\n\n```\n{autoplay_out}\n```\n"
        (workdir / "REPORT.md").write_text(report, encoding="utf-8")
        print("The game did not run; logs are from an earlier run. Nothing analyzed.\n" + autoplay_out)
        return 2

    print("3/3 Analyze ...")
    passed, lines = analyze(start, autoplay_out, workdir, expect_transitions=args.expect_transitions)
    header = [f"# Iteration {stamp}: {'PASS' if passed else 'FAIL'}", "",
              f"- Turns: {args.turns}; suite: {args.suite}; fast test: {fast}; autoplay exit code: {res.returncode}",
              f"- Source: hash {source_hash} (source/), git {head}{' + uncommitted changes' if dirty else ''}",
              ] + ([f"- Worker: {WORKER} (own user folders, Mods and Saves in {gamepool.worker_dir(WORKER)}; game started "
                    "from its executable)"] if WORKER else []) + [
              f"- Known limits hit (listed, not counted as failures): {sum('KNOWN LIMIT' in l for l in lines)}",
              ] + [f"- Build, {m}" for m in re.findall(r"world \w+: .*?violations", build_out)] + [""]
    report = workdir / "REPORT.md"
    report.write_text("\n".join(header + lines), encoding="utf-8")
    print(f"{'PASS' if passed else 'FAIL'}: {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
