"""Read Civilization VII module data and rebuild the gameplay database in SQLite.

The engine builds its gameplay database from the modinfo files of all enabled
modules. This module repeats that process closely enough to find key conflicts
and broken foreign keys before the game is started:

* parse each .modinfo (criteria, action groups, load order),
* decide which game-scope groups apply for a given current age,
* apply UpdateDatabase items (XML Database files, GameEffects files, SQL files)
  to an in-memory SQLite database created from the shipped schema.

GameEffects files are not translated into tables (the engine does that
internally). Their Modifier and RequirementSet ids are collected so that
duplicate ids can be reported.
"""
from __future__ import annotations

import os
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VII")

AGES = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]
BASE_MODULES = ["core", "base-standard", "age-antiquity", "age-exploration", "age-modern"]


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _fnv1a32(text) -> int:
    h = 0x811C9DC5
    for b in str(text).encode():
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h - (1 << 32) if h & 0x80000000 else h


@dataclass
class ActionGroup:
    module: str
    index: int
    id: str
    scope: str
    criteria: str
    load_order: int
    actions: list[tuple[str, list[str]]]  # (action tag, item paths)


@dataclass
class Module:
    id: str
    folder: Path
    criteria: dict[str, tuple[bool, list[tuple[str, str]]]]  # id -> (any, [(tag, text)])
    groups: list[ActionGroup] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


def parse_modinfo(path: Path) -> Module:
    root = ET.parse(path).getroot()
    mod = Module(id=root.get("id"), folder=path.parent, criteria={})
    for el in root:
        tag = strip_ns(el.tag)
        if tag == "Dependencies":
            mod.dependencies = [d.get("id") for d in el]
        elif tag == "ActionCriteria":
            for crit in el:
                # A condition with child elements (ConfigurationValueMatches: Group, ConfigurationId,
                # Value) keeps them as "Group/ConfigurationId=Value".
                conds = [(strip_ns(c.tag), "{}/{}={}".format(*((c.findtext(f"{{ModInfo}}{k}") or c.findtext(k) or "").strip()
                                                              for k in ("Group", "ConfigurationId", "Value")))
                          if len(c) else (c.text or "").strip()) for c in crit]
                mod.criteria[crit.get("id")] = (crit.get("any") == "true", conds)
        elif tag == "ActionGroups":
            for i, grp in enumerate(el):
                load_order = 0
                actions = []
                for part in grp:
                    ptag = strip_ns(part.tag)
                    if ptag == "Properties":
                        lo = part.find("{ModInfo}LoadOrder")
                        if lo is None:
                            lo = part.find("LoadOrder")
                        if lo is not None and lo.text:
                            load_order = int(lo.text.strip())
                    elif ptag == "Actions":
                        for act in part:
                            items = [(it.text or "").strip() for it in act if strip_ns(it.tag) == "Item"]
                            actions.append((strip_ns(act.tag), items))
                mod.groups.append(ActionGroup(mod.id, i, grp.get("id"), grp.get("scope"),
                                              grp.get("criteria"), load_order, actions))
    return mod


def load_base_modules(game_dir: Path = DEFAULT_GAME_DIR, include_dlc: bool = False) -> list[Module]:
    mods = []
    for name in BASE_MODULES:
        mods.append(parse_modinfo(game_dir / "Base" / "modules" / name / f"{name}.modinfo"))
    if include_dlc:
        dlc = [parse_modinfo(p) for p in sorted((game_dir / "DLC").glob("*/modules/*.modinfo"))]
        mods += order_by_dependencies(dlc, {m.id for m in mods})
    return mods


def order_by_dependencies(mods: list[Module], loaded: set[str]) -> list[Module]:
    """Order modules so that each comes after the modules it depends on."""
    out, pending, loaded = [], list(mods), set(loaded)
    while pending:
        ready = [m for m in pending if all(d in loaded for d in m.dependencies if d in {p.id for p in pending})]
        if not ready:  # a cycle or a missing module: keep the remaining order
            ready = pending[:1]
        for m in ready:
            out.append(m)
            loaded.add(m.id)
            pending.remove(m)
    return out


def criterion_met(cond: tuple[str, str], age: str, enabled: set[str] = frozenset(),
                  ruleset: str = "RULESET_STANDARD", config: dict | None = None) -> bool:
    """config: setup values as {"Group/ConfigurationId": value}; a value not given does not match."""
    tag, text = cond
    cur = AGES.index(age)
    if tag in ("ModInUse", "ModIsEnabled", "ModIsInstalled"):
        return text in enabled
    if tag == "AlwaysMet":
        return True
    if tag == "NeverMet":
        return False
    if tag == "AgeInUse":
        return text == age
    if tag in ("AgeAtOrBefore", "AgeEverInUse", "AgeWasUsed"):
        return AGES.index(text) <= cur
    if tag == "AgeBefore":
        return AGES.index(text) < cur
    if tag == "RuleSetInUse":
        return text == ruleset
    if tag == "ConfigurationValueMatches":
        key, _, value = text.partition("=")
        return (config or {}).get(key) == value
    raise ValueError(f"unsupported criterion {tag}")


def group_applies(mod: Module, grp: ActionGroup, age: str, enabled: set[str] = frozenset(),
                  config: dict | None = None) -> bool:
    if grp.scope != "game" or grp.criteria not in mod.criteria:
        # Some shipped modinfo files name criteria that they never define
        # (for example "great-britain-curret"); such a group cannot apply.
        return False
    any_, conds = mod.criteria[grp.criteria]
    results = [criterion_met(c, age, enabled, config=config) for c in conds]
    return any(results) if any_ else all(results)


def applicable_groups(mods: list[Module], age: str, config: dict | None = None) -> list[tuple[Module, ActionGroup]]:
    """Game-scope groups that load when `age` is current, in engine load order.
    All given modules count as enabled. config: setup values (see criterion_met)."""
    enabled = {m.id for m in mods}
    out = []
    for mi, mod in enumerate(mods):
        for grp in mod.groups:
            if group_applies(mod, grp, age, enabled, config):
                out.append((mi, mod, grp))
    out.sort(key=lambda t: (t[2].load_order, t[0], t[2].index))
    return [(mod, grp) for _, mod, grp in out]


def database_items(groups: list[tuple[Module, ActionGroup]]) -> list[Path]:
    paths = []
    for mod, grp in groups:
        for tag, items in grp.actions:
            if tag == "UpdateDatabase":
                paths.extend(mod.folder / item for item in items)
    return paths


# ---------------------------------------------------------------------------
# Database simulation


@dataclass
class Issue:
    file: str
    table: str
    kind: str      # "conflict" (primary key / unique) or "error"
    detail: str
    values: dict


class Simulator:
    def __init__(self, game_dir: Path = DEFAULT_GAME_DIR):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys = OFF")
        # The schema's insert triggers call an engine function. Its exact value does
        # not matter for validation, only that it is deterministic.
        self.db.create_function("Make_Hash", 1, _fnv1a32, deterministic=True)
        schema_dir = game_dir / "Base" / "Assets" / "schema" / "gameplay"
        for sql in sorted(schema_dir.glob("*.sql")):
            self.db.executescript(sql.read_text(encoding="utf-8-sig"))
        self.columns: dict[str, dict[str, str]] = {}
        for (name,) in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            cols = [r[1] for r in self.db.execute(f"PRAGMA table_info('{name}')")]
            self.columns[name.lower()] = {c.lower(): c for c in cols}
        self.table_names = {n.lower(): n for n in
                            (r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'"))}
        self.issues: list[Issue] = []
        self.modifiers: dict[str, str] = {}
        self.requirement_sets: dict[str, str] = {}

    # -- helpers -----------------------------------------------------------
    def _table(self, name: str) -> str | None:
        return self.table_names.get(name.lower())

    def _col(self, table: str, name: str) -> str | None:
        return self.columns[table.lower()].get(name.lower())

    @staticmethod
    def _value(v: str):
        if v == "true":
            return 1
        if v == "false":
            return 0
        return v

    def _row_values(self, table: str, el: ET.Element) -> dict:
        vals = {}
        for k, v in el.attrib.items():
            col = self._col(table, k)
            if col is None:
                raise KeyError(f"unknown column {k}")
            vals[col] = self._value(v)
        for child in el:
            col = self._col(table, strip_ns(child.tag))
            if col is None:
                raise KeyError(f"unknown column {strip_ns(child.tag)}")
            vals[col] = self._value((child.text or "").strip())
        return vals

    # -- operations ----------------------------------------------------------
    def insert(self, file: str, table: str, values: dict, mode: str = "") -> bool:
        cols = ", ".join(f'"{c}"' for c in values)
        qs = ", ".join("?" for _ in values)
        sql = f'INSERT {mode} INTO "{table}" ({cols}) VALUES ({qs})'
        try:
            self.db.execute(sql, list(values.values()))
            return True
        except sqlite3.IntegrityError as e:
            msg = str(e)
            kind = "conflict" if ("UNIQUE" in msg or "PRIMARY" in msg) else "error"
            self.issues.append(Issue(file, table, kind, msg, values))
            return False

    def apply_database_xml(self, file: str, root: ET.Element, filter_op=None) -> ET.Element:
        """Apply a <Database> document. filter_op(file, table, op_el, ok) may be
        given to record each operation's outcome. Returns the root."""
        for tbl_el in root:
            tname = strip_ns(tbl_el.tag)
            table = self._table(tname)
            for op in list(tbl_el):
                otag = strip_ns(op.tag)
                if table is None:
                    self.issues.append(Issue(file, tname, "error", "unknown table", {}))
                    continue
                ok = True
                try:
                    if otag in ("Row", "InsertOrIgnore", "Replace"):
                        mode = {"Row": "", "InsertOrIgnore": "OR IGNORE", "Replace": "OR REPLACE"}[otag]
                        ok = self.insert(file, table, self._row_values(table, op), mode)
                    elif otag == "Update":
                        where = self._row_values(table, op.find("Where")) if op.find("Where") is not None else {}
                        sets = self._row_values(table, op.find("Set"))
                        sql = f'UPDATE "{table}" SET ' + ", ".join(f'"{c}"=?' for c in sets)
                        if where:
                            sql += " WHERE " + " AND ".join(f'"{c}"=?' for c in where)
                        self.db.execute(sql, list(sets.values()) + list(where.values()))
                    elif otag == "Delete":
                        where = self._row_values(table, op)
                        sql = f'DELETE FROM "{table}"'
                        if where:
                            sql += " WHERE " + " AND ".join(f'"{c}"=?' for c in where)
                        self.db.execute(sql, list(where.values()))
                    else:
                        self.issues.append(Issue(file, table, "error", f"unknown op {otag}", {}))
                except (KeyError, sqlite3.Error) as e:
                    ok = False
                    self.issues.append(Issue(file, table, "error", str(e), dict(op.attrib)))
                if filter_op:
                    filter_op(file, tname, op, ok)
        return root

    def apply_game_effects(self, file: str, root: ET.Element, filter_el=None) -> None:
        for el in list(root):
            tag = strip_ns(el.tag)
            ident = el.get("id")
            store = self.modifiers if tag == "Modifier" else self.requirement_sets
            duplicate = ident in store
            if duplicate:
                self.issues.append(Issue(file, tag, "conflict",
                                         f"duplicate {tag} id (first in {store[ident]})", {"id": ident}))
            else:
                store[ident] = file
                # Register the id so that foreign keys to it can be checked. The engine
                # builds the full rows itself; only the key matters here.
                if tag == "Modifier":
                    self.db.execute("INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType) VALUES (?, ?)",
                                    (ident, "GAMEEFFECTS"))
                elif tag == "RequirementSet":
                    self.db.execute("INSERT OR IGNORE INTO RequirementSets (RequirementSetId) VALUES (?)",
                                    (ident,))
            if filter_el:
                filter_el(file, tag, el, not duplicate)

    def apply_file(self, path: Path) -> None:
        name = str(path)
        if path.suffix.lower() == ".sql":
            try:
                self.db.executescript(path.read_text(encoding="utf-8-sig"))
            except sqlite3.Error as e:
                self.issues.append(Issue(name, "", "error", str(e), {}))
            return
        root = ET.parse(path).getroot()
        if strip_ns(root.tag) == "GameEffects":
            self.apply_game_effects(name, root)
        else:
            self.apply_database_xml(name, root)

    def foreign_key_violations(self) -> list[tuple]:
        """Rows whose foreign keys point to missing parents: (table, parent, values)."""
        out = []
        self.unchecked_tables = []
        for name in sorted(self.table_names.values()):
            try:
                rows = self.db.execute(f"PRAGMA foreign_key_check('{name}')").fetchall()
            except sqlite3.OperationalError:
                # The schema has foreign keys to non-unique columns; SQLite cannot check them.
                self.unchecked_tables.append(name)
                continue
            for table, rowid, parent, fkid in rows:
                fk = [r for r in self.db.execute(f"PRAGMA foreign_key_list('{table}')") if r[0] == fkid]
                cols = [r[3] for r in fk]
                row = self.db.execute(f'SELECT {", ".join(chr(34)+c+chr(34) for c in cols)} FROM "{table}" '
                                      f"WHERE rowid=?", (rowid,)).fetchone() if rowid is not None else None
                out.append((table, parent, dict(zip(cols, row or ()))))
        return out


def simulate(game_dir: Path, age: str, extra_files: list[Path] = (), include_dlc: bool = False) -> Simulator:
    """Build the gameplay database of a game whose current age is `age`."""
    sim = Simulator(game_dir)
    mods = load_base_modules(game_dir, include_dlc)
    for path in database_items(applicable_groups(mods, age)):
        sim.apply_file(path)
    for path in extra_files:
        sim.apply_file(path)
    return sim


def rel(path: Path, game_dir: Path = DEFAULT_GAME_DIR) -> str:
    try:
        return os.path.relpath(path, game_dir / "Base" / "modules").replace("\\", "/")
    except ValueError:
        return str(path)
