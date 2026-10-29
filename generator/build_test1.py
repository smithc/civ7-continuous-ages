"""Build the "Continuous Ages - Test 1" mod from the installed game files.

Test 1 checks the continuous core in an Antiquity game:
  * all Exploration content is loaded while the global age stays Antiquity,
  * the Exploration techs join the Antiquity tech tree behind one gate,
  * the age does not end.

The Exploration files are copied from the game, with three changes:
  * Update, Delete and Replace operations are removed (they are balance changes
    for the start of Exploration and would change Antiquity content),
  * rows whose key already exists in an Antiquity game are removed,
  * GameEffects entries with an id that already exists are removed.
Every change is listed in build/<mod>/REPORT.md.

Usage: python build_test1.py [--game-dir DIR] [--install] [--fast-test [FACTOR]]

--fast-test multiplies the cost of every tech in the joined tree by FACTOR
(default 0.1), so that a playtest reaches the gate in a short session.
"""
from __future__ import annotations

import argparse
import os
import fnmatch
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import civ7data as c
import classification as cls

MOD_ID = "continuous-ages-test1"
MOD_NAME = "Continuous Ages - Test 1"
REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "build" / MOD_ID
# The game scans this folder for user mods (see Modding.log: "Discovering new mods").
MODS_DIR = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "Firaxis Games" / "Sid Meier's Civilization VII" / "Mods")

GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH"
GATE_MODIFIER = "MOD_CA_EXPLORATION_BREAKTHROUGH"
GATE_COST_FACTOR = 1.2   # gate cost = factor x most expensive Antiquity tech
NEVER_ENDS_POINTS = 100000

# Files that belong to the start of an age, not to its content.
EXCLUDE_PATTERNS = [
    "age-active.xml",            # sets Ages.Active for the age
    "advanced-start*.xml",       # legacy cards at an age start
    "age-transition*.xml",       # transition rules
    "advisory.xml",              # advisor text for the age
    "crisis-stages.xml",         # crises (test 3)
    "narrative-crises-*.xml",
    "metaprogression*.xml",      # per-age player challenges
    "goody-huts.xml",            # duplicate types with Antiquity
    "movies.xml",                # age intro movies
]

# Exploration-only text that belongs to the age start, not to its content.
TEXT_EXCLUDE = {"AdvisorText.xml", "AgeEndingWarning.xml", "TutorialText.xml"}

# Files matched with their module: the Exploration versions of civ abilities for
# civs of other ages (used when a civ persists into Exploration). In a continuous
# game these belong behind that civ's own breakthrough, not in every game.
EXCLUDE_MODULE_PATTERNS = [
    "age-antiquity/data/civilizations-exploration*.xml",
    "age-modern/data/civilizations-exploration*.xml",
]

ET.register_namespace("", "GameEffects")


def excluded(module: str, item: str) -> bool:
    name = item.rsplit("/", 1)[-1]
    return (any(fnmatch.fnmatch(name, p) for p in EXCLUDE_PATTERNS)
            or any(fnmatch.fnmatch(f"{module}/{item}", p) for p in EXCLUDE_MODULE_PATTERNS))


def exploration_only_groups(mods):
    aq = {(m.id, g.id) for m, g in c.applicable_groups(mods, "AGE_ANTIQUITY")}
    return [(m, g) for m, g in c.applicable_groups(mods, "AGE_EXPLORATION") if (m.id, g.id) not in aq]


def write_xml(root: ET.Element, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="\t")
    ET.ElementTree(root).write(dest, encoding="utf-8", xml_declaration=True)


def copy_transformed(sim: c.Simulator, src: Path, dest: Path, log: dict) -> None:
    """Apply src to the simulation and write a copy without the removed operations."""
    name = c.rel(src)
    if src.suffix.lower() == ".sql":
        sim.apply_file(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return
    root = ET.parse(src).getroot()
    changed = False
    if c.strip_ns(root.tag) == "GameEffects":
        for el in list(root):
            ident = el.get("id")
            store = sim.modifiers if c.strip_ns(el.tag) == "Modifier" else sim.requirement_sets
            if ident in store:
                root.remove(el)
                changed = True
                log["dropped_effects"].append((name, c.strip_ns(el.tag), ident))
        sim.apply_game_effects(name, root)
    else:
        for tbl_el in list(root):  # a copy: empty table elements are removed below
            tname = c.strip_ns(tbl_el.tag)
            table = sim._table(tname)
            klass = cls.table_class(tname, src.name)
            if klass != "content":
                # Systems stay with their own age (content per civ, systems per world).
                log["systems"].append((name, tname, klass, len(tbl_el)))
                root.remove(tbl_el)
                changed = True
                continue
            for op in list(tbl_el):
                if tname == "TraitModifiers" and c.strip_ns(op.tag) in ("Row", "InsertOrIgnore"):
                    # Only real civ abilities are content. A trait shared by several civs or leaders
                    # (TRAIT_ANACHRONISTIC_CIV, attribute traits) carries the age baseline for all of
                    # them (for example ocean travel in Exploration), which is a system.
                    trait = op.get("TraitType") or (op.findtext("TraitType") or "").strip()
                    owners = sim.db.execute(
                        "SELECT (SELECT COUNT(*) FROM CivilizationTraits WHERE TraitType = ?) + "
                        "(SELECT COUNT(*) FROM LeaderTraits WHERE TraitType = ?)", (trait, trait)).fetchone()[0]
                    if owners != 1:
                        tbl_el.remove(op)
                        changed = True
                        log["shared_traits"][trait] += 1
                        continue
                if tname == "Types" and c.strip_ns(op.tag) in ("Row", "InsertOrIgnore"):
                    kind = op.get("Kind") or (op.findtext("Kind") or "").strip() or None
                    if not cls.type_is_content(kind):
                        tbl_el.remove(op)
                        changed = True
                        log["system_types"][kind] += 1
                        continue
                otag = c.strip_ns(op.tag)
                if otag in ("Update", "Delete", "Replace"):
                    tbl_el.remove(op)
                    changed = True
                    log["stripped"].append((name, tname, otag, ET.tostring(op, encoding="unicode").strip()))
                    continue
                if table is None:
                    log["errors"].append((name, tname, "unknown table"))
                    continue
                before = len(sim.issues)
                mode = "OR IGNORE" if otag == "InsertOrIgnore" else ""
                try:
                    values = sim._row_values(table, op)
                except KeyError as e:
                    log["errors"].append((name, tname, str(e)))
                    continue
                if not sim.insert(name, table, values, mode):
                    issue = sim.issues[before]
                    tbl_el.remove(op)
                    changed = True
                    if issue.kind == "conflict":
                        log["dropped_rows"].append((name, tname, values))
                    else:
                        log["errors"].append((name, tname, issue.detail))
            if len(tbl_el) == 0:
                root.remove(tbl_el)
    if changed:
        write_xml(root, dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)


def rules_sql(sim: c.Simulator, fast: float | None = None, age_points: int | None = None) -> str:
    """SQL that joins the Exploration tech tree to the Antiquity tree behind a gate."""
    q = lambda sql, *a: sim.db.execute(sql, a).fetchall()
    aq_future, ex_future = "NODE_TECH_AQ_FUTURE_TECH", "NODE_TECH_EX_FUTURE_TECH"
    aq = [r[0] for r in q("SELECT ProgressionTreeNodeType FROM ProgressionTreeNodes WHERE ProgressionTree='TREE_TECHS_AQ'")]
    ex = [r[0] for r in q("SELECT ProgressionTreeNodeType FROM ProgressionTreeNodes WHERE ProgressionTree='TREE_TECHS_EX'")]
    prereqs = q("SELECT Node, PrereqNode FROM ProgressionTreePrereqs")
    used_as_prereq = {p for n, p in prereqs if n in aq and n != aq_future}
    aq_leaves = sorted(n for n in aq if n != aq_future and n not in used_as_prereq)
    has_prereq = {n for n, p in prereqs}
    ex_roots = sorted(n for n in ex if n != ex_future and n not in has_prereq)
    max_cost = q("SELECT MAX(Cost) FROM ProgressionTreeNodes WHERE ProgressionTree='TREE_TECHS_AQ' "
                 "AND ProgressionTreeNodeType != ?", aq_future)[0][0]
    gate_cost = int(round(max_cost * GATE_COST_FACTOR / 5.0) * 5)
    icon = q("SELECT IconString FROM ProgressionTreeNodes WHERE ProgressionTreeNodeType=?", aq_future)[0][0]

    lines = [
        "-- Generated by build_test1.py. Do not edit; run the generator again.",
        "",
        "-- 1. The Exploration Breakthrough gate.",
        f"INSERT INTO Types (Type, Kind) VALUES ('{GATE}', 'KIND_TREE_NODE');",
        "INSERT INTO ProgressionTreeNodes (ProgressionTreeNodeType, ProgressionTree, Cost, Name, Description, IconString)",
        f"VALUES ('{GATE}', 'TREE_TECHS_AQ', {gate_cost}, 'LOC_{GATE}_NAME', 'LOC_{GATE}_DESCRIPTION', '{icon}');",
        "-- A tech needs at least one unlock. The tree screen draws one row per unlock level, and the engine",
        "-- did not count a node with no levels as researched: it was researched again every turn.",
        "-- This unlock only shows a line of text (EFFECT_DO_NOTHING), as Firaxis does for",
        "-- MOD_TECH_EX_NO_OCEAN_DAMAGE_CIVILLIAN_SUPPORT.",
        "INSERT INTO ProgressionTreeNodeUnlocks (ProgressionTreeNodeType, TargetKind, TargetType, UnlockDepth)",
        f"VALUES ('{GATE}', 'KIND_MODIFIER', '{GATE_MODIFIER}', 1);",
        "-- The gate needs the last Antiquity techs.",
    ]
    lines += [f"INSERT INTO ProgressionTreePrereqs (Node, PrereqNode) VALUES ('{GATE}', '{n}');" for n in aq_leaves]
    lines += ["", "-- 2. The first Exploration techs need the gate."]
    lines += [f"INSERT INTO ProgressionTreePrereqs (Node, PrereqNode) VALUES ('{n}', '{GATE}');" for n in ex_roots]
    lines += [
        "",
        "-- 3. Move the Exploration techs into the Antiquity tree.",
        "UPDATE ProgressionTreeNodes SET ProgressionTree = 'TREE_TECHS_AQ' WHERE ProgressionTree = 'TREE_TECHS_EX';",
        "",
        "-- 4. Remove the Antiquity Future Tech; the Exploration Future Tech ends the joined tree.",
        f"DELETE FROM ProgressionTreePrereqs WHERE Node = '{aq_future}' OR PrereqNode = '{aq_future}';",
        f"DELETE FROM ProgressionTreeNodeUnlocks WHERE ProgressionTreeNodeType = '{aq_future}';",
        f"DELETE FROM ProgressionTreeNodes WHERE ProgressionTreeNodeType = '{aq_future}';",
        f"DELETE FROM TypeQuotes WHERE Type = '{aq_future}';",
        f"DELETE FROM Types WHERE Type = '{aq_future}';",
        "",
        "-- 5. The age does not end.",
        f"UPDATE AgeProgressions SET MaxPoints_Abbreviated = {age_points or NEVER_ENDS_POINTS}, "
        f"MaxPoints_Standard = {age_points or NEVER_ENDS_POINTS}, MaxPoints_Long = {age_points or NEVER_ENDS_POINTS};",
        "UPDATE AgeProgressions SET EndsAge = 0 WHERE AgeType != 'AGE_ANTIQUITY';",
        "",
        "-- 5b. Buildings, improvements and wonders: the engine offers only constructibles of the current",
        "--     world age (or with no age), plus civ-unique ones. Each gets the earlier of its own age and",
        "--     the world age, so later-age content is offered and its tech still decides who can build it.",
        "--     The database is rebuilt at each world-age transition, so older buildings can then be built over.",
        "UPDATE Constructibles SET Age = 'AGE_ANTIQUITY' WHERE Age IN ('AGE_EXPLORATION', 'AGE_MODERN');",
        "",
        "-- 6. Governments: the chooser lists every StartingGovernments row without an age filter.",
        "--    Test 1 offers only the Antiquity governments. (Final design: filter by the civ's own age.)",
        "DELETE FROM StartingGovernments WHERE AgeType != 'AGE_ANTIQUITY';",
        "",
    ]
    if fast is not None:
        lines += [
            f"-- 7. Fast test: all techs of the joined tree cost {fast:g} x normal (minimum 1).",
            f"UPDATE ProgressionTreeNodes SET Cost = MAX(1, CAST(Cost * {fast} AS INTEGER)) "
            "WHERE ProgressionTree = 'TREE_TECHS_AQ';",
            "",
        ]
    info = {"aq_leaves": aq_leaves, "ex_roots": ex_roots, "gate_cost": gate_cost, "ex_nodes": len(ex),
            "fast": fast}
    return "\n".join(lines), info


# Adapter: the civ's own Exploration baseline arrives at its own breakthrough.
# In the base game every civ gets these modifiers (trait TRAIT_EXPLORATION_CIV) when the world
# enters Exploration. Chosen with the design owner: the ocean group and the age-balance group.
# Left out: age-start gifts, victory trackers (world system), treasure counts, and the penalties
# whose values are defined elsewhere (review before adding).
BASELINE_AS_IS = [
    # Ocean
    "MOD_TECH_OCEAN_TRAVEL", "MOD_EXPLORATION_EMBARKATION", "MOD_EX_DEEP_OCEAN_TRADE", "TRAIT_MOD_FREE_SHIP",
    # Age balance
    "TRAIT_MOD_BAZAAR_RESOURCE_CAP", "TRAIT_MOD_WHARF_RESOURCE_CAP", "TRAIT_MOD_EXPLORATION_CIV_DIPLOMACY_TOKENS",
    "TRAIT_COMBAT_FLANKING", "TRAIT_AI_SIGHT", "TRAIT_MOD_TOWN_FARMING_PROJECT", "TRAIT_MOD_TOWN_FISHING_PROJECT",
    "TRAIT_MOD_TOWN_URBAN_CENTER_PROJECT", "TRAIT_MOD_TOWN_GROWTH_PROJECT", "TRAIT_MOD_TOWN_TRADE_PROJECT",
    "TRAIT_MOD_ORTOO_RESTORE_MOVEMENT", "TERRACE_FARM_MOD_BUILDING_GOLD",
]
# Same id in both ages: the civ already has the Antiquity version, so it gets a renamed copy of
# the Exploration definition with the difference (argument overrides) or as it is (None).
BASELINE_DELTA = {
    "TRAIT_MOD_GOLD_UNASSIGNED_RESOURCE": {"Amount": "1"},       # Antiquity 1, Exploration 2
    "TRAIT_MOD_HAPPINESS_UNASSIGNED_RESOURCE": {"Amount": "1"},  # Antiquity 1, Exploration 2
    "TRAIT_INITIAL_SETTLEMENT_CAP": None,                       # Exploration: minimum 8 (Antiquity: 3)
}
BASELINE_TRAITS_AQ = ("TRAIT_ANTIQUITY_CIV", "TRAIT_ANACHRONISTIC_CIV")


def exploration_definitions(game: Path) -> dict:
    """Modifier elements of the Exploration age module, by id."""
    out = {}
    for f in sorted((game / "Base" / "modules" / "age-exploration" / "data").glob("*gameeffects*.xml")):
        for el in ET.parse(f).getroot():
            if c.strip_ns(el.tag) == "Modifier":
                out.setdefault(el.get("id"), el)
    return out


def baseline_adapter(sim: c.Simulator, game: Path):
    """Modifiers that the gate unlocks (hidden), new delta definitions, and a report."""
    in_aq = {r[0] for r in sim.db.execute(
        f"SELECT ModifierId FROM TraitModifiers WHERE TraitType IN ({','.join('?' * len(BASELINE_TRAITS_AQ))})",
        BASELINE_TRAITS_AQ)}
    unlocks, skipped, new_defs = [], [], []
    for mid in BASELINE_AS_IS:
        if mid in in_aq:
            skipped.append((mid, "already in the Antiquity baseline"))
        elif mid not in sim.modifiers:
            skipped.append((mid, "not defined in this build"))
        else:
            unlocks.append(mid)
    ex_defs = exploration_definitions(game)
    for mid, overrides in BASELINE_DELTA.items():
        el = ex_defs.get(mid)
        if el is None:
            skipped.append((mid, "no Exploration definition"))
            continue
        copy = ET.fromstring(ET.tostring(el))
        copy.set("id", f"CA_EX_{mid}")
        for arg in copy:
            if c.strip_ns(arg.tag) == "Argument" and overrides and arg.get("name") in overrides:
                arg.text = overrides[arg.get("name")]
        new_defs.append(copy)
        unlocks.append(f"CA_EX_{mid}")
    return unlocks, new_defs, skipped


def adapter_sql(unlocks: list[str], game: Path) -> str:
    lines = ["", "-- 8. Adapter: the civ's own Exploration baseline arrives at its Exploration Breakthrough.",
             "--    Hidden unlocks of the gate (see BASELINE_AS_IS and BASELINE_DELTA in build_test1.py)."]
    lines += [f"INSERT INTO ProgressionTreeNodeUnlocks (ProgressionTreeNodeType, TargetKind, TargetType, UnlockDepth, Hidden) "
              f"VALUES ('{GATE}', 'KIND_MODIFIER', '{m}', 1, 1);" for m in unlocks]
    lines += ["", "--    Exploration ocean movement rule (deep ocean ends the turn until Shipbuilding).",
              "--    It only matters for units that may enter deep ocean, that is civs past their breakthrough."]
    src = game / "Base" / "modules" / "age-exploration" / "data" / "unit-movement.xml"
    for tbl in ET.parse(src).getroot():
        if c.strip_ns(tbl.tag) != "UnitMovementClassObstacles":
            continue
        for row in tbl:
            cols = ", ".join(row.attrib)
            vals = ", ".join("1" if v == "true" else "0" if v == "false" else f"'{v}'" for v in row.attrib.values())
            lines.append(f"INSERT OR IGNORE INTO UnitMovementClassObstacles ({cols}) VALUES ({vals});")
    return "\n".join(lines) + "\n"


# The transition without a reset: a copy of the base transition script with the reset steps
# removed. Each edit must match the installed script exactly, so a game patch that changes the
# script stops the build instead of producing a wrong copy.
TRANSITION_EDITS = [
    # Imports point at the base module, wherever the engine loads this copy from.
    ("from '../maps/", "from 'fs://game/base-standard/maps/"),
    ("from './", "from 'fs://game/base-standard/scripts/"),
    # Old-age resources stay on the map: civs in an earlier age still use them.
    ("const removedResourcePlots = removeObsoleteResources(aGeneratedResourceHashes);",
     "const removedResourcePlots = []; // Continuous Ages: old-age resources stay"),
    # Units: the Continuity steps for every setting. The other setting ("Original") moves commanders
    # to cities and makes free defenders, which are extra units when every unit is kept.
    ('  if (setting == "AGE_TRANSITION_SETTING_KEEP_MORE") {\n',
     '  if (true) { // Continuous Ages: every unit is kept, so the Continuity steps for every setting\n'),
    # Cities stay cities; gold and influence are not capped.
    ("const regressedCities = regressCitiesToTowns(iPlayer);",
     "const regressedCities = []; // Continuous Ages: cities stay cities"),
    ("    capGold(iPlayer);\n", "    // Continuous Ages: no gold cap\n"),
    ("    capInfluence(iPlayer);\n", "    // Continuous Ages: no influence cap\n"),
    # New-age resources skip tiles that already have a district or any constructible: placing one
    # there removes the district and its improvement (seen: one woodcutter, fishing boat or unique
    # improvement per civ; then Han's Great Wall, not in a district, iteration 20261024-224137).
    ("        const idx = y * iWidth + x;\n        const resourceIdx = GameplayMap.getResourceType(x, y);\n",
     "        const idx = y * iWidth + x;\n        const resourceIdx = GameplayMap.getResourceType(x, y);\n"
     "        if (MapCities.getDistrict(x, y) != null || (MapConstructibles.getConstructibles(x, y)?.length ?? 0) > 0) skipMask[idx] = 1; // Continuous Ages: keep improvements\n"),
    # Every unit is kept (Unit_TransitionRetains), and the engine still leaves a shadow for each
    # military unit, so each kept unit came back twice (iteration 20261024-214035: units 31 -> 74).
    # A shadow makes a unit only when the kept units of its domain and class are used up. Matching
    # on the plot as well still made units (iteration 20261024-220907: Egypt lost no military unit
    # and got 7 Swordsmen; packed units are not on their army's plot), and the engine already
    # replaces the previous civ's unique units itself (Persia: 12 Immortals -> 12 Spearmen).
    ("function createUnitFromShadowAtLocation(player, shadow, location) {\n",
     "function createUnitFromShadowAtLocation(player, shadow, location) {\n"
     "  try {\n"
     "    if (caShadowIsKept(player, shadow)) return null; // Continuous Ages: the unit itself was kept\n"
     "    // A leftover shadow is that of a removed unique unit; its tag can name another class.\n"
     "    const tagHash = caLeftoverTag(player, shadow);\n"
     "    if (tagHash != shadow.tagHash) shadow = { domainHash: shadow.domainHash, coreClassHash: shadow.coreClassHash, tagHash,\n"
     "      activityType: shadow.activityType, location: shadow.location, isInCommander: shadow.isInCommander };\n"
     "  } catch (e) {\n"
     "    console.log(`[CA] shadow check error, player ${player.id}: ${e}`);\n"
     "  }\n"),
    ("function getNumDefenders() {\n",
     "// GameInfo tables in this script can be iterated but are not all arrays (iteration 20261025-003254:\n"
     "// Unit_ShadowReplacements.map is not a function).\n"
     "var g_caArrays = null;\n"
     "function caArray(name) {\n"
     "  g_caArrays ??= new Map();\n"
     "  if (!g_caArrays.has(name)) g_caArrays.set(name, Array.from(GameInfo[name]));\n"
     "  return g_caArrays.get(name);\n"
     "}\n"
     "var g_caKept = null;\n"
     "var g_caShadows = null;\n"
     "function caShadowIsKept(player, shadow) {\n"
     "  g_caKept ??= new Map();\n"
     "  g_caShadows ??= new Map();\n"
     "  let kept = g_caKept.get(player.id);\n"
     "  if (kept == null) {\n"
     "    kept = new Map();\n"
     "    const double = caDoubleShadowTypes(player);\n"
     "    for (const id of player.Units?.getUnitIds() ?? []) {\n"
     "      const unit = Units.get(id);\n"
     "      const info = unit ? GameInfo.Units.lookup(unit.type) : null;\n"
     "      if (info == null) continue;\n"
     "      const key = `${Database.makeHash(info.Domain)},${Database.makeHash(info.CoreClass)},${caClassTag(info.UnitType)}`;\n"
     "      kept.set(key, (kept.get(key) ?? 0) + (double.has(info.UnitType) ? 2 : 1));\n"
     "    }\n"
     "    g_caKept.set(player.id, kept);\n"
     "    g_caShadows.get(player.id).keptBy = caNamedCounts(kept); // the shadows each unit type can take\n"
     "  }\n"
     "  const count = g_caShadows.get(player.id);\n"
     "  // The same class tag first (a removed melee unit comes back as melee), then any tag of the same\n"
     "  // domain and class (iteration 20261025-001907: Medjay removed, Catapult made).\n"
     "  const key = `${shadow.domainHash},${shadow.coreClassHash},${shadow.tagHash}`;\n"
     "  const prefix = `${shadow.domainHash},${shadow.coreClassHash},`;\n"
     "  // Last, the same domain and tag with another core class: the shadow of a unique unit can carry\n"
     "  // the core class of the unit it replaces (iteration 20261025-083254: Jaguar Slayer, a military\n"
     "  // unit replacing the Scout, left recon-class shadows, and 4 extra units were made).\n"
     "  const domainTag = (k) => k.startsWith(`${shadow.domainHash},`) && k.endsWith(`,${shadow.tagHash}`);\n"
     "  const use = (kept.get(key) ?? 0) > 0 ? key : [...kept.keys()].find((k) => k.startsWith(prefix) && kept.get(k) > 0)\n"
     "    ?? (shadow.tagHash ? [...kept.keys()].find((k) => domainTag(k) && kept.get(k) > 0) : undefined);\n"
     "  if (use != null) {\n"
     "    kept.set(use, kept.get(use) - 1);\n"
     "    count.kept++;\n"
     "    if (use != key) count.otherTag = (count.otherTag ?? 0) + 1;\n"
     "    return true;\n"
     "  }\n"
     "  // Check record: which shadows had no kept unit (domain/class/tag names, in an army).\n"
     "  const name = caHashNames();\n"
     "  const what = `${name.get(shadow.domainHash)}/${name.get(shadow.coreClassHash)}/${name.get(shadow.tagHash)}${shadow.isInCommander ? '/army' : ''}`;\n"
     "  count.unmatched[what] = (count.unmatched[what] ?? 0) + 1;\n"
     "  // The rest are shadows of removed unique units, one for each (a kept or converted unique unit\n"
     "  // has two; a removed one has one: Egypt 2 removed Medjay -> 2 left, iteration 20261024-235610).\n"
     "  count.made++;\n"
     "  return false;\n"
     "}\n"
     "// The engine leaves two shadows for each unique unit of the civ's previous civ (iteration\n"
     "// 20261024-231716: Egypt 4 + 2 x 7 Medjay = 18 shadows, Persia 16 + 2 x 12 Immortals = 40), and\n"
     "// one for each other unit. It keeps the unique units of a civ that keeps its civ, and converts\n"
     "// them to their base type for a civ that changes (Immortal -> Spearman). So a kept unit of a\n"
     "// unique type of the current or the previous civ, or of the base type of such a unit, takes two.\n"
     "function caDoubleShadowTypes(player) {\n"
     "  const civs = new Set();\n"
     "  const add = (c) => { const t = GameInfo.Civilizations.lookup(c)?.CivilizationType; if (t) civs.add(t); };\n"
     "  add(player.civilizationType);\n"
     "  // Configuration.getPlayer is UI-only (iteration 20261024-232636: not a function here).\n"
     "  const previous = player.previousAgeCivilizationType;\n"
     "  add(previous);\n"
     "  const traits = new Set(caArray('CivilizationTraits').filter((r) => civs.has(r.CivilizationType)).map((r) => r.TraitType));\n"
     "  const out = new Set(caArray('Units').filter((u) => u.TraitType != null && traits.has(u.TraitType)).map((u) => u.UnitType));\n"
     "  // Base types only for a civ that changed: the engine converts the old civ's unique units to them.\n"
     "  // For a civ that keeps its civ they would take shadows of units really removed (Egypt: 96 for 89).\n"
     "  if (civs.size > 1) for (const r of GameInfo.UnitReplaces) if (out.has(r.CivUniqueUnitType)) out.add(r.ReplacesUnitType);\n"
     "  const count = g_caShadows.get(player.id) ?? { kept: 0, made: 0, unmatched: {} };\n"
     "  count.civs = [...civs].map((c) => c.replace('CIVILIZATION_', ''));\n"
     "  count.previousRaw = `${previous}`;\n"
     "  g_caShadows.set(player.id, count);\n"
     "  return out;\n"
     "}\n"
     "// U-SHADOW-CLASS: the engine tags some shadows of removed unique units with another class (Immortal\n"
     "// -> ranged, cavalry, siege, iteration 20261025-062542; Mamluk, Legion -> siege, 054526), and a shadow\n"
     "// has no unit type. The removed units are unique units the player had: its previous civ's (the same\n"
     "// civ when it keeps its civ). A leftover military shadow takes the class of those units of its\n"
     "// domain, unless its own tag is one of them (iteration 20261025-070342: with the new civ's Mamluk\n"
     "// in the set, Immortal shadows tagged cavalry stayed cavalry).\n"
     "var g_caUniqueTags = null;\n"
     "function caLeftoverTag(player, shadow) {\n"
     "  if (shadow.coreClassHash != Database.makeHash('CORE_CLASS_MILITARY')) return shadow.tagHash;\n"
     "  g_caUniqueTags ??= new Map();\n"
     "  let tags = g_caUniqueTags.get(player.id);\n"
     "  if (tags == null) {\n"
     "    const civs = new Set([player.previousAgeCivilizationType ?? player.civilizationType]\n"
     "      .map((c) => GameInfo.Civilizations.lookup(c)?.CivilizationType).filter((c) => c));\n"
     "    if (civs.size == 0) { const c = GameInfo.Civilizations.lookup(player.civilizationType)?.CivilizationType; if (c) civs.add(c); }\n"
     "    const traits = new Set(caArray('CivilizationTraits').filter((r) => civs.has(r.CivilizationType)).map((r) => r.TraitType));\n"
     "    tags = new Map();\n"
     "    for (const u of caArray('Units')) {\n"
     "      if (u.TraitType == null || !traits.has(u.TraitType) || u.CoreClass != 'CORE_CLASS_MILITARY') continue;\n"
     "      const t = caClassTag(u.UnitType);\n"
     "      if (!t) continue;\n"
     "      const d = Database.makeHash(u.Domain);\n"
     "      if (!tags.has(d)) tags.set(d, []);\n"
     "      if (!tags.get(d).includes(t)) tags.get(d).push(t);\n"
     "    }\n"
     "    g_caUniqueTags.set(player.id, tags);\n"
     "  }\n"
     "  const own = tags.get(shadow.domainHash) ?? [];\n"
     "  if (own.length == 0 || own.includes(shadow.tagHash)) return shadow.tagHash;\n"
     "  const count = g_caShadows?.get(player.id);\n"
     "  if (count) count.retagged = (count.retagged ?? 0) + 1;\n"
     "  return own[0];\n"
     "}\n"
     "var g_caHashNames = null;\n"
     "function caHashNames() {\n"
     "  if (g_caHashNames == null) {\n"
     "    g_caHashNames = new Map();\n"
     "    for (const u of GameInfo.Units) for (const v of [u.Domain, u.CoreClass]) g_caHashNames.set(Database.makeHash(v), v);\n"
     "    for (const t of GameInfo.TypeTags) g_caHashNames.set(Database.makeHash(t.Tag), t.Tag);\n"
     "  }\n"
     "  return g_caHashNames;\n"
     "}\n"
     "function caNamedCounts(kept) {\n"
     "  const name = caHashNames();\n"
     "  const out = {};\n"
     "  for (const [k, n] of kept) {\n"
     "    const [d, c, t] = k.split(',').map(Number);\n"
     "    out[`${name.get(d)}/${name.get(c)}/${name.get(t) ?? 'none'}`] = n;\n"
     "  }\n"
     "  return out;\n"
     "}\n"
     "// The unit's class tag as shadows carry it: its tag that names a row of Unit_ShadowReplacements.\n"
     "var g_caShadowTags = null;\n"
     "function caClassTag(unitType) {\n"
     "  g_caShadowTags ??= new Set(caArray('Unit_ShadowReplacements').map((r) => r.Tag));\n"
     "  const tag = caArray('TypeTags').find((t) => t.Type == unitType && g_caShadowTags.has(t.Tag));\n"
     "  return tag ? Database.makeHash(tag.Tag) : 0;\n"
     "}\n"
     "// Check records: the unit types and the settlement constructible types after the reload, before any\n"
     "// civ plays (the first check runs after each civ's first turn), in chunks (long lines are cut).\n"
     "function caLogTypes(iPlayer) {\n"
     "  try {\n"
     "    const player = Players.get(iPlayer);\n"
     "    const short = (t) => (t ?? '?').replace(/^(UNIT|BUILDING|IMPROVEMENT|WONDER)_/, '');\n"
     "    const units = (player?.Units?.getUnitIds() ?? []).map((u) => short(GameInfo.Units.lookup(Units.get(u)?.type)?.UnitType)).sort();\n"
     "    // Per settlement, as the age-end record counts them; the player list where that lookup is\n"
     "    // not in this script (the record says which).\n"
     "    const cons = [];\n"
     "    let source = 'city';\n"
     "    if (typeof Constructibles != 'undefined' && typeof Constructibles.getByComponentID == 'function') {\n"
     "      for (const c of player?.Cities?.getCityIds() ?? []) {\n"
     "        for (const id of Cities.get(c)?.Constructibles?.getIds() ?? []) {\n"
     "          const k = Constructibles.getByComponentID(id);\n"
     "          cons.push(short(k ? GameInfo.Constructibles.lookup(k.type)?.ConstructibleType : null));\n"
     "        }\n"
     "      }\n"
     "    } else {\n"
     "      source = 'player';\n"
     "      for (const k of player?.Constructibles?.getConstructibles() ?? []) cons.push(short(GameInfo.Constructibles.lookup(k.typeHash)?.ConstructibleType));\n"
     "    }\n"
     "    cons.sort();\n"
     "    for (const [kind, list] of [['RELOADUNITS', units], ['RELOADCONS', cons]]) {\n"
     "      for (let i = 0; i === 0 || i < list.length; i += 30) {\n"
     "        console.log(`[CA-CHECK][${kind}] ${JSON.stringify({ id: iPlayer, source, part: i / 30, types: list.slice(i, i + 30) })}`);\n"
     "      }\n"
     "    }\n"
     "  } catch (e) {\n"
     "    console.log(`[CA] reload types record error, player ${iPlayer}: ${e}`);\n"
     "  }\n"
     "}\n"
     "// The RELOAD record keeps only the shadow counts: long lines are cut in the log, and a cut record\n"
     "// cannot be read (iteration 20261025-010211: player 1's RELOAD lost). The detail goes to SHADOWS.\n"
     "function caShadowCounts(iPlayer) {\n"
     "  const s = g_caShadows?.get(iPlayer);\n"
     "  if (s == null) return null;\n"
     "  const out = {};\n"
     "  for (const k of ['kept', 'made', 'ownAge', 'lost', 'otherTag', 'unchecked', 'civs']) if (s[k] != null) out[k] = s[k];\n"
     "  return out;\n"
     "}\n"
     "// Check record: military units by class tag after the reload.\n"
     "function caMilitaryByTag(player) {\n"
     "  try {\n"
     "    g_caShadowTags ??= new Set(caArray('Unit_ShadowReplacements').map((r) => r.Tag));\n"
     "    const out = {};\n"
     "    for (const id of player?.Units?.getUnitIds() ?? []) {\n"
     "      const info = GameInfo.Units.lookup(Units.get(id)?.type);\n"
     "      if (info?.CoreClass != 'CORE_CLASS_MILITARY') continue;\n"
     "      const tag = caArray('TypeTags').find((t) => t.Type == info.UnitType && g_caShadowTags.has(t.Tag))?.Tag ?? 'none';\n"
     "      out[tag] = (out[tag] ?? 0) + 1;\n"
     "    }\n"
     "    return out;\n"
     "  } catch (e) {\n"
     "    console.log(`[CA] military record error, player ${player?.id}: ${e}`);\n"
     "    return null;\n"
     "  }\n"
     "}\n"
     "// A unit type with unlock rows needs one of its nodes unlocked by this player: the shadow's\n"
     "// replacement is the new age's type, which a civ behind its gate may not have (iteration\n"
     "// 20261024-220907: Line Infantry for Exploration civs).\n"
     "function caCanHaveUnit(player, buildUnit) {\n"
     "  const count = g_caShadows?.get(player.id);\n"
     "  const type = GameInfo.Units.lookup(buildUnit)?.UnitType;\n"
     "  const nodes = caArray('ProgressionTreeNodeUnlocks').filter((u) => u.TargetKind == \"KIND_UNIT\" && u.TargetType == type);\n"
     "  if (nodes.length == 0) return true;\n"
     "  if (typeof Game.ProgressionTrees?.getNodeState != \"function\") {\n"
     "    if (count) count.unchecked = (count.unchecked ?? 0) + 1;\n"
     "    return true;\n"
     "  }\n"
     "  // Depth 1 counts: NODE_STATE_UNLOCKED is depth 1 with the mastery still open (gotcha review of 2026-10-29).\n"
     "  const S = typeof ProgressionTreeNodeState != \"undefined\" ? ProgressionTreeNodeState : null;\n"
     "  const fully = S ? S.NODE_STATE_FULLY_UNLOCKED : 5;\n"
     "  return nodes.some((u) => {\n"
     "    const s = Game.ProgressionTrees.getNodeState(player.id, Database.makeHash(u.ProgressionTreeNodeType));\n"
     "    return s >= fully || (S != null && s === S.NODE_STATE_UNLOCKED);\n"
     "  });\n"
     "}\n"
     "// Instead of the new age's type: the best generic unit of the shadow's domain, class and class tag\n"
     "// that the civ can have (its unique version when it has one), so a civ behind its gate keeps the\n"
     "// unit as a type of its own age. Best: the costliest unlock node (later techs cost more; Tier\n"
     "// restarts in each age), then Tier.\n"
     "function caOwnAgeUnit(player, shadow) {\n"
     "  const count = g_caShadows?.get(player.id);\n"
     "  const tagged = new Set(caArray('TypeTags').filter((t) => Database.makeHash(t.Tag) == shadow.tagHash).map((t) => t.Type));\n"
     "  const score = (u) => 10 * Math.max(0, ...caArray('ProgressionTreeNodeUnlocks')\n"
     "    .filter((x) => x.TargetKind == \"KIND_UNIT\" && x.TargetType == u.UnitType)\n"
     "    .map((x) => GameInfo.ProgressionTreeNodes.lookup(x.ProgressionTreeNodeType)?.Cost ?? 0)) + (u.Tier ?? 0);\n"
     "  let best = null, bestScore = -1;\n"
     "  for (const u of GameInfo.Units) {\n"
     "    if (!u.CanTrain || u.TraitType != null || !tagged.has(u.UnitType)) continue;\n"
     "    if (Database.makeHash(u.Domain) != shadow.domainHash || Database.makeHash(u.CoreClass) != shadow.coreClassHash) continue;\n"
     "    if (!caCanHaveUnit(player, u.UnitType)) continue;\n"
     "    const s = score(u);\n"
     "    if (s > bestScore) { best = u; bestScore = s; }\n"
     "  }\n"
     "  if (best == null) {\n"
     "    if (count) count.lost = (count.lost ?? 0) + 1;\n"
     "    return null;\n"
     "  }\n"
     "  const own = player.Units?.getBuildUnit(best.UnitType);\n"
     "  if (count) count.ownAge = (count.ownAge ?? 0) + 1;\n"
     "  return own != null && caCanHaveUnit(player, own) ? own : best.UnitType;\n"
     "}\n"
     "function getNumDefenders() {\n"),
    ("      const buildUnit = player.Units?.getBuildUnit(shadowOption.UnitType);\n      if (buildUnit != null) {\n",
     "      let buildUnit = player.Units?.getBuildUnit(shadowOption.UnitType);\n"
     "      if (buildUnit != null && !caCanHaveUnit(player, buildUnit)) buildUnit = caOwnAgeUnit(player, shadow); // Continuous Ages: the civ's own age\n"
     "      if (buildUnit != null) {\n"),
    # Earth map: the generic resource step (with the mod's rules above) for every map. The Earth step
    # has about 44 inline blocks that remove a rural district and clear its resource at fixed plots
    # (gotcha checker review 5); the guarded stamp below stays as a second line of defence.
    ('  if (mapName == "LOC_MAP_EARTH_NAME") {\n',
     '  if (false && mapName == "LOC_MAP_EARTH_NAME") { // Continuous Ages: the generic step on every map\n'),
    # Earth map: the base script stamps fixed resources instead of the generic step above, and it
    # removed rural districts (and their improvements). Skip plots with a district other than
    # wilderness or with a constructible; on open land the base update applies (iteration
    # 20261025-014844: skipping every plot with a resource left all 56 Exploration resources out).
    ("function stampResourceEarthHuge(xCoord, yCoord, resourceToBePlaced) {\n",
     "function stampResourceEarthHuge(xCoord, yCoord, resourceToBePlaced) {\n"
     "  // Continuous Ages: keep districts and improvements (on open land the base update applies).\n"
     "  const caDistrict = MapCities.getDistrict(xCoord, yCoord);\n"
     "  const caWhy = (caDistrict != null && Districts.get(caDistrict)?.typeHash != DistrictTypes.WILDERNESS) ? 'district'\n"
     "    : (MapConstructibles.getConstructibles(xCoord, yCoord)?.length ?? 0) > 0 ? 'constructible'\n"
     "    : GameInfo.Resources.lookup(GameplayMap.getResourceType(xCoord, yCoord))?.ResourceType == resourceToBePlaced ? 'same resource' : null;\n"
     "  if (caWhy != null) {\n"
     "    console.log(`[CA] Earth resource ${resourceToBePlaced} not placed at ${xCoord},${yCoord}: ${caWhy}`);\n"
     "    return;\n"
     "  }\n"),
    # Check record: each civ's gold after the reload, before any civ plays (Scripting.log).
    ("    Players.AdvancedStart.get(iPlayer)?.dynamicCardsAddedComplete();\n",
     "    Players.AdvancedStart.get(iPlayer)?.dynamicCardsAddedComplete();\n"
     '    console.log(`[CA-CHECK][RELOAD] {"id":${iPlayer},"gold":${Math.round(Players.get(iPlayer)?.Treasury?.goldBalance ?? -1)},'
     '"units":${Players.get(iPlayer)?.Units?.getUnitIds()?.length ?? -1},'
     '"military":${(Players.get(iPlayer)?.Units?.getUnitIds() ?? []).filter((u) => GameInfo.Units.lookup(Units.get(u)?.type)?.CoreClass == "CORE_CLASS_MILITARY").length},'
     '"militaryByTag":${JSON.stringify(caMilitaryByTag(Players.get(iPlayer)))},'
     '"cons":${(Players.get(iPlayer)?.Cities?.getCityIds() ?? []).reduce((n, c) => n + (Cities.get(c)?.Constructibles?.getIds()?.length ?? 0), 0)},'
     '"shadows":${JSON.stringify(caShadowCounts(iPlayer))}}`);\n'
     '    console.log(`[CA-CHECK][SHADOWS] {"id":${iPlayer},"detail":${JSON.stringify(g_caShadows?.get(iPlayer) ?? null)}}`);\n'
     '    caLogTypes(iPlayer); // Continuous Ages check record: unit and constructible types after the reload\n'
     '    caGateMods(iPlayer); // Continuous Ages check record: the gated and regrant modifiers per civ\n'),
    # Check record (gameplay context): the game effects library lists live modifiers here; GEPROBE logs
    # its call shapes once, GATEMODS counts the CA_GATE_ (rule 5e) and CA_REGRANT_ (rule 5d) modifiers.
    ("function caShadowCounts(iPlayer) {\n",
     "let g_caGeProbed = false, g_caGeOwnerLogged = false;\n"
     "function caGateMods(iPlayer) {\n"
     "  try {\n"
     "    const GE = typeof GameEffects !== 'undefined' ? GameEffects : null;\n"
     "    if (!g_caGeProbed) {\n"
     "      g_caGeProbed = true;\n"
     "      const pr = (k, f) => { let v; try { v = f(); v = JSON.stringify(v === undefined ? 'undefined' : v)?.slice(0, 700); } catch (e) { v = `error ${e}`; } console.log(`[CA-CHECK][GEPROBE] ${k}: ${v}`); };\n"
     "      const ms = (() => { try { return GE.getModifiers(); } catch (e) { return null; } })();\n"
     "      const m0 = Array.isArray(ms) ? ms[0] : null, id0 = m0?.id ?? m0;\n"
     "      pr('count', () => GE.getModifierCount());\n"
     "      pr('modifiers', () => Array.isArray(ms) ? [ms.length, ms[0], ms[1]] : typeof ms);\n"
     "      pr('definition', () => GE.getModifierDefinition(id0));\n"
     "      pr('owner', () => GE.getModifierOwner(id0));\n"
     "      pr('active', () => GE.getModifierActive(id0));\n"
     "    }\n"
     "    if (!GE || typeof GE.getModifiers !== 'function') return;\n"
     "    // getModifiers(): modifier ids; getModifierDefinition(id).ID: its name; getModifierOwner(id):\n"
     "    // an object id, its player from getObjectsPlayerId (run 20261025-053548).\n"
     "    const counts = {};\n"
     "    for (const id of GE.getModifiers() ?? []) {\n"
     "      let name = '';\n"
     "      try { name = String(GE.getModifierDefinition(id)?.ID ?? ''); } catch (e) {}\n"
     "      const kind = ['CA_GATE_', 'CA_ATTACH_REGRANT_', 'CA_REGRANT_'].find((k) => name.startsWith(k));\n"
     "      if (!kind) continue;\n"
     "      counts[`all ${kind}`] = (counts[`all ${kind}`] ?? 0) + 1;\n"
     "      let owner = null;\n"
     "      try { const o = GE.getModifierOwner(id); owner = GE.getObjectsPlayerId(o); if (!g_caGeOwnerLogged) { g_caGeOwnerLogged = true; console.log(`[CA-CHECK][GEPROBE] owner sample: ${name} ${o} ${owner} ${GE.getObjectString(o)} ${GE.getObjectType(o)}`); } } catch (e) { owner = `error ${e}`; }\n"
     "      if (owner != iPlayer) continue;\n"
     "      const e = counts[kind] ??= [0, 0];\n"
     "      e[0]++;\n"
     "      try { if (GE.getModifierActive(id)) e[1]++; } catch (e2) {}\n"
     "    }\n"
     "    console.log(`[CA-CHECK][GATEMODS] ${JSON.stringify({ id: iPlayer, counts })}`);\n"
     "  } catch (e) {\n"
     "    console.log(`[CA-CHECK][GEPROBE] error ${e}`);\n"
     "  }\n"
     "}\n"
     "function caShadowCounts(iPlayer) {\n"),
]


def transition_script(game: Path) -> str:
    src = (game / "Base" / "modules" / "base-standard" / "scripts" / "age-transition-post-load.js").read_text(encoding="utf-8")
    for old, new in TRANSITION_EDITS:
        if old not in src:
            raise SystemExit(f"Transition script changed (game patch?): cannot find {old!r}")
        src = src.replace(old, new)
    return 'console.log("[CA] continuous transition script loaded");\n' + src


def text_xml(fast: float | None) -> str:
    name = MOD_NAME if fast is None else f"{MOD_NAME} (FAST TEST: techs at {fast:.0%} cost)"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Database>
	<EnglishText>
		<Row Tag="LOC_{GATE}_NAME">
			<Text>Exploration Breakthrough</Text>
		</Row>
		<Row Tag="LOC_{GATE}_DESCRIPTION">
			<Text>Your civilization enters the Exploration Age. Opens the Exploration technologies.</Text>
		</Row>
		<Row Tag="LOC_{GATE_MODIFIER}_DESCRIPTION">
			<Text>Enter the Exploration Age. Opens the Exploration technologies.</Text>
		</Row>
		<Row Tag="LOC_MODULE_CONTINUOUS_AGES_TEST1_NAME">
			<Text>{name}</Text>
		</Row>
		<Row Tag="LOC_MODULE_CONTINUOUS_AGES_TEST1_DESCRIPTION">
			<Text>Test build. Loads Exploration content in an Antiquity game, joins the tech trees behind an Exploration Breakthrough, and stops the age from ending.</Text>
		</Row>
	</EnglishText>
</Database>
"""


EFFECTS_XML = f"""<?xml version="1.0" encoding="utf-8"?>
<GameEffects xmlns="GameEffects">
	<!-- Display-only unlock of the Exploration Breakthrough gate. -->
	<Modifier id="{GATE_MODIFIER}" collection="COLLECTION_OWNER" effect="EFFECT_DO_NOTHING">
		<String context="Description">LOC_{GATE_MODIFIER}_DESCRIPTION</String>
	</Modifier>
</GameEffects>
"""


def modinfo_xml(items: list[str], text_items: list[str], ui_items: list[str] = ()) -> str:
    content = "\n".join(f"\t\t\t\t\t<Item>{i}</Item>" for i in items)
    text_content = "\n".join(f"\t\t\t\t\t<Item>{i}</Item>" for i in text_items)
    ui_content = "".join(f"\t\t\t\t\t<Item>{i}</Item>\n" for i in ui_items)
    ui_group = "" if not ui_items else f"""		<ActionGroup id="ca-test1-checks" scope="game" criteria="always">
			<Actions>
				<UIScripts>
{ui_content}				</UIScripts>
			</Actions>
		</ActionGroup>
"""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Mod id="{MOD_ID}" version="1" xmlns="ModInfo">
	<Properties>
		<Name>LOC_MODULE_CONTINUOUS_AGES_TEST1_NAME</Name>
		<Description>LOC_MODULE_CONTINUOUS_AGES_TEST1_DESCRIPTION</Description>
		<Authors>Continuous Ages project</Authors>
		<AffectsSavedGames>1</AffectsSavedGames>
	</Properties>
	<Dependencies>
		<Mod id="base-standard" title="LOC_MODULE_BASE_STANDARD_NAME" />
	</Dependencies>
	<References>
		<Mod id="age-antiquity" title="LOC_MODULE_AGE_ANTIQUITY_NAME" />
		<Mod id="age-exploration" title="LOC_MODULE_AGE_EXPLORATION_NAME" />
	</References>
	<ActionCriteria>
		<Criteria id="antiquity-age-current">
			<AgeInUse>AGE_ANTIQUITY</AgeInUse>
		</Criteria>
		<Criteria id="always">
			<AlwaysMet></AlwaysMet>
		</Criteria>
	</ActionCriteria>
	<ActionGroups>
		<ActionGroup id="ca-test1-exploration-content" scope="game" criteria="antiquity-age-current">
			<Properties>
				<LoadOrder>100</LoadOrder>
			</Properties>
			<Actions>
				<UpdateDatabase>
{content}
				</UpdateDatabase>
			</Actions>
		</ActionGroup>
		<ActionGroup id="ca-test1-rules" scope="game" criteria="antiquity-age-current">
			<Properties>
				<LoadOrder>200</LoadOrder>
			</Properties>
			<Actions>
				<UpdateDatabase>
					<Item>data/continuous-ages-effects.xml</Item>
					<Item>data/continuous-ages-rules.sql</Item>
				</UpdateDatabase>
			</Actions>
		</ActionGroup>
		<ActionGroup id="ca-test1-exploration-text" scope="game" criteria="antiquity-age-current">
			<Actions>
				<UpdateText>
{text_content}
				</UpdateText>
			</Actions>
		</ActionGroup>
{ui_group}		<ActionGroup id="ca-test1-transition" scope="game" criteria="always">
			<Actions>
				<ImportFiles>
					<Item>scripts/age-transition-post-load.js</Item>
				</ImportFiles>
				<AgeTransitionScripts>
					<Item>scripts/ca-transition-marker.js</Item>
				</AgeTransitionScripts>
			</Actions>
		</ActionGroup>
		<ActionGroup id="ca-test1-text" scope="game" criteria="always">
			<Actions>
				<UpdateText>
					<Item>text/en_us/ContinuousAgesText.xml</Item>
				</UpdateText>
			</Actions>
		</ActionGroup>
		<ActionGroup id="ca-test1-shell-text" scope="shell" criteria="always">
			<Actions>
				<UpdateText>
					<Item>text/en_us/ContinuousAgesText.xml</Item>
				</UpdateText>
			</Actions>
		</ActionGroup>
	</ActionGroups>
</Mod>
"""


def fk_set(sim):
    return {(t, p, tuple(sorted(v.items()))) for t, p, v in sim.foreign_key_violations()}


def validate(game, mods):
    check = c.Simulator(game)
    all_mods = mods + [c.parse_modinfo(OUT / f"{MOD_ID}.modinfo")]
    for path in c.database_items(c.applicable_groups(all_mods, "AGE_ANTIQUITY")):
        check.apply_file(path)
    return check


def prune_dangling(items: list[str], violations, log) -> int:
    """Remove copied rows whose foreign keys point to rows that do not exist."""
    removed = 0
    for item in items:
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
                        log["dangling"].append((item, table, parent, dict(values)))
            if len(tbl_el) == 0:
                root.remove(tbl_el)
        if changed:
            write_xml(root, path)
    return removed


def copy_exploration_text(groups, mods, log) -> list[str]:
    """Copy the English text that loads only in Exploration (for example the Exploration
    tech names), without the keys that an Antiquity game already defines."""
    aq_tags = set()
    for mod, grp in c.applicable_groups(mods, "AGE_ANTIQUITY"):
        for tag, paths in grp.actions:
            if tag == "UpdateText":
                for item in paths:
                    if "en_us" in item and (mod.folder / item).exists():
                        aq_tags |= {el.get("Tag") for el in ET.parse(mod.folder / item).iter() if el.get("Tag")}
    out = []
    for mod, grp in groups:
        for tag, paths in grp.actions:
            if tag != "UpdateText":
                continue
            for item in paths:
                if "en_us" not in item:
                    continue  # other languages: not needed for the test
                if item.rsplit("/", 1)[-1] in TEXT_EXCLUDE:
                    log["skipped"].append((f"{mod.id}:{grp.id}", item, 1))
                    continue
                root = ET.parse(mod.folder / item).getroot()
                dropped = 0
                for table in list(root):
                    for row in list(table):
                        key = row.get("Tag")
                        if key in aq_tags:
                            table.remove(row)
                            dropped += 1
                        elif key:
                            aq_tags.add(key)
                    if len(table) == 0:
                        root.remove(table)
                rel_item = f"text/{mod.id}/{item.split('/', 1)[1] if item.startswith('text/') else item}"
                write_xml(root, OUT / rel_item)
                out.append(rel_item)
                log["text"].append((rel_item, dropped))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", type=Path, default=c.DEFAULT_GAME_DIR)
    ap.add_argument("--install", action="store_true", help=f"copy the mod to {MODS_DIR}")
    ap.add_argument("--checks", action="store_true",
                    help="add the in-game check script (checks/ca-checks.js) for autoplay tests")
    ap.add_argument("--age-points", type=int, default=None, metavar="N",
                    help="the age ends at N age-progress points (test of world transitions); default: never")
    ap.add_argument("--fast-test", nargs="?", const=0.1, type=float, metavar="FACTOR",
                    help="multiply all tech costs by FACTOR (default 0.1) to reach the gate quickly")
    args = ap.parse_args()
    if args.fast_test is not None and not 0 < args.fast_test <= 1:
        ap.error("--fast-test FACTOR must be greater than 0 and not more than 1")
    game = args.game_dir

    # Empty the output folder (not delete it: a shell may still have it open).
    OUT.mkdir(parents=True, exist_ok=True)
    for child in OUT.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    # Content comes from the base modules. Conflict checks and validation also
    # load the installed DLC, because an Antiquity game loads it too.
    groups = exploration_only_groups(c.load_base_modules(game))
    mods = c.load_base_modules(game, include_dlc=True)

    baseline = c.simulate(game, "AGE_ANTIQUITY", include_dlc=True)
    baseline_fk = fk_set(baseline)

    # Build the mod against a simulation of the Antiquity game.
    sim = c.simulate(game, "AGE_ANTIQUITY", include_dlc=True)
    log = {"stripped": [], "dropped_rows": [], "dropped_effects": [], "errors": [], "skipped": [],
           "dangling": [], "text": [], "systems": [],
           "system_types": Counter(), "shared_traits": Counter()}
    items = []
    text_items = copy_exploration_text(groups, mods, log)
    for mod, grp in groups:
        for tag, paths in grp.actions:
            if tag == "UpdateText":
                continue  # handled by copy_exploration_text
            if tag != "UpdateDatabase":
                if paths:
                    log["skipped"].append((f"{mod.id}:{grp.id}", tag, len(paths)))
                continue
            for item in paths:
                if excluded(mod.id, item):
                    log["skipped"].append((f"{mod.id}:{grp.id}", item, 1))
                    continue
                rel_item = f"data/{mod.id}/{item}"
                copy_transformed(sim, mod.folder / item, OUT / rel_item, log)
                items.append(rel_item)

    sql, info = rules_sql(sim, args.fast_test, args.age_points)
    baseline_unlocks, baseline_defs, baseline_skipped = baseline_adapter(sim, game)
    sql += adapter_sql(baseline_unlocks, game)
    info["baseline"] = (baseline_unlocks, baseline_skipped)
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "data" / "continuous-ages-rules.sql").write_text(sql, encoding="utf-8")
    effects = ET.fromstring(EFFECTS_XML.split("?>", 1)[1])
    for el in baseline_defs:
        effects.append(el)
    write_xml(effects, OUT / "data" / "continuous-ages-effects.xml")
    (OUT / "text" / "en_us").mkdir(parents=True, exist_ok=True)
    (OUT / "text" / "en_us" / "ContinuousAgesText.xml").write_text(text_xml(args.fast_test), encoding="utf-8")
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "scripts" / "age-transition-post-load.js").write_text(transition_script(game), encoding="utf-8")
    (OUT / "scripts" / "ca-transition-marker.js").write_text(
        'console.log("[CA] AgeTransitionScripts item ran");\n', encoding="utf-8")
    ui_items = []
    if args.checks:
        (OUT / "ui").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(__file__).parent / "checks" / "ca-checks.js", OUT / "ui" / "ca-checks.js")
        # Automation test for world transitions; the autoplay suite loads it from the mod folder.
        shutil.copyfile(Path(__file__).parent / "checks" / "ca-automation.js", OUT / "ui" / "ca-automation.js")
        ui_items.append("ui/ca-checks.js")
    (OUT / f"{MOD_ID}.modinfo").write_text(modinfo_xml(items, text_items, ui_items), encoding="utf-8")

    # Validate: load the base modules plus the generated mod, in load order.
    # Copied rows that point to excluded content are removed, then validated again.
    check = validate(game, mods)
    new_fk = sorted(fk_set(check) - baseline_fk)
    for _ in range(8):
        if not new_fk or not prune_dangling(items, [(t, p, v) for t, p, v in new_fk], log):
            break
        check = validate(game, mods)
        new_fk = sorted(fk_set(check) - baseline_fk)
    tree = check.db.execute(
        "SELECT ProgressionTree, COUNT(*) FROM ProgressionTreeNodes WHERE ProgressionTree LIKE 'TREE_TECHS%' "
        "GROUP BY ProgressionTree").fetchall()

    write_report(log, info, check.issues, new_fk, tree, items)
    print(f"Built {OUT}")
    print(f"  files: {len(items)}  stripped ops: {len(log['stripped'])}  dropped rows: {len(log['dropped_rows'])}"
          f"  dropped effects: {len(log['dropped_effects'])}  dangling: {len(log['dangling'])}  errors: {len(log['errors'])}")
    unclassified = {t for _, t, k, _ in log["systems"] if k == "unclassified"}
    print(f"  systems left with their age: {sum(1 for x in log['systems'] if x[2] == 'system')} tables,"
          f" {sum(log['system_types'].values())} types; unclassified tables: {sorted(unclassified) or 'none'}")
    print(f"  validation: {len(check.issues)} load issues, {len(new_fk)} new foreign-key violations")
    print(f"  tech trees: {tree}")
    if args.install:
        dest = MODS_DIR / MOD_ID
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(OUT, dest)
        print(f"Installed to {dest}")


def write_report(log, info, issues, new_fk, tree, items) -> None:
    fast_text = "off" if info["fast"] is None else f"on, all tech costs x {info['fast']:g} (minimum 1)"
    out = [f"# {MOD_NAME}: build report", ""]
    out += ["## Result", "",
            f"- Copied files: {len(items)}",
            f"- Exploration tech nodes joined: {info['ex_nodes']}; gate cost: {info['gate_cost']}",
            f"- Fast test: {fast_text}",
            f"- Gate prerequisites (last Antiquity techs): {', '.join(info['aq_leaves'])}",
            f"- Techs that need the gate (first Exploration techs): {', '.join(info['ex_roots'])}",
            f"- Tech trees after load: {tree}",
            f"- Validation load issues: {len(issues)}",
            f"- New foreign-key violations: {len(new_fk)}", ""]
    if issues:
        out += ["## Validation load issues", ""] + [f"- {i.kind}: {c.rel(Path(i.file))} {i.table}: {i.detail}"
                                                       for i in issues] + [""]
    if new_fk:
        out += ["## New foreign-key violations", ""] + [f"- {t} -> {p}: {dict(v)}" for t, p, v in new_fk] + [""]
    out += ["## Skipped groups and files", ""] + [f"- {g}: {what} ({n})" for g, what, n in log["skipped"]] + [""]
    out += ["## Removed operations (Exploration balance changes)", ""]
    out += [f"- {f} `{t}` {op}: `{x[:200]}`" for f, t, op, x in log["stripped"]] + [""]
    counts = Counter((f, t) for f, t, _ in log["dropped_rows"])
    out += ["## Removed rows (key already exists in Antiquity)", ""]
    out += [f"- {f} `{t}`: {n}" for (f, t), n in sorted(counts.items())] + [""]
    out += ["## Removed GameEffects entries (id already exists)", ""]
    out += [f"- {f} {k} `{i}`" for f, k, i in log["dropped_effects"]] + [""]
    unclassified = sorted({(t, f) for f, t, k, _ in log["systems"] if k == "unclassified"})
    out += ["## Unclassified tables (not loaded; review: content or system?)", ""]
    out += [f"- **{t}** in {f}" for t, f in unclassified] or ["- none"]
    out += [""]
    sys_rows = Counter()
    for f, t, k, n in log["systems"]:
        if k == "system":
            sys_rows[t] += n
    out += ["## System tables left with their age (rows not loaded)", ""]
    out += [f"- {t}: {n}" for t, n in sorted(sys_rows.items())] + [""]
    out += ["## Shared-trait modifiers left with their age (age baselines, not civ abilities)", ""]
    out += [f"- {t}: {n}" for t, n in log["shared_traits"].most_common()] + [""]
    out += ["## System types left with their age (by kind)", ""]
    out += [f"- {k}: {n}" for k, n in log["system_types"].most_common()] + [""]
    unlocks, skipped = info["baseline"]
    out += ["## Adapter: Exploration baseline at the civ's breakthrough", "",
            f"- Granted by the gate (hidden): {', '.join(unlocks)}"]
    out += [f"- Not granted: {m} ({why})" for m, why in skipped] + [""]
    out += ["## Copied Exploration text (keys that Antiquity already defines are removed)", ""]
    out += [f"- {f}: {n} keys removed" for f, n in log["text"]] + [""]
    out += ["## Removed rows (reference to content that is not loaded)", ""]
    out += [f"- {f} `{t}` -> `{p}`: {v}" for f, t, p, v in log["dangling"]] + [""]
    if log["errors"]:
        out += ["## Errors", ""] + [f"- {f} `{t}`: {e}" for f, t, e in log["errors"]] + [""]
    (OUT / "REPORT.md").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
