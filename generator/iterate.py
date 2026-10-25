"""One test iteration: build, validate, install, autoplay, analyze.

  1. Build the test mod with the in-game checks (build_mod.py --install --checks).
     Stop if the simulator finds load issues, broken references or unclassified tables.
  2. Run an AI-only autoplay game (run_autoplay.ps1). The game must be closed first.
  3. Analyze: automation result, crash dumps (tools/crashstack.py), database and mod
     errors, the [CA-CHECK] lines of checks/ca-checks.js, and the CSV logs.
  4. Write build/iterations/<time>/REPORT.md and keep a copy of the logs.

Usage: python iterate.py [--turns 60] [--fast-test 0.1 | --no-fast-test] [--timeout 75]
Exit code: 0 = pass, 1 = fail, 2 = could not run.
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MOD_DIR = REPO / "build" / "continuous-ages"
USER_DATA = Path.home() / "AppData" / "Local" / "Firaxis Games" / "Sid Meier's Civilization VII"
LOGS = USER_DATA / "Logs"
DUMP_DIRS = [USER_DATA / "packagedDumps", USER_DATA / "dumps", Path.home() / "AppData" / "Local" / "CrashDumps"]
TOOLS_PY = HERE / ".venv" / "Scripts" / "python.exe"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def game_running() -> bool:
    out = run(["tasklist", "/FI", "IMAGENAME eq Civ7_Win64_DX12_FinalRelease.exe", "/NH"]).stdout
    return "Civ7_Win64" in out


def build(fast: float | None, age_points: int | None = None, extra: list | None = None) -> tuple[bool, str]:
    cmd = [sys.executable, str(HERE / "build_mod.py"), "--install", "--checks"] + (extra or [])
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


def required_ages(world: str) -> dict:
    """Item -> the civ age it needs in the built mod for this world (0 Antiquity, 1 Exploration,
    2 Modern), from its unlock rows; the unlocks are OR, so the earliest counts. A node of a civ's
    own tree (unique, Test of Time or branch civics) counts as its tree's age. A civ-unique item
    with no unlock row needs the age of its civ (the age of the civ's unique tree)."""
    mods = c.load_base_modules(include_dlc=True) + [c.parse_modinfo(MOD_DIR / "continuous-ages.modinfo")]
    sim = c.Simulator()
    for path in c.database_items(c.applicable_groups(mods, world)):
        sim.apply_file(path)
    q = lambda sql: sim.db.execute(sql).fetchall()
    short = {"AQ": 0, "EX": 1, "MO": 2}
    tree_of = dict(q("SELECT ProgressionTreeNodeType, ProgressionTree FROM ProgressionTreeNodes"))
    def node_age(n):
        for age, prefixes in ((0, ("NODE_TECH_AQ_", "NODE_CIVIC_AQ_MAIN_")),
                              (1, ("NODE_TECH_EX_", "NODE_CIVIC_EX_MAIN_", "NODE_TECH_CA_EXPLORATION_")),
                              (2, ("NODE_TECH_MO_", "NODE_CIVIC_MO_MAIN_", "NODE_TECH_CA_MODERN_"))):
            if n.startswith(prefixes):
                return age
        parts = (tree_of.get(n) or "").split("_")  # TREE_CIVICS_<age>_<name>
        return short.get(parts[2]) if len(parts) > 2 else None
    rows = {}
    for node, target in q("SELECT ProgressionTreeNodeType, TargetType FROM ProgressionTreeNodeUnlocks "
                          "WHERE TargetKind IN ('KIND_UNIT', 'KIND_CONSTRUCTIBLE')"):
        rows.setdefault(target, []).append(node_age(node))
    need = {t: min(a for a in ages if a is not None) for t, ages in rows.items() if any(a is not None for a in ages)}
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
        if t not in need and len(civs) == 1 and next(iter(civs)) in civ_age:
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
    rank = {"AQ": 0, "EX": 1, "MO": 2}
    need = {w: required_ages(w) for w in worlds}
    timeline = {}
    for p in players:
        if "civAge" in p and p.get("age") in worlds:
            timeline.setdefault((p["age"], p["id"]), []).append((p["turn"], p["civAge"]))
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
        later = [ca for t, ca in sorted(timeline.get((world, pid), [])) if t >= turn]
        civ_age = later[0] if later else None
        if civ_age is not None and rank[civ_age] < required:
            leaks.append((world, turn, pid, row[2].strip(), item, civ_age))
    return leaks


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


def analyze(start: datetime, autoplay_out: str, workdir: Path) -> tuple[bool, list[str]]:
    lines, failed = [], False
    # Automation result
    results = log_lines(r"\[PASS\]|\[FAIL\]|Autoplay Turn Limit Hit")
    lines += ["## Automation", ""] + [f"- {r}" for r in results] + [""]
    if not any("[PASS]" in r for r in results) or any("[FAIL]" in r for r in results):
        failed = True
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
             if p.is_file() and datetime.fromtimestamp(p.stat().st_mtime) > start
             and ("Civ7" in p.name or p.name == "submission.pkg")]
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
    # Gold after each reload, before any civ plays (written by the transition script, one batch per transition).
    reload_batches, cur = [], {}
    for r in records("RELOAD"):
        if r["id"] in cur:
            reload_batches.append(cur)
            cur = {}
        cur[r["id"]] = r
    if cur:
        reload_batches.append(cur)
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
        reload = reload_batches[ti] if ti < len(reload_batches) else {}
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
            gm = (gate_mods[ti] if ti < len(gate_mods) else {}).get(pid)
            if gm is not None:
                n, act = (gm.get("CA_GATE_") or [0, 0])
                behind = {"AQ": 0, "EX": 1, "MO": 2}.get(b.get("civAge"), 0) < order.index(nxt)
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
            r_units = reload_units[ti].get(pid) if ti < len(reload_units) else None
            r_cons = reload_cons[ti].get(pid) if ti < len(reload_cons) else None
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
                # Egypt's Tjaty great people at each load (iterations 20261025-012715, 012845, 010211).
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
                known_civil = {u: n for u, n in lost_civil.items() if u.startswith("TJATY") or u == "PHYSICIAN"
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
                    rank = {"AQ": 0, "EX": 1, "MO": 2}.get(a.get("civAge"))
                    early = {u: n for u, n in new_u.items()
                             if rank is not None and (need_cache[nxt].get("UNIT_" + u) or 0) > rank}
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
                        for u in list(early):
                            base = need_cache["replaces"].get("UNIT_" + u, "").replace("UNIT_", "")
                            k = min(early[u], left.get(base, 0))
                            if k:
                                converted[f"{base} -> {u}"] = k
                                left[base] -= k
                                early[u] -= k
                                if not early[u]:
                                    del early[u]
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
                    rank = {"AQ": 0, "EX": 1, "MO": 2}.get(a.get("civAge"))
                    early1 = {u: n for u, n in t1_new.items()
                              if rank is not None and (need_cache[nxt].get("UNIT_" + u) or 0) > rank}
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
        late = _C(u for u in types if (need_cache[e["age"]].get("UNIT_" + u) or 0) > rank3[e["civAge"]])
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
            e = lag.setdefault((w, p["id"]), {"civ": p.get("civ"), "start": None, "caught": None, "ahead": None, "last": 0})
            if e["start"] is None:
                e["start"] = p["civAge"]
            if e["caught"] is None and rank_s[p["civAge"]] >= rank_s[order_short[w]]:
                e["caught"] = p["turn"]
            if e["ahead"] is None and rank_s[p["civAge"]] > rank_s[order_short[w]]:
                e["ahead"] = p["turn"]
            e["last"] = max(e["last"], p["turn"])
    if lag:
        lines += ["", "Civ age against world age (turn of the first check at or above the world's age; "
                      "'ahead' = first check past it):", "",
                  "| World age | Player | Civ | Civ age at start | Reached world age | Ahead of world | Last turn checked |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for (w, pid), e in sorted(lag.items(), key=lambda x: (["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"].index(x[0][0]), x[0][1])):
            lines.append(f"| {w} | {pid} | {e['civ']} | {e['start']} | {e['caught'] if e['caught'] is not None else 'never'} | "
                         f"{e['ahead'] if e['ahead'] is not None else '-'} | {e['last']} |")
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
    args = ap.parse_args()
    fast = None if args.no_fast_test else args.fast_test

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    workdir = REPO / "build" / "iterations" / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    if game_running():
        print("Civilization VII is running. Close it first.")
        return 2
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
    ok, build_out = build(fast, args.age_points)
    (workdir / "build.txt").write_text(build_out, encoding="utf-8")
    if not ok:
        print("Build or validation failed:\n" + build_out[-2000:])
        return 1

    print(f"2/3 Autoplay {args.turns} turns ...")
    start = datetime.now()
    res = run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "run_autoplay.ps1"),
               "-Turns", str(args.turns), "-TimeoutMinutes", str(args.timeout), "-ObserveAs", args.observe, "-Suite", args.suite])
    autoplay_out = res.stdout + res.stderr
    ui_log = LOGS / "UI.log"
    if res.returncode == 2 or not ui_log.exists() or datetime.fromtimestamp(ui_log.stat().st_mtime) < start:
        # No game ran (the runner timed out waiting for the game to start): the logs are an older run's.
        report = f"# Iteration {stamp}: COULD NOT RUN\n\n```\n{autoplay_out}\n```\n"
        (workdir / "REPORT.md").write_text(report, encoding="utf-8")
        print("The game did not run; logs are from an earlier run. Nothing analyzed.\n" + autoplay_out)
        return 2

    print("3/3 Analyze ...")
    passed, lines = analyze(start, autoplay_out, workdir)
    header = [f"# Iteration {stamp}: {'PASS' if passed else 'FAIL'}", "",
              f"- Turns: {args.turns}; suite: {args.suite}; fast test: {fast}; autoplay exit code: {res.returncode}",
              f"- Source: hash {source_hash} (source/), git {head}{' + uncommitted changes' if dirty else ''}",
              f"- Known limits hit (listed, not counted as failures): {sum('KNOWN LIMIT' in l for l in lines)}",
              ] + [f"- Build, {m}" for m in re.findall(r"world \w+: .*?violations", build_out)] + [""]
    report = workdir / "REPORT.md"
    report.write_text("\n".join(header + lines), encoding="utf-8")
    print(f"{'PASS' if passed else 'FAIL'}: {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
