"""Build the Continuous Ages mod for all ages and all world ages.

The world age is the engine's global age (Antiquity, Exploration or Modern). It advances
through the game's own age transition, which the mod keeps but without the reset. Each civ
also has its own age: the last breakthrough tech it has researched.

For each world age W the mod loads, in addition to W's own data (loaded by the game):
  * the content of the other ages, through the content allow list (classification.py),
  * rules (SQL): one joined tech tree and one joined civic tree with the same ids in every
    world age, the Exploration and Modern breakthrough gates, the building-age rule, and
    the baseline adapters for ages ahead of W.
Systems (engine behaviour, transition setup) stay with their own age and start when the
world reaches it. See the design doc, "Core rule: content per civ, systems per world".

Usage: python build_mod.py [--install] [--package] [--checks] [--fast-test [F]] [--age-points N]
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import escape
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import civ7data as c
import classification as cls
from build_test1 import transition_script, write_xml, EXCLUDE_PATTERNS, TEXT_EXCLUDE

MOD_ID = "continuous-ages"
MOD_VERSION = "0.2.0"  # the release version (docs/releasing.md); the zip name and build-info.json use it
OLD_MOD_IDS = ["continuous-ages-test1"]
MOD_NAME = "Continuous Ages"
# Plain text in the modinfo, not text keys: the Steam Workshop uploader shows the modinfo's Name and
# Description as written (the game's Mods screen accepts both). No Steam markup: the Mods screen
# shows the same text.
MOD_DESCRIPTION = """One continuous game. Each civilization moves through the ages at its own pace, and nothing resets at an age transition. A strong civilization can keep its lead and snowball.

HOW IT WORKS
- Your own age: one joined tech tree with two Breakthrough techs. Research the Exploration Breakthrough and the Modern Breakthrough to enter the next age, when you are ready. A small banner shows "Your age / World age".
- The world still moves on: the world age changes at the normal time. Crises, legacy paths, treasure fleets, the Distant Lands and victories start with the world age, as in the base game.
- No reset: cities stay cities, armies keep their units and promotions, gold is not capped, old resources stay, and your techs, civics, policies and buildings stay.
- Content waits for your age: later-age techs, civics, units, buildings, unique items and civ abilities need that age's Breakthrough, also after the world moves on.
- Units upgrade across ages, for example Phalanx to Swordsman and Pikeman to Line Infantry.

CATCH-UP RESEARCH (OPTIONAL)
Set it in the game setup: Advanced Options, Game Options, Catch-up Research (below Age Transition Impact). Choose before the game starts; you cannot change it later.
- Off (default): no catch-up, full snowballing.
- +50%: after each world age transition, the techs and civics of earlier ages, and the Breakthrough into the new world age, cost two thirds.
- +100%: they cost half.
Only a civ that still needs those techs and civics gains from it, so it helps civs that are behind the world to catch up. AI civs get it too.

RECOMMENDED SETTINGS
- Age Transition Impact: Continuity.
- Start age: Antiquity.
- AI civ selection at age transition: Mirroring (default), or Current Civilization Persistence.

STATUS
Playable, in testing. Full AI games pass all three ages at all four game speeds in automated tests. Human play through an age transition has had less testing. Please report problems.

COMPATIBILITY
- Version {mod_version}, built for Civilization VII {game_version}, with the base game and DLC civilizations.
- Affects saved games: enable it before you start a new game.
- Replaces the game's age transition script. Other mods that change that script will conflict.
- Single player. Multiplayer is not tested.

Documentation, source and known limits: https://github.com/smithc/civ7-continuous-ages"""
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "build" / MOD_ID
MODS_DIR = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "Firaxis Games" / "Sid Meier's Civilization VII" / "Mods")

AGES = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
SHORT = {"AGE_ANTIQUITY": "AQ", "AGE_EXPLORATION": "EX", "AGE_MODERN": "MO"}
NAME = {"AGE_ANTIQUITY": "Antiquity", "AGE_EXPLORATION": "Exploration", "AGE_MODERN": "Modern"}

# One joined tree per system, with the same id in every world age (so completed nodes have the
# best chance to survive the transition reload).
TECH_TREES = ["TREE_TECHS_AQ", "TREE_TECHS_EX", "TREE_TECHS_MO"]
CIVIC_TREES = ["TREE_CIVICS_AQ_MAIN", "TREE_CIVICS_EX_MAIN", "TREE_CIVICS_MO_MAIN"]
GATES = {"AGE_EXPLORATION": "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", "AGE_MODERN": "NODE_TECH_CA_MODERN_BREAKTHROUGH"}
GATE_MODIFIER = {a: f"MOD_CA_{NAME[a].upper()}_BREAKTHROUGH" for a in GATES}
GATE_COST_FACTOR = 1.2
# Catch-up research (game setup option): every node of an age before the world age, and the
# Breakthrough into the world age, costs 1 / (1 + Percent/100): +50% two thirds, +100% half
# (getNodeCost, iterations 20261025-170959 and 171708).
CATCHUP_KEY = "CaCatchUp"
CATCHUP = {"CA_CATCHUP_50": 50, "CA_CATCHUP_100": 100}
CATCHUP_CHUNK = 40  # nodes per modifier (the base game's longest list has 7; keep each list short)

# Shared civ-age files of another age: the civ abilities of other-age civs in that age.
EXCLUDE_MODULE_PATTERNS: list[str] = []

# Baseline adapters (design doc, rules 3 and 4): the civ's own age baseline arrives at its gate,
# while the world is behind that age. Chosen with the design owner: the ocean group and the
# age-balance group. Delta entries: (Exploration or Modern definition, argument overrides).
BASELINE = {
    "AGE_EXPLORATION": {
        "as_is": ["MOD_TECH_OCEAN_TRAVEL", "MOD_EXPLORATION_EMBARKATION", "MOD_EX_DEEP_OCEAN_TRADE",
                  "TRAIT_MOD_BAZAAR_RESOURCE_CAP", "TRAIT_MOD_WHARF_RESOURCE_CAP",
                  "TRAIT_MOD_EXPLORATION_CIV_DIPLOMACY_TOKENS", "TRAIT_COMBAT_FLANKING", "TRAIT_AI_SIGHT",
                  "TRAIT_MOD_TOWN_TRADE_PROJECT", "TRAIT_MOD_ORTOO_RESTORE_MOVEMENT", "TERRACE_FARM_MOD_BUILDING_GOLD"],
        "delta": {"TRAIT_MOD_GOLD_UNASSIGNED_RESOURCE": {"Amount": "1"},       # 1 -> 2
                  "TRAIT_MOD_HAPPINESS_UNASSIGNED_RESOURCE": {"Amount": "1"},  # 1 -> 2
                  "TRAIT_INITIAL_SETTLEMENT_CAP": None},                      # minimum 8
    },
    "AGE_MODERN": {
        "as_is": ["MOD_MODERN_OCEAN_TRAVEL", "MOD_MODERN_EMBARKATION", "MOD_TECH_MO_EMBARKATION",
                  "TRAIT_MOD_DEPARTMENT_STORE_RESOURCE_CAP", "TRAIT_MOD_PORT_RESOURCE_CAP",
                  "TRAIT_MOD_FACTORY_RESOURCE_CAP", "TRAIT_MOD_MODERN_CIV_DIPLOMACY_TOKENS",
                  "TRAIT_MOD_TOWN_FACTORY_PROJECT", "DIPLOMACY_MOD_UNLOCK_COUNTER_SPY"],
        "delta": {"TRAIT_MOD_GOLD_UNASSIGNED_RESOURCE": {"Amount": "1"},       # 2 -> 3
                  "TRAIT_MOD_HAPPINESS_UNASSIGNED_RESOURCE": {"Amount": "1"},  # 2 -> 3
                  "TRAIT_INITIAL_SETTLEMENT_CAP": None},                      # minimum 16
    },
}
# Traits that carry each age's baseline in the base game.
BASELINE_TRAITS = ("TRAIT_ANTIQUITY_CIV", "TRAIT_EXPLORATION_CIV", "TRAIT_MODERN_CIV", "TRAIT_ANACHRONISTIC_CIV")

ET.register_namespace("", "GameEffects")


def later(a: str, b: str) -> bool:
    return AGES.index(a) > AGES.index(b)


def excluded(module: str, item: str) -> bool:
    name = item.rsplit("/", 1)[-1]
    return (any(fnmatch.fnmatch(name, p) for p in EXCLUDE_PATTERNS)
            or any(fnmatch.fnmatch(f"{module}/{item}", p) for p in EXCLUDE_MODULE_PATTERNS))


def other_age_groups(mods, world: str):
    """Groups that load in some other age but not in the world age, oldest age first."""
    in_world = {(m.id, g.id) for m, g in c.applicable_groups(mods, world)}
    seen, out = set(), []
    for age in AGES:
        if age == world:
            continue
        for m, g in c.applicable_groups(mods, age):
            key = (m.id, g.id)
            if key not in in_world and key not in seen:
                seen.add(key)
                out.append((age, m, g))
    return out


class WorldBuild:
    """Everything the mod loads when the world age is `world`."""

    def __init__(self, game: Path, world: str, args):
        self.game, self.world, self.args = game, world, args
        self.w = SHORT[world]
        self.log = defaultdict(list)
        self.counters = defaultdict(Counter)
        self.sim = c.simulate(game, world, include_dlc=True)
        # Traits whose abilities the world age defines itself: its version wins.
        self.native_traits = {r[0] for r in self.sim.db.execute("SELECT DISTINCT TraitType FROM TraitModifiers")}
        self.items: list[str] = []
        self.text_items: list[str] = []

    # -- content ---------------------------------------------------------------
    def copy_content(self, groups):
        for age, mod, grp in groups:
            for tag, paths in grp.actions:
                if tag != "UpdateDatabase":
                    continue
                for item in paths:
                    if excluded(mod.id, item):
                        self.log["skipped"].append((f"{mod.id}:{grp.id}", item))
                        continue
                    rel_item = f"data/{self.w}/{mod.id}/{item}"
                    self.copy_file(mod.folder / item, OUT / rel_item)
                    self.items.append(rel_item)

    def copy_file(self, src: Path, dest: Path):
        name = c.rel(src)
        sim = self.sim
        if src.suffix.lower() == ".sql":
            sim.apply_file(src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            return
        root = ET.parse(src).getroot()
        changed = False
        if c.strip_ns(root.tag) == "GameEffects":
            for el in list(root):
                store = sim.modifiers if c.strip_ns(el.tag) == "Modifier" else sim.requirement_sets
                if el.get("id") in store:
                    root.remove(el)
                    changed = True
                    self.counters["dropped_effects"][name] += 1
            sim.apply_game_effects(name, root)
        else:
            for tbl_el in list(root):
                tname = c.strip_ns(tbl_el.tag)
                table = sim._table(tname)
                klass = cls.table_class(tname, src.name)
                if klass != "content":
                    self.log["systems"].append((name, tname, klass, len(tbl_el)))
                    root.remove(tbl_el)
                    changed = True
                    continue
                for op in list(tbl_el):
                    otag = c.strip_ns(op.tag)
                    if otag in ("Update", "Delete", "Replace"):
                        tbl_el.remove(op)
                        changed = True
                        self.counters["stripped"][f"{name} {tname} {otag}"] += 1
                        continue
                    if tname == "TraitModifiers":
                        trait = op.get("TraitType") or (op.findtext("TraitType") or "").strip()
                        owners = sim.db.execute(
                            "SELECT (SELECT COUNT(*) FROM CivilizationTraits WHERE TraitType = ?) + "
                            "(SELECT COUNT(*) FROM LeaderTraits WHERE TraitType = ?)", (trait, trait)).fetchone()[0]
                        reason = ("shared trait (age baseline)" if owners != 1 else
                                  "world-age version of this civ's abilities wins" if trait in self.native_traits else None)
                        if reason:
                            tbl_el.remove(op)
                            changed = True
                            self.counters["trait_rows"][f"{trait}: {reason}"] += 1
                            continue
                    if tname == "Types":
                        kind = op.get("Kind") or (op.findtext("Kind") or "").strip() or None
                        if not cls.type_is_content(kind):
                            tbl_el.remove(op)
                            changed = True
                            self.counters["system_types"][kind] += 1
                            continue
                    if table is None:
                        self.log["errors"].append((name, tname, "unknown table"))
                        continue
                    before = len(sim.issues)
                    mode = "OR IGNORE" if otag == "InsertOrIgnore" else ""
                    try:
                        values = sim._row_values(table, op)
                    except KeyError as e:
                        self.log["errors"].append((name, tname, str(e)))
                        continue
                    if not sim.insert(name, table, values, mode):
                        issue = sim.issues[before]
                        tbl_el.remove(op)
                        changed = True
                        if issue.kind == "conflict":
                            self.counters["dropped_rows"][f"{name} {tname}"] += 1
                        else:
                            self.log["errors"].append((name, tname, issue.detail))
                if len(tbl_el) == 0:
                    root.remove(tbl_el)
        if changed:
            write_xml(root, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)

    def copy_text(self, groups, mods):
        tags = set()
        for mod, grp in c.applicable_groups(mods, self.world):
            for tag, paths in grp.actions:
                if tag == "UpdateText":
                    for item in paths:
                        f = mod.folder / item
                        if "en_us" in item and f.exists():
                            tags |= {el.get("Tag") for el in ET.parse(f).iter() if el.get("Tag")}
        for age, mod, grp in groups:
            for tag, paths in grp.actions:
                if tag != "UpdateText":
                    continue
                for item in paths:
                    if "en_us" not in item or item.rsplit("/", 1)[-1] in TEXT_EXCLUDE:
                        continue
                    root = ET.parse(mod.folder / item).getroot()
                    for table in list(root):
                        for row in list(table):
                            key = row.get("Tag")
                            if key in tags:
                                table.remove(row)
                            elif key:
                                tags.add(key)
                        if len(table) == 0:
                            root.remove(table)
                    rel_item = f"text/{self.w}/{mod.id}/{item}"
                    write_xml(root, OUT / rel_item)
                    self.text_items.append(rel_item)

    # -- rules -----------------------------------------------------------------
    def tree_chain(self, trees: list[str], gates: dict | None, prefix: str):
        """SQL that joins the main trees of all ages into trees[0], in age order.
        With gates, a gate node sits between the ages; otherwise each age's first nodes
        need the previous age's last nodes."""
        q = lambda sql, *a: self.sim.db.execute(sql, a).fetchall()
        canon = trees[0]
        nodes = {t: [r[0] for r in q("SELECT ProgressionTreeNodeType FROM ProgressionTreeNodes "
                                      "WHERE ProgressionTree = ?", t)] for t in trees}
        repeatable = {r[0] for r in q("SELECT ProgressionTreeNodeType FROM ProgressionTreeNodes WHERE Repeatable = 1")}
        prereqs = q("SELECT Node, PrereqNode FROM ProgressionTreePrereqs")
        lines, info = [], {}
        # Each age's repeatable "future" node is removed, except the last age's.
        removed = [n for t in trees[:-1] for n in nodes[t] if n in repeatable]
        for i in range(1, len(trees)):
            prev = [n for n in nodes[trees[i - 1]] if n not in repeatable]
            cur = [n for n in nodes[trees[i]] if n not in repeatable]
            used = {p for n, p in prereqs if n in prev}
            leaves = sorted(n for n in prev if n not in used)
            has = {n for n, p in prereqs}
            roots = sorted(n for n in cur if n not in has)
            age = AGES[i]
            if gates:
                gate = gates[age]
                cost = q(f"SELECT MAX(Cost) FROM ProgressionTreeNodes WHERE ProgressionTree = ? "
                         f"AND Repeatable = 0", trees[i - 1])[0][0] or 100
                gate_cost = int(round(cost * GATE_COST_FACTOR / 5.0) * 5)
                icon = q("SELECT IconString FROM ProgressionTreeNodes WHERE Repeatable = 1 AND ProgressionTree = ?",
                         trees[i - 1])
                icon = icon[0][0] if icon else "tech_futuretech"
                lines += [f"-- {NAME[age]} Breakthrough gate (cost {gate_cost}).",
                          f"INSERT INTO Types (Type, Kind) VALUES ('{gate}', 'KIND_TREE_NODE');",
                          "INSERT INTO ProgressionTreeNodes (ProgressionTreeNodeType, ProgressionTree, Cost, Name, Description, IconString) "
                          f"VALUES ('{gate}', '{canon}', {gate_cost}, 'LOC_{gate}_NAME', 'LOC_{gate}_DESCRIPTION', '{icon}');",
                          "-- A node needs one unlock level, or it is not drawn and is researched again every turn.",
                          "INSERT INTO ProgressionTreeNodeUnlocks (ProgressionTreeNodeType, TargetKind, TargetType, UnlockDepth) "
                          f"VALUES ('{gate}', 'KIND_MODIFIER', '{GATE_MODIFIER[age]}', 1);"]
                lines += [f"INSERT INTO ProgressionTreePrereqs (Node, PrereqNode) VALUES ('{gate}', '{n}');" for n in leaves]
                lines += [f"INSERT INTO ProgressionTreePrereqs (Node, PrereqNode) VALUES ('{n}', '{gate}');" for n in roots]
                info[age] = {"gate_cost": gate_cost, "leaves": leaves, "roots": roots}
            else:
                lines += [f"-- {NAME[age]} {prefix}: first nodes need the previous age's last nodes,"]
                lines += [f"INSERT INTO ProgressionTreePrereqs (Node, PrereqNode) VALUES ('{r}', '{l}');"
                          for r in roots for l in leaves]
                # and the civ's tech breakthrough of that age (a prereq across the two trees; both use
                # PrereqFormat AND). Without it, a civ entered later-age civics (museum, wonders)
                # before its breakthrough (iteration 20261024-185219).
                lines += [f"--   and the {NAME[age]} Breakthrough tech."]
                lines += [f"INSERT INTO ProgressionTreePrereqs (Node, PrereqNode) VALUES ('{r}', '{GATES[age]}');"
                          for r in roots]
                info[age] = {"leaves": leaves, "roots": roots, "gate": GATES[age]}
        lines += [f"UPDATE ProgressionTreeNodes SET ProgressionTree = '{canon}', UILayoutColumn = NULL, UILayoutRow = NULL "
                  f"WHERE ProgressionTree IN ({', '.join(repr(t) for t in trees)});"]
        for n in removed:
            lines += [f"DELETE FROM ProgressionTreePrereqs WHERE Node = '{n}' OR PrereqNode = '{n}';",
                      f"DELETE FROM ProgressionTreeNodeUnlocks WHERE ProgressionTreeNodeType = '{n}';",
                      f"DELETE FROM ProgressionTreeNodes WHERE ProgressionTreeNodeType = '{n}';",
                      f"DELETE FROM TypeQuotes WHERE Type = '{n}';",
                      f"DELETE FROM Types WHERE Type = '{n}';"]
        info["removed_repeatable"] = removed
        return lines, info

    def baseline_adapter(self):
        """Gate unlocks for the baseline of each age ahead of the world, and new definitions."""
        in_world = {r[0] for r in self.sim.db.execute(
            f"SELECT tm.ModifierId FROM TraitModifiers tm WHERE tm.TraitType IN "
            f"({','.join('?' * len(BASELINE_TRAITS))})", BASELINE_TRAITS)}
        lines, defs, report = [], [], []
        for age, spec in BASELINE.items():
            if not later(age, self.world):
                report.append((age, "the world provides this baseline (one source per baseline)"))
                continue
            gate = GATES[age]
            defs_by_id = {}
            for f in sorted((self.game / "Base" / "modules" / f"age-{NAME[age].lower()}" / "data").glob("*gameeffects*.xml")):
                for el in ET.parse(f).getroot():
                    if c.strip_ns(el.tag) == "Modifier":
                        defs_by_id.setdefault(el.get("id"), el)
            granted = []
            for mid in spec["as_is"]:
                if mid in in_world and age == self.world:
                    continue
                if mid not in self.sim.modifiers:
                    if mid in defs_by_id:  # defined only in that age's data: add the definition
                        defs.append(ET.fromstring(ET.tostring(defs_by_id[mid])))
                    else:
                        report.append((age, f"{mid}: no definition"))
                        continue
                granted.append(mid)
            for mid, overrides in spec["delta"].items():
                el = defs_by_id.get(mid)
                if el is None:
                    report.append((age, f"{mid}: no definition"))
                    continue
                copy = ET.fromstring(ET.tostring(el))
                new_id = f"CA_{SHORT[age]}_{mid}"
                copy.set("id", new_id)
                for arg in copy:
                    if c.strip_ns(arg.tag) == "Argument" and overrides and arg.get("name") in overrides:
                        arg.text = overrides[arg.get("name")]
                defs.append(copy)
                granted.append(new_id)
            lines += [f"-- {NAME[age]} baseline at the civ's {NAME[age]} Breakthrough (hidden unlocks)."]
            lines += [f"INSERT INTO ProgressionTreeNodeUnlocks (ProgressionTreeNodeType, TargetKind, TargetType, UnlockDepth, Hidden) "
                      f"VALUES ('{gate}', 'KIND_MODIFIER', '{m}', 1, 1);" for m in granted]
            report.append((age, "granted: " + ", ".join(granted)))
        return lines, defs, report

    def rules(self):
        args = self.args
        lines = [f"-- Generated by build_mod.py for world age {self.world}. Do not edit; run the generator again.", ""]
        lines += ["-- 1. One joined tech tree and one joined civic tree, with the same ids in every world age.",
                  "UPDATE Ages SET MainTechProgressionTreeType = 'TREE_TECHS_AQ', "
                  "MainCultureProgressionTreeType = 'TREE_CIVICS_AQ_MAIN';"]
        # Test (2026-10-24): after a transition, items unlocked by later-age nodes were built without
        # those nodes. Hypothesis: the engine treats a tree of an earlier age as finished. The joined
        # trees therefore take the world age.
        lines += [f"UPDATE ProgressionTrees SET AgeType = '{self.world}' "
                  "WHERE ProgressionTreeType IN ('TREE_TECHS_AQ', 'TREE_CIVICS_AQ_MAIN');"]
        tech_lines, tech_info = self.tree_chain(TECH_TREES, GATES, "techs")
        civic_lines, civic_info = self.tree_chain(CIVIC_TREES, None, "civics")
        lines += tech_lines + [""] + civic_lines + [""]
        lines += ["-- 2. Building-age rule: the earlier of the constructible's age and the world age."]
        later_ages = [a for a in AGES if later(a, self.world)]
        if later_ages:
            lines += [f"UPDATE Constructibles SET Age = '{self.world}' WHERE Age IN ({', '.join(repr(a) for a in later_ages)});"]
        lines += ["", "-- 2b. Starter items of a later age (no unlock in the base game) need that age's gate."]
        for age, kinds in self.starters.items():
            for kind, types in kinds.items():
                lines += [f"INSERT OR IGNORE INTO ProgressionTreeNodeUnlocks (ProgressionTreeNodeType, TargetKind, TargetType, "
                          f"UnlockDepth) VALUES ('{GATES[age]}', '{kind}', '{t}', 1);" for t in types]
        lines += ["", "-- 2d. Civ content of a later age needs the gate of the civ's age: the first nodes of the",
                  "--     civ's unique civic tree, and its unique items that have no unlock row. (Guarded: the",
                  "--     tree or item may not be in this world's data.)"]
        for age, content in self.civ_content.items():
            gate = GATES[age]
            lines += [f"INSERT INTO ProgressionTreePrereqs (Node, PrereqNode) SELECT '{n}', '{gate}' WHERE EXISTS "
                      f"(SELECT 1 FROM ProgressionTreeNodes WHERE ProgressionTreeNodeType = '{n}');" for n in content["roots"]]
            for kind, types in content["items"].items():
                lines += [f"INSERT OR IGNORE INTO ProgressionTreeNodeUnlocks (ProgressionTreeNodeType, TargetKind, TargetType, "
                          f"UnlockDepth) SELECT '{gate}', '{kind}', '{t}', 1 WHERE EXISTS (SELECT 1 FROM Types WHERE Type = '{t}');"
                          for t in types]
        # The engine does not enforce unlocks in a tree whose age is earlier than the world age (the reason
        # the joined trees take the world age). So in the Modern world an Exploration civ tree's items were
        # free for a civ still in Antiquity (Earth run 20261025-030928: Spain built both Casas without
        # Council of the Indies). Those items also get the Exploration Breakthrough, which is enforced.
        earlier_gated = [a for a in GATES if later(self.world, a)]
        for age in earlier_gated:
            trees = ", ".join(repr(t) for t in self.civ_content[age]["trees"])
            if trees:
                lines += [f"-- 2f. {NAME[age]} civ trees are earlier than this world: their items need the {NAME[age]} Breakthrough.",
                          "INSERT OR IGNORE INTO ProgressionTreeNodeUnlocks (ProgressionTreeNodeType, TargetKind, TargetType, UnlockDepth) "
                          f"SELECT DISTINCT '{GATES[age]}', u.TargetKind, u.TargetType, 1 FROM ProgressionTreeNodeUnlocks u "
                          "JOIN ProgressionTreeNodes n ON n.ProgressionTreeNodeType = u.ProgressionTreeNodeType "
                          f"WHERE n.ProgressionTree IN ({trees}) AND u.TargetKind IN ('KIND_UNIT', 'KIND_CONSTRUCTIBLE');"]
        # (Removed: rule 2h, which locked each later-age civ behind its age's Breakthrough so that a civ
        # behind its gate would keep its civ. The AI then took a locked civ or a civ of another age
        # (Persia -> Nepal, a Modern civ, in the Exploration world; iterations 20261025-040432, 043636).)
        lines += ["", "-- 2g. Upgrades across ages: the last unit of each class upgrades to the next age's base unit of",
                  "--     that class (the engine still needs the civ to be able to build the target: its gate)."]
        lines += [f"INSERT OR IGNORE INTO UnitUpgrades (Unit, UpgradeUnit) SELECT '{u}', '{v}' WHERE EXISTS "
                  f"(SELECT 1 FROM Units WHERE UnitType = '{u}') AND EXISTS (SELECT 1 FROM Units WHERE UnitType = '{v}');"
                  for u, v in self.cross_upgrades]
        lines += ["", "-- 2c. Units: every unit is kept as it is at a world transition (type, promotions, position).",
                  "--     Without this the engine keeps only commanders and remakes other military units as the",
                  "--     new age's type for their class (Unit_ShadowReplacements); a civ that cannot build that",
                  "--     type (behind its gate) lost the unit, and every remade unit lost its promotions.",
                  "INSERT OR IGNORE INTO Unit_TransitionRetains (UnitType) SELECT UnitType FROM Units;"]
        # (Removed: rule 2e, ObsoletesTraditionType = NULL. It did not stop the Modern-load policy loss
        # (iteration 20261025-001907) and made about 100 tradition upgrades stack inside each age.)
        lines += ["", "-- 3. Governments: the chooser lists every StartingGovernments row; offer the world age's.",
                  f"DELETE FROM StartingGovernments WHERE AgeType != '{self.world}';", ""]
        # The world age ends as in the base game (the transition is kept, without the reset),
        # unless a test sets the length.
        if args.age_points:
            points = args.age_points
            lines += [f"-- 4. Age length (test setting): the world age ends at {points} points.",
                      f"UPDATE AgeProgressions SET MaxPoints_Abbreviated = {points}, MaxPoints_Standard = {points}, "
                      f"MaxPoints_Long = {points} WHERE AgeType = '{self.world}';", ""]
        baseline_lines, defs, baseline_report = self.baseline_adapter()
        lines += ["-- 5. Baseline adapters."] + baseline_lines + [""]
        # The Exploration civ trait's free Cog came at the world transition to civs still in Antiquity,
        # and a second time to civs that got it at their gate (iteration 20261024-224137). One source:
        # the trait's grant, which now also needs the Exploration Breakthrough.
        # The engine drops some policies at a load although the civic that unlocked them stays completed
        # (U-POLICY: Drama and Poetry; U-POLICY-2: Castes, Conscription, Oratory, Priesthood, Survey at the
        # Modern load). No reset: a game modifier unlocks each main-tree policy again for every major
        # player that has completed its civic (EFFECT_PLAYER_UNLOCK_TRADITION, as the base game's crisis
        # stories use it).
        keep = policy_keep_modifiers(self.policy_unlocks)
        lines += ["-- 5c. Policies stay: each main-tree policy is unlocked again for a player that has its civic."]
        lines += [f"INSERT INTO GameModifiers (ModifierId) VALUES ('{m.get('id')}');" for m in keep]
        lines += [""]
        defs += keep
        # (Removed: rule 5d, a hidden unlock on each civ-tree civic that attached a modifier granting the
        # civic again after a reset. The engine rebuilds attached modifiers from the node states at a
        # load, so a civic the load resets loses its modifier too (iterations 052602, 053834).)
        # Half swap: a civ behind its gate still takes a new civ at a world transition (the engine's
        # choice). Its civ abilities wait for the civ's own Breakthrough: each modifier of a civ-only
        # trait of a later-age civ is a copy with that age's Breakthrough as an owner requirement.
        abil, abil_sql = self.civ_abilities
        lines += ["-- 5e. Civ abilities of a later-age civ need that age's Breakthrough (copies CA_GATE_<id>)."]
        lines += abil_sql + [""]
        defs += abil
        # Legacy cards at a world transition can grant a node of the new age (Modern: Academics, Steam
        # Engine, Military Science, three main-tree civics; Exploration: five). A civ behind its gate
        # got it at the load (iteration 20261025-075443: Maya, civ age Exploration, a Modern tech at
        # Modern turn 1). The card's modifier is a copy with that age's Breakthrough as an owner
        # requirement; run once, it grants the node when the civ reaches its gate.
        cards = card_grant_modifiers(self.game)
        lines += ["-- 5f. Legacy cards that grant a node of the new age wait for that age's Breakthrough."]
        lines += [f"UPDATE AdvancedStartCardEffects SET EffectType = '{m.get('id')}' WHERE EffectType = '{m.get('id')[len('CA_CARD_'):]}';" for m in cards]
        lines += [""]
        defs += cards
        ships = free_ship_modifiers(self.game)
        lines += ["-- 5b. Free ship: once per civ, at the later of its Exploration Breakthrough and the Exploration world."]
        lines += [f"UPDATE TraitModifiers SET ModifierId = '{m.get('id')}' WHERE ModifierId = '{m.get('id')[3:]}';" for m in ships]
        lines += [""]
        defs += ships
        if self.world == "AGE_ANTIQUITY":
            lines += ["-- 6. Exploration ocean movement rule (deep ocean ends the turn until Shipbuilding).",
                      "--    Only units that may enter deep ocean are affected: civs past their breakthrough."]
            src = self.game / "Base" / "modules" / "age-exploration" / "data" / "unit-movement.xml"
            for tbl in ET.parse(src).getroot():
                if c.strip_ns(tbl.tag) == "UnitMovementClassObstacles":
                    for row in tbl:
                        cols = ", ".join(row.attrib)
                        vals = ", ".join("1" if v == "true" else "0" if v == "false" else f"'{v}'" for v in row.attrib.values())
                        lines.append(f"INSERT OR IGNORE INTO UnitMovementClassObstacles ({cols}) VALUES ({vals});")
            lines.append("")
        if args.fast_test is not None:
            lines += [f"-- 7. Fast test: all techs of the joined tree cost {args.fast_test:g} x normal (minimum 1).",
                      f"UPDATE ProgressionTreeNodes SET Cost = MAX(1, CAST(Cost * {args.fast_test} AS INTEGER)) "
                      "WHERE ProgressionTree = 'TREE_TECHS_AQ';", ""]
        self.info = {"tech": tech_info, "civic": civic_info, "baseline": baseline_report}
        return "\n".join(lines), defs

    def catchup(self, removed: set[str]):
        """Catch-up research for the setup option: modifier definitions (always loaded, harmless
        when not attached) and, per option value, the SQL that attaches them to every major player.
        No requirement on the player: a civ that has the nodes gains nothing, so the bonus goes to
        civs behind the world, and to any civ that skipped an old node."""
        earlier = [a for a in AGES if later(self.world, a)]
        if not earlier:
            return [], {}, {}
        rows = self.sim.db.execute(
            "SELECT n.ProgressionTreeNodeType, t.SystemType FROM ProgressionTreeNodes n JOIN ProgressionTrees t "
            f"ON t.ProgressionTreeType = n.ProgressionTree WHERE t.AgeType IN ({', '.join('?' * len(earlier))}) "
            "ORDER BY t.SystemType, n.ProgressionTree, n.ProgressionTreeNodeType", earlier).fetchall()
        nodes = defaultdict(list)
        for n, system in rows:
            if n not in removed:
                nodes[system].append(n)
        # The Breakthrough into the world age ends the lag, so it counts as the end of the age before.
        nodes["SYSTEM_TECH"] += [GATES[a] for a in GATES if not later(a, self.world)]
        g = "{GameEffects}"
        defs, sql = [], {}
        for value, pct in CATCHUP.items():
            lines = [f"-- Catch-up research ({value}): +{pct}% toward the nodes of earlier ages, for every major player."]
            for system in sorted(nodes):
                for i in range(0, len(nodes[system]), CATCHUP_CHUNK):
                    mid = f"CA_CATCHUP_{pct}_{system[len('SYSTEM_'):]}_{i // CATCHUP_CHUNK}"
                    m = ET.Element(f"{g}Modifier", {"id": mid, "collection": "COLLECTION_MAJOR_PLAYERS",
                                                    "effect": "EFFECT_PLAYER_ADJUST_PROGRESSION_TREE_EFFICIENCY"})
                    ET.SubElement(m, f"{g}Argument", {"name": "SystemType"}).text = system
                    ET.SubElement(m, f"{g}Argument", {"name": "ProgressionTreeNodeType"}).text = \
                        ",".join(nodes[system][i:i + CATCHUP_CHUNK])
                    ET.SubElement(m, f"{g}Argument", {"name": "Percent"}).text = str(pct)
                    defs.append(m)
                    lines.append(f"INSERT INTO GameModifiers (ModifierId) VALUES ('{mid}');")
            sql[value] = "\n".join(lines) + "\n"
        return defs, sql, {s: len(v) for s, v in nodes.items()}

    def effects_xml(self, defs) -> ET.Element:
        root = ET.Element("{GameEffects}GameEffects")
        for age in GATES:
            m = ET.SubElement(root, "{GameEffects}Modifier", {"id": GATE_MODIFIER[age], "collection": "COLLECTION_OWNER",
                                                             "effect": "EFFECT_DO_NOTHING"})
            s = ET.SubElement(m, "{GameEffects}String", {"context": "Description"})
            s.text = f"LOC_{GATE_MODIFIER[age]}_DESCRIPTION"
        known = {GATE_MODIFIER[a] for a in GATES}
        for el in defs:
            if el.get("id") not in known:
                known.add(el.get("id"))
                root.append(el)
        return root


def cross_age_upgrades(sims: dict) -> list[tuple[str, str]]:
    """(unit, upgrade) links from the last military unit of each class in one age to the next age's
    base unit of that class (the next age's Unit_ShadowReplacements). The base game has no upgrade
    across ages because the transition remakes units; with every unit kept, an old army would stay
    at its old tier (units at the end of a chain in every run: Phalanx, Archer, Pikeman...).
    sims: the base game with DLC per age."""
    out = []
    for age, nxt in (("AGE_ANTIQUITY", "AGE_EXPLORATION"), ("AGE_EXPLORATION", "AGE_MODERN")):
        q = lambda sql: sims[age].db.execute(sql).fetchall()
        target = dict(sims[nxt].db.execute("SELECT Tag, UnitType FROM Unit_ShadowReplacements "
                                           "WHERE CoreClass = 'CORE_CLASS_MILITARY'").fetchall())
        has_up = {r[0] for r in q("SELECT Unit FROM UnitUpgrades")}
        tags = {}
        for typ, tag in q("SELECT Type, Tag FROM TypeTags ORDER BY Tag"):
            if tag in target:
                tags.setdefault(typ, tag)
        later_units = {r[0] for w, s in sims.items() if later(w, age) for r in s.db.execute("SELECT UnitType FROM Units")}
        for (unit,) in q("SELECT UnitType FROM Units WHERE CanTrain = 1 AND CoreClass = 'CORE_CLASS_MILITARY'"):
            if unit in has_up or unit in later_units or unit not in tags:
                continue  # has an upgrade, or the unit also belongs to a later age's data
            if target[tags[unit]] != unit:
                out.append((unit, target[tags[unit]]))
    return sorted(set(out))


def policy_unlocks(sims: dict) -> list[tuple[str, str, int]]:
    """(main-tree civic node, policy, unlock depth) of all ages: the policy slot traditions that a
    main-tree civic unlocks (crisis policies left out). The depth matters: 17 policies need the
    civic's mastery (UnlockDepth 2), and depth 1 would give them early (gotcha checker review 5).
    sims: the base game with DLC per age."""
    out = {}
    for sim in sims.values():
        for node, trad, depth in sim.db.execute(
                "SELECT u.ProgressionTreeNodeType, u.TargetType, u.UnlockDepth FROM ProgressionTreeNodeUnlocks u "
                "JOIN Traditions t ON t.TraditionType = u.TargetType WHERE u.TargetKind = 'KIND_TRADITION' "
                "AND t.CultureSlotType = 'POLICY_CULTURE_SLOT' AND t.IsCrisis = 0 "
                "AND u.ProgressionTreeNodeType LIKE 'NODE_CIVIC_%_MAIN_%'"):
            out.setdefault((node, trad, int(depth or 1)), None)
    return sorted(out)


def policy_keep_modifiers(pairs: list[tuple[str, str, int]]) -> list[ET.Element]:
    g = "{GameEffects}"
    out = []
    for i, (node, trad, depth) in enumerate(pairs):
        m = ET.Element(f"{g}Modifier", {"id": f"CA_KEEP_{trad}_{i}", "collection": "COLLECTION_MAJOR_PLAYERS",
                                        "effect": "EFFECT_PLAYER_UNLOCK_TRADITION", "permanent": "true"})
        reqs = ET.SubElement(m, f"{g}SubjectRequirements")
        r = ET.SubElement(reqs, f"{g}Requirement", {"type": "REQUIREMENT_PLAYER_HAS_COMPLETED_PROGRESSION_TREE_NODE"})
        ET.SubElement(r, f"{g}Argument", {"name": "ProgressionTreeNodeType"}).text = node
        ET.SubElement(r, f"{g}Argument", {"name": "MinDepth"}).text = str(depth)
        ET.SubElement(m, f"{g}Argument", {"name": "Tradition"}).text = trad
        out.append(m)
    return out


def card_grant_modifiers(game: Path) -> list[ET.Element]:
    """Copies (CA_CARD_<id>) of the card modifiers (advanced start and transition legacy cards) that
    grant a named Exploration or Modern node (EFFECT_PLAYER_GRANT_PROGRESSION, NODE_SPECIFIC), with
    that age's Breakthrough as an extra owner requirement."""
    g = "{GameEffects}"
    out = []
    for age, short in (("AGE_EXPLORATION", "EX"), ("AGE_MODERN", "MO")):
        data = game / "Base" / "modules" / age.lower().replace("_", "-") / "data"
        for f in (data / "advanced-start-gameeffects.xml", data / "age-transition-gameeffects.xml"):
          for el in ET.parse(f).getroot():
            if c.strip_ns(el.tag) != "Modifier" or el.get("effect") != "EFFECT_PLAYER_GRANT_PROGRESSION":
                continue
            args = {a.get("name"): a.text for a in el if c.strip_ns(a.tag) == "Argument"}
            # Boosts (AgeTransitionBoostableNodes) complete nothing; only grants of a named node.
            if args.get("FreeProgressionType") != "FREE_PROGRESSION_NODE_SPECIFIC" or f"_{short}_" not in (args.get("NodeType") or ""):
                continue
            m = ET.fromstring(ET.tostring(el))
            m.set("id", f"CA_CARD_{el.get('id')}")
            reqs = next((ch for ch in m if c.strip_ns(ch.tag) == "OwnerRequirements"), None)
            if reqs is None:
                reqs = ET.Element(f"{g}OwnerRequirements")
                m.insert(0, reqs)
            r = ET.SubElement(reqs, f"{g}Requirement", {"type": "REQUIREMENT_PLAYER_HAS_COMPLETED_PROGRESSION_TREE_NODE"})
            ET.SubElement(r, f"{g}Argument", {"name": "ProgressionTreeNodeType"}).text = GATES[age]
            ET.SubElement(r, f"{g}Argument", {"name": "MinDepth"}).text = "1"
            out.append(m)
    return out


def civ_ability_modifiers(game: Path, sims: dict) -> tuple[list[ET.Element], list[str], list[str]]:
    """Copies (CA_GATE_<id>) of the modifiers of each trait that only one Exploration or Modern civ has,
    with that age's Breakthrough as an extra owner requirement; the TraitModifiers updates; and the
    modifier ids left out (not found in the game effects files, or an owner set that tests ANY).
    sims: the base game with DLC per age."""
    g = "{GameEffects}"
    found = {}
    files = sorted((game / "Base" / "modules").glob("*/data/**/*.xml")) + sorted((game / "DLC").glob("*/modules/**/*.xml"))
    for f in files:
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError:
            continue
        if c.strip_ns(root.tag) != "GameEffects":
            continue
        for el in root:
            if c.strip_ns(el.tag) == "Modifier" and el.get("id"):
                found.setdefault(el.get("id"), el)
    out, sql, skipped, done = [], [], [], set()
    for age in ("AGE_EXPLORATION", "AGE_MODERN"):
        db = sims[age].db
        civs = {r[0] for r in db.execute("SELECT CivilizationType FROM LegacyCivilizations WHERE Age = ?", (age,))}
        pairs = db.execute("SELECT CivilizationType, TraitType FROM CivilizationTraits").fetchall()
        uses = {}
        for civ, trait in pairs:
            uses[trait] = uses.get(trait, 0) + 1
        traits = sorted({t for civ, t in pairs if civ in civs and uses[t] == 1})
        for trait, mid in db.execute("SELECT TraitType, ModifierId FROM TraitModifiers WHERE TraitType IN (%s)"
                                     % ",".join("?" * len(traits)), traits).fetchall():
            el = found.get(mid)
            reqs = None if el is None else next((ch for ch in el if c.strip_ns(ch.tag) == "OwnerRequirements"), None)
            if el is None or (reqs is not None and reqs.get("type", "REQUIREMENTSET_TEST_ALL") != "REQUIREMENTSET_TEST_ALL"):
                skipped.append(mid)
                continue
            if mid not in done:
                done.add(mid)
                m = ET.fromstring(ET.tostring(el))
                m.set("id", f"CA_GATE_{mid}")
                reqs = next((ch for ch in m if c.strip_ns(ch.tag) == "OwnerRequirements"), None)
                if reqs is None:
                    reqs = ET.Element(f"{g}OwnerRequirements")
                    m.insert(0, reqs)
                r = ET.SubElement(reqs, f"{g}Requirement", {"type": "REQUIREMENT_PLAYER_HAS_COMPLETED_PROGRESSION_TREE_NODE"})
                ET.SubElement(r, f"{g}Argument", {"name": "ProgressionTreeNodeType"}).text = GATES[age]
                ET.SubElement(r, f"{g}Argument", {"name": "MinDepth"}).text = "1"
                out.append(m)
            sql.append(f"UPDATE TraitModifiers SET ModifierId = 'CA_GATE_{mid}' WHERE TraitType = '{trait}' AND ModifierId = '{mid}';")
    return out, sql, sorted(set(skipped))


# The Exploration civ trait's free ship, in the base game and as the Pirate Republic DLC changes it.
FREE_SHIPS = ["TRAIT_MOD_FREE_SHIP", "TRAIT_MOD_FREE_SHIP_REDUX", "TRAIT_MOD_FREE_SLOOP"]


def free_ship_modifiers(game: Path) -> list[ET.Element]:
    """Copies (id CA_<id>) of each free-ship modifier found in the Exploration and DLC game effects,
    with the Exploration Breakthrough as an extra owner requirement."""
    g = "{GameEffects}"
    files = sorted((game / "Base" / "modules" / "age-exploration" / "data").glob("*gameeffects*.xml"))
    files += sorted((game / "DLC").glob("*/modules/data/*gameeffects*.xml"))
    found = {}
    for f in files:
        for el in ET.parse(f).getroot():
            if c.strip_ns(el.tag) == "Modifier" and el.get("id") in FREE_SHIPS:
                found.setdefault(el.get("id"), el)
    out = []
    for mid, el in found.items():
        m = ET.fromstring(ET.tostring(el))
        m.set("id", f"CA_{mid}")
        reqs = next((ch for ch in m if c.strip_ns(ch.tag) == "OwnerRequirements"), None)
        if reqs is None:
            reqs = ET.Element(f"{g}OwnerRequirements")
            m.insert(0, reqs)
        r = ET.SubElement(reqs, f"{g}Requirement", {"type": "REQUIREMENT_PLAYER_HAS_COMPLETED_PROGRESSION_TREE_NODE"})
        ET.SubElement(r, f"{g}Argument", {"name": "ProgressionTreeNodeType"}).text = GATES["AGE_EXPLORATION"]
        ET.SubElement(r, f"{g}Argument", {"name": "MinDepth"}).text = "1"
        out.append(m)
    return out


def text_xml() -> str:
    rows = []
    for age, gate in GATES.items():
        rows += [(f"LOC_{gate}_NAME", f"{NAME[age]} Breakthrough"),
                 (f"LOC_{gate}_DESCRIPTION", f"Your civilization enters the {NAME[age]} Age. Opens the {NAME[age]} technologies."),
                 (f"LOC_{GATE_MODIFIER[age]}_DESCRIPTION", f"Enter the {NAME[age]} Age. Opens the {NAME[age]} technologies.")]
    rows += [("LOC_CA_YOUR_AGE", "Your age"), ("LOC_CA_WORLD_AGE", "World age")]
    rows += [("LOC_CA_CATCHUP_NAME", "Catch-up Research"),
             ("LOC_CA_CATCHUP_DESCRIPTION",
              "Continuous Ages: after each world age transition, all techs and civics of earlier ages, and the "
              "Breakthrough into the world age, are easier to research for every civilization."),
             ("LOC_CA_CATCHUP_OFF_NAME", "Off"),
             ("LOC_CA_CATCHUP_OFF_DESCRIPTION", "No change to research."),
             ("LOC_CA_CATCHUP_50_NAME", "+50%"),
             ("LOC_CA_CATCHUP_50_DESCRIPTION", "These nodes cost two thirds (about a third fewer turns)."),
             ("LOC_CA_CATCHUP_100_NAME", "+100%"),
             ("LOC_CA_CATCHUP_100_DESCRIPTION", "These nodes cost half (half the turns).")]
    body = "\n".join(f'\t\t<Row Tag="{t}">\n\t\t\t<Text>{v}</Text>\n\t\t</Row>' for t, v in rows)
    return f'<?xml version="1.0" encoding="utf-8"?>\n<Database>\n\t<EnglishText>\n{body}\n\t</EnglishText>\n</Database>\n'


def config_xml() -> str:
    """The Catch-up Research setup option (game setup, Game Options)."""
    values = [("CA_CATCHUP_OFF", "LOC_CA_CATCHUP_OFF")] + [(v, f"LOC_{v}") for v in CATCHUP]
    rows = "\n".join(f'\t\t<Row Domain="CaCatchUpValues" Value="{v}" Name="{loc}_NAME" Description="{loc}_DESCRIPTION" '
                     f'SortIndex="{i}"/>' for i, (v, loc) in enumerate(values))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Database>
	<Parameters>
		<Row ParameterID="{CATCHUP_KEY}" Name="LOC_CA_CATCHUP_NAME" Description="LOC_CA_CATCHUP_DESCRIPTION" Domain="CaCatchUpValues" Hash="0" DefaultValue="CA_CATCHUP_OFF" ConfigurationGroup="Game" ConfigurationKey="{CATCHUP_KEY}" GroupId="GameOptions" ChangeableAfterGameStart="0" SortIndex="148"/>
	</Parameters>
	<DomainValues>
{rows}
	</DomainValues>
</Database>
"""


def item_lines(items, indent=5):
    return "\n".join("\t" * indent + f"<Item>{i}</Item>" for i in items)


def modinfo_xml(builds: list[WorldBuild], checks: bool, fast, game: Path) -> str:
    name = MOD_NAME if fast is None else f"{MOD_NAME} (FAST TEST: techs at {fast:.0%} cost)"
    crit = "\n".join(f'\t\t<Criteria id="world-{b.w}">\n\t\t\t<AgeInUse>{b.world}</AgeInUse>\n\t\t</Criteria>' for b in builds)
    groups = []
    for b in builds:
        for value, item in b.catchup_items.items():
            cid = f"world-{b.w}-catchup-{CATCHUP[value]}"
            crit += (f'\n\t\t<Criteria id="{cid}">\n\t\t\t<AgeInUse>{b.world}</AgeInUse>\n'
                     f'\t\t\t<ConfigurationValueMatches>\n\t\t\t\t<Group>Game</Group>\n'
                     f'\t\t\t\t<ConfigurationId>{CATCHUP_KEY}</ConfigurationId>\n\t\t\t\t<Value>{value}</Value>\n'
                     f'\t\t\t</ConfigurationValueMatches>\n\t\t</Criteria>')
            groups.append(f"""		<ActionGroup id="ca-{b.w}-catchup-{CATCHUP[value]}" scope="game" criteria="{cid}">
			<Properties><LoadOrder>210</LoadOrder></Properties>
			<Actions>
				<UpdateDatabase>
					<Item>{item}</Item>
				</UpdateDatabase>
			</Actions>
		</ActionGroup>""")
        groups.append(f"""		<ActionGroup id="ca-{b.w}-content" scope="game" criteria="world-{b.w}">
			<Properties><LoadOrder>100</LoadOrder></Properties>
			<Actions>
				<UpdateDatabase>
{item_lines(b.items)}
				</UpdateDatabase>
			</Actions>
		</ActionGroup>
		<ActionGroup id="ca-{b.w}-rules" scope="game" criteria="world-{b.w}">
			<Properties><LoadOrder>200</LoadOrder></Properties>
			<Actions>
				<UpdateDatabase>
					<Item>data/{b.w}/continuous-ages-effects.xml</Item>
					<Item>data/{b.w}/continuous-ages-rules.sql</Item>
				</UpdateDatabase>
			</Actions>
		</ActionGroup>
		<ActionGroup id="ca-{b.w}-text" scope="game" criteria="world-{b.w}">
			<Actions>
				<UpdateText>
{item_lines(b.text_items)}
				</UpdateText>
			</Actions>
		</ActionGroup>""")
    checks_group = """
		<ActionGroup id="ca-checks" scope="game" criteria="always">
			<Actions>
				<UIScripts>
					<Item>ui/ca-checks.js</Item>
				</UIScripts>
			</Actions>
		</ActionGroup>""" if checks else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Mod id="{MOD_ID}" version="1" xmlns="ModInfo">
	<Properties>
		<Name>{name}</Name>
		<Description>{escape(MOD_DESCRIPTION.format(mod_version=MOD_VERSION, game_version=game_version(game)["product_version"] or "(unknown version)"))}</Description>
		<Authors>Continuous Ages project</Authors>
		<AffectsSavedGames>1</AffectsSavedGames>
	</Properties>
	<Dependencies>
		<Mod id="base-standard" title="LOC_MODULE_BASE_STANDARD_NAME" />
	</Dependencies>
	<References>
		<Mod id="age-antiquity" title="LOC_MODULE_AGE_ANTIQUITY_NAME" />
		<Mod id="age-exploration" title="LOC_MODULE_AGE_EXPLORATION_NAME" />
		<Mod id="age-modern" title="LOC_MODULE_AGE_MODERN_NAME" />
	</References>
	<ActionCriteria>
{crit}
		<Criteria id="always">
			<AlwaysMet></AlwaysMet>
		</Criteria>
	</ActionCriteria>
	<ActionGroups>
{chr(10).join(groups)}
		<ActionGroup id="ca-ui" scope="game" criteria="always">
			<Actions>
				<UIScripts>
					<Item>ui/ca-civ-age.js</Item>
				</UIScripts>
			</Actions>
		</ActionGroup>
		<ActionGroup id="ca-transition" scope="game" criteria="always">
			<Actions>
				<ImportFiles>
					<Item>scripts/age-transition-post-load.js</Item>
				</ImportFiles>
			</Actions>
		</ActionGroup>{checks_group}
		<ActionGroup id="ca-text" scope="game" criteria="always">
			<Actions>
				<UpdateText>
					<Item>text/en_us/ContinuousAgesText.xml</Item>
				</UpdateText>
			</Actions>
		</ActionGroup>
		<ActionGroup id="ca-shell-text" scope="shell" criteria="always">
			<Actions>
				<UpdateDatabase>
					<Item>config/continuous-ages-config.xml</Item>
				</UpdateDatabase>
				<UpdateText>
					<Item>text/en_us/ContinuousAgesText.xml</Item>
				</UpdateText>
			</Actions>
		</ActionGroup>
	</ActionGroups>
</Mod>
"""


def age_starter_items(sims: dict) -> dict:
    """Generic units and buildings that a later age makes available at its start (no unlock row).
    With all ages loaded, every civ could build them from turn 1, so they get their age's gate
    as their unlock. Civ-unique items stay as they are: their civ's trait gates them.
    sims: the base game (no mod) per world age, before any content is added."""
    def items(sim):
        q = lambda sql: {r[0] for r in sim.db.execute(sql)}
        unlocked = q("SELECT TargetType FROM ProgressionTreeNodeUnlocks")
        units = q("SELECT UnitType FROM Units WHERE CanTrain = 1 AND TraitType IS NULL")
        buildings = q("SELECT c.ConstructibleType FROM Constructibles c JOIN Buildings b USING (ConstructibleType) "
                      "WHERE c.ConstructibleClass = 'BUILDING' AND b.TraitType IS NULL")
        return {"KIND_UNIT": units - unlocked, "KIND_CONSTRUCTIBLE": buildings - unlocked,
                "all": q("SELECT UnitType FROM Units UNION SELECT ConstructibleType FROM Constructibles")}
    per_age = {a: items(s) for a, s in sims.items()}
    out = {}
    for age in GATES:
        # New in this age: not in any earlier age's data. (A later age can keep an older item,
        # for example the Modern data keeps the Exploration Bazaar.)
        earlier = set().union(*(per_age[o]["all"] for o in AGES[:AGES.index(age)]))
        out[age] = {k: sorted(per_age[age][k] - earlier) for k in ("KIND_UNIT", "KIND_CONSTRUCTIBLE")}
    return out


def civ_age_content(sims: dict) -> dict:
    """Civ content of the later ages: the first nodes of every civic tree of that age other than
    the main tree (each civ's unique tree, the Test of Time tree, the branch trees), and the
    unique units, buildings and improvements of that age's civs that have no unlock row. A civ's
    age is the age of its unique tree (TREE_CIVICS_<age>_<civ>). At a world transition a civ
    behind its gate still gets a civ of the new age, or keeps its civ and gets the Test of Time
    tree and another civ's tree (Rome: Norman, then Great Britain), so this content needs the gate
    of that age (iterations 20261024-205920 and 20261024-214035).
    sims: the base game with DLC (no mod) per age."""
    out = {}
    for age in GATES:
        q = lambda sql, *a: sims[age].db.execute(sql, a).fetchall()
        civs = {r[0] for r in q("SELECT CivilizationType FROM Civilizations")}
        all_trees = [r[0] for r in q("SELECT ProgressionTreeType FROM ProgressionTrees WHERE SystemType = "
                                     "'SYSTEM_CULTURE' AND AgeType = ?", age) if r[0] not in CIVIC_TREES]
        trees = {}
        for tree in all_trees:
            civ = "CIVILIZATION_" + tree[len(f"TREE_CIVICS_{SHORT[age]}_"):]
            if tree.startswith(f"TREE_CIVICS_{SHORT[age]}_") and civ in civs:
                trees[tree] = civ
        tree_list = ", ".join(repr(t) for t in all_trees)
        roots = [r[0] for r in q(f"SELECT ProgressionTreeNodeType FROM ProgressionTreeNodes WHERE ProgressionTree IN "
                                 f"({tree_list}) AND ProgressionTreeNodeType NOT IN (SELECT Node FROM ProgressionTreePrereqs)")]
        # A trait of exactly one civ of this age.
        civ_list = ", ".join(repr(v) for v in trees.values())
        traits = {r[0] for r in q(f"SELECT TraitType FROM CivilizationTraits WHERE CivilizationType IN ({civ_list}) "
                                  "AND TraitType IN (SELECT TraitType FROM CivilizationTraits GROUP BY TraitType "
                                  "HAVING COUNT(*) = 1)")}
        unlocked = {r[0] for r in q("SELECT TargetType FROM ProgressionTreeNodeUnlocks")}
        items = {"KIND_UNIT": set(), "KIND_CONSTRUCTIBLE": set()}
        for table, key, kind in (("Units", "UnitType", "KIND_UNIT"), ("Buildings", "ConstructibleType", "KIND_CONSTRUCTIBLE"),
                                 ("Improvements", "ConstructibleType", "KIND_CONSTRUCTIBLE")):
            items[kind] |= {t for t, tr in q(f"SELECT {key}, TraitType FROM {table} WHERE TraitType IS NOT NULL")
                            if tr in traits and t not in unlocked}
        out[age] = {"trees": sorted(all_trees), "roots": sorted(roots), "items": {k: sorted(v) for k, v in items.items()}}
    return out


def fk_set(sim):
    return {(t, p, tuple(sorted(v.items()))) for t, p, v in sim.foreign_key_violations()}


def validate(game, world):
    sim = c.Simulator(game)
    mods = c.load_base_modules(game, include_dlc=True) + [c.parse_modinfo(OUT / f"{MOD_ID}.modinfo")]
    # With the Catch-up Research option on, so that its rules are validated too (both values have the same rows).
    config = {f"Game/{CATCHUP_KEY}": "CA_CATCHUP_100"}
    for path in c.database_items(c.applicable_groups(mods, world, config)):
        sim.apply_file(path)
    return sim


def prune_dangling(b: WorldBuild, violations) -> int:
    removed = 0
    for item in b.items:
        path = OUT / item
        if path.suffix.lower() != ".xml":
            continue
        root = ET.parse(path).getroot()
        if c.strip_ns(root.tag) != "Database":
            continue
        changed = False
        for tbl_el in list(root):
            for table, parent, values in violations:
                if c.strip_ns(tbl_el.tag).lower() != table.lower():
                    continue
                for op in list(tbl_el):
                    attrs = {k.lower(): v for k, v in op.attrib.items()}
                    if all(str(attrs.get(k.lower())) == str(v) for k, v in values):
                        tbl_el.remove(op)
                        changed = True
                        removed += 1
                        b.counters["dangling"][f"{table} -> {parent}"] += 1
            if len(tbl_el) == 0:
                root.remove(tbl_el)
        if changed:
            write_xml(root, path)
    return removed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", type=Path, default=c.DEFAULT_GAME_DIR)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--checks", action="store_true", help="add the in-game check script and the automation test")
    ap.add_argument("--fast-test", nargs="?", const=0.1, type=float, metavar="FACTOR")
    ap.add_argument("--age-points", type=int, default=None, metavar="N",
                    help="each world age ends at N age-progress points (test setting)")
    ap.add_argument("--package", action="store_true",
                    help="release build: write build-info.json and zip the mod to build/dist (refused with test settings)")
    args = ap.parse_args()
    game = args.game_dir
    if args.package and (args.checks or args.fast_test is not None or args.age_points):
        ap.error("--package makes a release build: leave out --checks, --fast-test and --age-points")

    OUT.mkdir(parents=True, exist_ok=True)
    for child in OUT.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()

    base_mods = c.load_base_modules(game)
    all_mods = c.load_base_modules(game, include_dlc=True)
    builds = [WorldBuild(game, world, args) for world in AGES]
    starters = age_starter_items({b.world: b.sim for b in builds})
    dlc_sims = {a: c.simulate(game, a, include_dlc=True) for a in AGES}
    civ_content = civ_age_content({a: dlc_sims[a] for a in GATES})
    pol_unlocks = policy_unlocks(dlc_sims)
    abil_defs, abil_sql, abil_skipped = civ_ability_modifiers(game, dlc_sims)
    print(f"civ abilities gated: {len(abil_defs)} modifiers, {len(abil_sql)} trait rows; left out: {abil_skipped}")
    upgrades = cross_age_upgrades(dlc_sims)
    for b in builds:
        b.starters = starters
        b.civ_content = civ_content
        b.policy_unlocks = pol_unlocks
        b.civ_abilities = (abil_defs, abil_sql)
        b.cross_upgrades = upgrades
        world = b.world
        groups = other_age_groups(base_mods, world)
        b.copy_content(groups)
        b.copy_text(groups, all_mods)
        sql, defs = b.rules()
        (OUT / "data" / b.w).mkdir(parents=True, exist_ok=True)
        (OUT / "data" / b.w / "continuous-ages-rules.sql").write_text(sql, encoding="utf-8")
        catchup_defs, catchup_sql, b.catchup_nodes = b.catchup(set(b.info["tech"]["removed_repeatable"])
                                                               | set(b.info["civic"]["removed_repeatable"]))
        defs += catchup_defs
        b.catchup_items = {}
        for value, text in catchup_sql.items():
            b.catchup_items[value] = f"data/{b.w}/continuous-ages-catchup-{CATCHUP[value]}.sql"
            (OUT / b.catchup_items[value]).write_text(text, encoding="utf-8")
        write_xml(b.effects_xml(defs), OUT / "data" / b.w / "continuous-ages-effects.xml")

    (OUT / "text" / "en_us").mkdir(parents=True, exist_ok=True)
    (OUT / "text" / "en_us" / "ContinuousAgesText.xml").write_text(text_xml(), encoding="utf-8")
    (OUT / "config").mkdir(parents=True, exist_ok=True)
    (OUT / "config" / "continuous-ages-config.xml").write_text(config_xml(), encoding="utf-8")
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "scripts" / "age-transition-post-load.js").write_text(transition_script(game), encoding="utf-8")
    (OUT / "ui").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).parent / "ui" / "ca-civ-age.js", OUT / "ui" / "ca-civ-age.js")
    if args.checks:
        for f in ("ca-checks.js", "ca-automation.js"):
            shutil.copyfile(Path(__file__).parent / "checks" / f, OUT / "ui" / f)
    (OUT / f"{MOD_ID}.modinfo").write_text(modinfo_xml(builds, args.checks, args.fast_test, game), encoding="utf-8")

    # Validate each world age: base modules + DLC + the mod, in load order.
    summary = []
    for b in builds:
        baseline_fk = fk_set(c.simulate(game, b.world, include_dlc=True))
        check = validate(game, b.world)
        new_fk = sorted(fk_set(check) - baseline_fk)
        for _ in range(8):
            if not new_fk or not prune_dangling(b, [(t, p, v) for t, p, v in new_fk]):
                break
            check = validate(game, b.world)
            new_fk = sorted(fk_set(check) - baseline_fk)
        trees = check.db.execute("SELECT ProgressionTree, COUNT(*) FROM ProgressionTreeNodes WHERE ProgressionTree "
                                 "IN ('TREE_TECHS_AQ','TREE_CIVICS_AQ_MAIN') GROUP BY ProgressionTree").fetchall()
        unclassified = sorted({t for _, t, k, _ in b.log["systems"] if k == "unclassified"})
        b.result = {"issues": len(check.issues), "new_fk": len(new_fk), "trees": trees, "unclassified": unclassified,
                    "issue_samples": [f"{i.kind}: {c.rel(Path(i.file))} {i.table}: {i.detail}" for i in check.issues[:10]],
                    "fk_samples": [f"{t} -> {p}: {dict(v)}" for t, p, v in new_fk[:10]]}
        summary.append(f"  world {b.w}: files {len(b.items)}, text {len(b.text_items)}; validation: {len(check.issues)} load issues, "
                       f"{len(new_fk)} new foreign-key violations; joined trees {trees}; unclassified tables: {unclassified or 'none'}")
    write_report(builds)
    print(f"Built {OUT}")
    print("\n".join(summary))
    print("catch-up nodes per world: " + "; ".join(f"{b.w} {b.catchup_nodes}" for b in builds if b.catchup_nodes))
    if args.package:
        bad = [b.w for b in builds if b.result["issues"] or b.result["new_fk"]]
        if bad:
            raise SystemExit(f"Not packaged: validation issues in world {', '.join(bad)} (see the build report)")
        print(f"Packaged {package(game)}")
    if args.install:
        for old in [MOD_ID] + OLD_MOD_IDS:
            if (MODS_DIR / old).exists():
                shutil.rmtree(MODS_DIR / old)
        shutil.copytree(OUT, MODS_DIR / MOD_ID)
        print(f"Installed to {MODS_DIR / MOD_ID}")


def game_version(game: Path) -> dict:
    """The installed game's version: the executable's product version (Windows), the Steam build id,
    and the DLC folders the build saw."""
    info = {"product_version": None, "steam_build": None,
            "dlc": sorted(d.name for d in (game / "DLC").iterdir() if d.is_dir()) if (game / "DLC").exists() else []}
    exe = game / "Base" / "Binaries" / "Win64" / "Civ7_Win64_DX12_FinalRelease.exe"
    if os.name == "nt" and exe.exists():
        import ctypes
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(str(exe), None)
        if size:
            buf = ctypes.create_string_buffer(size)
            ver.GetFileVersionInfoW(str(exe), 0, size, buf)
            ptr, n = ctypes.c_void_p(), ctypes.c_uint()
            if ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)):
                ms, ls = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint32))[2:4]  # VS_FIXEDFILEINFO file version
                info["product_version"] = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    manifest = game.parent.parent / "appmanifest_1295660.acf"
    if manifest.exists():
        found = re.search(r'"buildid"\s+"(\d+)"', manifest.read_text(encoding="utf-8", errors="replace"))
        info["steam_build"] = found.group(1) if found else None
    return info


def package(game: Path) -> Path:
    """Writes build-info.json into the mod and zips the mod folder to build/dist (the folder a player
    puts in the Mods folder, and the folder to upload to the Steam Workshop)."""
    repo = Path(__file__).resolve().parent.parent
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout.strip()
    version = game_version(game)
    info = {"mod": MOD_ID, "mod_version": MOD_VERSION, "game": version,
            "git_commit": git("rev-parse", "--short", "HEAD") or None,
            "git_dirty": bool(git("status", "--porcelain", "generator")),
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (OUT / "build-info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    dist = OUT.parent / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    zip_path = dist / f"{MOD_ID}-{MOD_VERSION}-civ7-{version['product_version'] or 'unknown'}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.rglob("*")):
            if f.is_file() and f.relative_to(OUT) != Path("REPORT.md"):  # the build report is for the developer
                z.write(f, Path(MOD_ID) / f.relative_to(OUT))
    if info["git_dirty"]:
        print("Warning: the generator has uncommitted changes (build-info.json: git_dirty)")
    return zip_path


def write_report(builds) -> None:
    out = [f"# {MOD_NAME}: build report", ""]
    for b in builds:
        r = b.result
        out += [f"## World age {NAME[b.world]}", "",
                f"- Content files from other ages: {len(b.items)}; text files: {len(b.text_items)}",
                f"- Validation: {r['issues']} load issues, {r['new_fk']} new foreign-key violations",
                f"- Joined trees: {r['trees']}",
                f"- Unclassified tables (not loaded; review): {', '.join(r['unclassified']) or 'none'}"]
        for age, i in b.info["tech"].items():
            if age in GATES:
                out.append(f"- {NAME[age]} gate: cost {i['gate_cost']}; needs {', '.join(i['leaves'])}; opens {', '.join(i['roots'])}")
        out.append(f"- Removed repeatable nodes: techs {b.info['tech']['removed_repeatable']}, civics {b.info['civic']['removed_repeatable']}")
        out += [f"- Baseline {NAME[a]}: {t}" for a, t in b.info["baseline"]]
        out += [f"- {NAME[a]} civ content at the gate: {len(v['trees'])} unique trees ({len(v['roots'])} first nodes); "
                f"items without unlock: {', '.join(v['items']['KIND_UNIT'] + v['items']['KIND_CONSTRUCTIBLE']) or 'none'}"
                for a, v in b.civ_content.items()]
        out += [f"- Issue: {s}" for s in r["issue_samples"]] + [f"- Broken reference: {s}" for s in r["fk_samples"]]
        for key, title in [("trait_rows", "Trait-modifier rows left out"), ("dropped_rows", "Rows whose key exists (kept the world's)"),
                           ("system_types", "System types left with their age"), ("dangling", "Rows pointing to content not loaded"),
                           ("stripped", "Balance changes removed (Update/Delete/Replace)")]:
            if b.counters[key]:
                total = sum(b.counters[key].values())
                out += ["", f"### {title} ({total})", ""] + [f"- {k}: {n}" for k, n in b.counters[key].most_common(25)]
        sys_rows = Counter()
        for f, t, k, n in b.log["systems"]:
            sys_rows[t] += n
        out += ["", f"### System tables left with their age ({sum(sys_rows.values())} rows)", "",
                ", ".join(f"{t} {n}" for t, n in sorted(sys_rows.items())), ""]
        if b.log["errors"]:
            out += ["### Errors", ""] + [f"- {f} {t}: {e}" for f, t, e in b.log["errors"][:30]] + [""]
    (OUT / "REPORT.md").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
