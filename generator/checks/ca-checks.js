// Continuous Ages: in-game checks for test builds (generator --checks).
// Writes short "[CA-CHECK]" lines to UI.log (console.warn; console.log output is not kept,
// and UI.log cuts lines at about 1000 characters). iterate.py reads them after a run.
//   [CA-CHECK][SNAPSHOT] {"turn","age","ageProgress","ageMax"}      every SNAPSHOT_EVERY turns
//   [CA-CHECK][PLAYER] {"age","turn","id","civAge","civ","gate",...} one line per major civ
//   [CA-CHECK][STATE] {"age","turn","id","civAge","gold","techs",...} values a transition could reset
//   [CA-CHECK][BUILD] {"turn","id","ok","needUnlock","noPlot",...}   capital: can it build Exploration buildings?
//   [CA-CHECK][FAIL] ...    a rule of the design was broken
//   [CA-CHECK][ERROR] ...   the check itself failed

const SNAPSHOT_EVERY = 5;
const BUILD_CHECK_EVERY = 20;
const GATE_CHECK_EVERY = 10;
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH";
const MO_GATE = "NODE_TECH_CA_MODERN_BREAKTHROUGH";
const OCEAN_TECH = "NODE_TECH_EX_SHIPBUILDING"; // removes the deep-ocean obstacle (MOD_TECH_EX_NO_OCEAN_OBSTACLE)
// Ocean travel itself (MOD_TECH_OCEAN_TRAVEL) comes with the gate: the civ's own Exploration baseline.

let lastTurnChecked = -1;
let firstCheckAfterLoad = false;

// Exploration constructibles, found by the Exploration tech or civic that unlocks them
// (their Age column is set to the world age by the generator, so Age cannot tell).
const EX_CONSTRUCTIBLES = new Set();
for (const u of GameInfo.ProgressionTreeNodeUnlocks) {
  if (u.TargetKind === "KIND_CONSTRUCTIBLE" &&
      (u.ProgressionTreeNodeType.startsWith("NODE_TECH_EX_") || u.ProgressionTreeNodeType.startsWith("NODE_CIVIC_EX_"))) {
    EX_CONSTRUCTIBLES.add(u.TargetType);
  }
}

function log(kind, text) {
  console.warn(`[CA-CHECK][${kind}] ${text}`);
}

function hasNode(playerId, type) {
  const hash = GameInfo.ProgressionTreeNodes.lookup(type)?.$hash;
  if (hash === undefined) return false;
  return Game.ProgressionTrees.getNodeState(playerId, hash) >= ProgressionTreeNodeState.NODE_STATE_FULLY_UNLOCKED;
}

function completedNodes(playerId, prefix) {
  const out = [];
  for (const node of GameInfo.ProgressionTreeNodes) {
    if (node.ProgressionTreeNodeType.startsWith(prefix) &&
        Game.ProgressionTrees.getNodeState(playerId, node.$hash) >= ProgressionTreeNodeState.NODE_STATE_FULLY_UNLOCKED) {
      out.push(node.ProgressionTreeNodeType.replace(/^NODE_(TECH|CIVIC)_/, ""));
    }
  }
  return out;
}
function explorationTechs(playerId, prefix = "NODE_TECH_EX_") {
  return completedNodes(playerId, prefix).length;
}

function explorationBuildings(player) {
  const found = [];
  for (const cityId of player.Cities?.getCityIds() ?? []) {
    for (const id of Cities.get(cityId)?.Constructibles?.getIds() ?? []) {
      const constructible = Constructibles.getByComponentID(id);
      const def = constructible ? GameInfo.Constructibles.lookup(constructible.type) : null;
      if (def && EX_CONSTRUCTIBLES.has(def.ConstructibleType)) found.push(def.ConstructibleType);
    }
  }
  return found;
}

function oceanUnits(player, oceanIndex) {
  const units = [];
  for (const unitId of player.Units?.getUnitIds() ?? []) {
    const unit = Units.get(unitId);
    const loc = unit?.location;
    if (loc && GameplayMap.getTerrainType(loc.x, loc.y) === oceanIndex) {
      units.push(GameInfo.Units.lookup(unit.type)?.UnitType ?? String(unit.type));
    }
  }
  return units;
}

// canStart(MOVE_TO) said Success for deep-ocean plots of a civ behind its gate (it answers only when
// the observed player is the unit's owner: ObserveAs=0; run 20261025-100334), but no unit ever ended a
// turn there. A plot counts as reachable only when the path finder (Units.getPathTo, as the game's
// move UI uses it) returns a path that ends on it. OCEANTEST logs one sample per age with both answers.
let oceanTestAge = null;
// The path finder treats plots the player has not seen as passable (run 20261025-103909: a 32-plot
// path to deep ocean 3 plots away), so a target counts only when it and every plot of the path are
// revealed to the unit's owner.
function pathEndsAt(unit, px, py, oceanIndex) {
  const path = Units.getPathTo(unit.id, { x: px, y: py });
  const plots = path?.plots ?? [];
  const loc = (p) => (typeof p === "object" ? p : GameplayMap.getLocationFromIndex(p));
  const end = plots.length ? loc(plots[plots.length - 1]) : null;
  const hidden = plots.filter((p) => { const l = loc(p); return GameplayMap.getRevealedState(unit.owner, l.x, l.y) == RevealedStates.HIDDEN; }).length;
  const ocean = plots.filter((p) => { const l = loc(p); return GameplayMap.getTerrainType(l.x, l.y) === oceanIndex; }).length;
  const targetSeen = GameplayMap.getRevealedState(unit.owner, px, py) != RevealedStates.HIDDEN;
  const ok = end != null && end.x === px && end.y === py && hidden === 0 && targetSeen;
  return { length: plots.length, hidden, ocean, targetSeen, ok };
}
function oceanSample(player, unit, px, py, result, path, turn) {
  const age = GameInfo.Ages.lookup(Game.age)?.AgeType;
  if (oceanTestAge === age) return;
  oceanTestAge = age;
  log("OCEANTEST", JSON.stringify({ turn, age, id: player.id, unit: GameInfo.Units.lookup(unit.type)?.UnitType,
    from: { x: unit.location.x, y: unit.location.y }, to: { x: px, y: py }, canStart: !!result?.Success, path }));
}

// Asks the engine whether the player's ships may move onto deep ocean near them.
// Only a civ past its gate may. Does not depend on the AI choosing to sail there.
function oceanProbe(player, oceanIndex, hasGate, turn) {
  const width = GameplayMap.getGridWidth();
  const height = GameplayMap.getGridHeight();
  let ships = 0, probed = 0, allowed = 0, first = null;
  for (const unitId of player.Units?.getUnitIds() ?? []) {
    const unit = Units.get(unitId);
    if (!unit || GameInfo.Units.lookup(unit.type)?.Domain !== "DOMAIN_SEA") continue;
    ships++;
    const { x, y } = unit.location;
    for (let dy = -3; dy <= 3 && probed < 12; dy++) {
      for (let dx = -3; dx <= 3 && probed < 12; dx++) {
        const px = (x + dx + width) % width, py = y + dy;
        if (py < 0 || py >= height || GameplayMap.getTerrainType(px, py) !== oceanIndex) continue;
        probed++;
        const result = Game.UnitOperations.canStart(unit.id, UnitOperationTypes.MOVE_TO,
          { X: px, Y: py, Modifiers: UnitOperationMoveModifiers.MOVE_IGNORE_UNEXPLORED_DESTINATION }, false);
        if (result?.Success) {
          const path = pathEndsAt(unit, px, py, oceanIndex);
          oceanSample(player, unit, px, py, result, path, turn);
          if (!path.ok) continue;
          allowed++;
          first ??= `${GameInfo.Units.lookup(unit.type)?.UnitType} at ${x},${y} to ${px},${py}, moves ${unit.Movement?.movementMovesRemaining}, path ${path.length}`;
        }
      }
    }
  }
  if (allowed > 0 && !hasGate) {
    log("FAIL", `turn ${turn}: player ${player.id} may move ships onto deep ocean without ${GATE} (${first})`);
  }
  return { ships, probed, allowed };
}

// Upgrades. UPGRADES_TO_EX: Antiquity unit type -> its Exploration successor.
const EX_UNITS = new Set();
for (const u of GameInfo.ProgressionTreeNodeUnlocks) {
  if (u.TargetKind === "KIND_UNIT" && u.ProgressionTreeNodeType.startsWith("NODE_TECH_EX_")) EX_UNITS.add(u.TargetType);
}
const UPGRADES_TO_EX = new Map();
for (const row of GameInfo.UnitUpgrades) {
  if (EX_UNITS.has(row.UpgradeUnit) && !EX_UNITS.has(row.Unit)) UPGRADES_TO_EX.set(row.Unit, row.UpgradeUnit);
}
const lastUnitType = new Map(); // unit id -> unit type seen at the last check

// Logs a unit that kept its id but changed into its successor (an upgrade), and asks the
// engine whether units with an Exploration successor may upgrade now.
function upgradeCheck(player, turn) {
  let eligible = 0, allowed = 0;
  for (const unitId of player.Units?.getUnitIds() ?? []) {
    const unit = Units.get(unitId);
    if (!unit) continue;
    const type = GameInfo.Units.lookup(unit.type)?.UnitType;
    const key = `${unitId.owner}:${unitId.id}`;
    const before = lastUnitType.get(key);
    if (before && before !== type) {
      log("UPGRADE", JSON.stringify({ turn, id: player.id, from: before, to: type, toExploration: EX_UNITS.has(type) }));
    }
    lastUnitType.set(key, type);
    if (UPGRADES_TO_EX.has(type)) {
      eligible++;
      const result = Game.UnitCommands.canStart(unitId, "UNITCOMMAND_UPGRADE", {}, false);
      if (result?.Success) allowed++;
    }
  }
  return { eligible, allowed };
}

// Values that an age transition could reset: gold, settlements, units, completed techs and civics.
const TREE_SYSTEM = new Map();
for (const tree of GameInfo.ProgressionTrees) TREE_SYSTEM.set(tree.ProgressionTreeType, tree.SystemType);
// Civic trees the player has (a tree a player does not have shows its nodes as not unlocked),
// and the traditions and policies unlocked (the effect of civics, kept across ages in the base game).
// Snowball measures: settlement cap, population, buildings, science and culture per turn.
// Constructible types in the civ's settlements, logged in chunks (UI.log cuts long lines).
function logConstructibles(kind, player, extra) {
  const types = [];
  for (const id of player.Cities?.getCityIds() ?? []) {
    for (const cid of Cities.get(id)?.Constructibles?.getIds() ?? []) {
      const c = Constructibles.getByComponentID(cid);
      const t = c ? GameInfo.Constructibles.lookup(c.type)?.ConstructibleType : null;
      if (t) types.push(t.replace(/^(BUILDING|IMPROVEMENT|WONDER)_/, ""));
    }
  }
  types.sort();
  for (let i = 0; i < types.length; i += 30) {
    console.warn(`[CA-CHECK][${kind}] ${JSON.stringify({ ...extra, id: player.id, part: i / 30, types: types.slice(i, i + 30) })}`);
  }
}
function logChunks(kind, extra, key, list) {
  for (let i = 0; i === 0 || i < list.length; i += 30) {
    console.warn(`[CA-CHECK][${kind}] ${JSON.stringify({ ...extra, part: i / 30, [key]: list.slice(i, i + 30) })}`);
  }
}
function unitTypes(player) {
  return (player.Units?.getUnitIds() ?? []).map((uid) => (GameInfo.Units.lookup(Units.get(uid)?.type)?.UnitType ?? "?")
    .replace(/^UNIT_/, "")).sort();
}
function growthState(player) {
  const st = player.Stats;
  let buildings = 0;
  for (const id of player.Cities?.getCityIds() ?? []) buildings += (Cities.get(id)?.Constructibles?.getIds() ?? []).length;
  // Unit experience (U5): promotions and levels summed over the civ's units.
  let promotions = 0, levels = 0;
  for (const uid of player.Units?.getUnitIds() ?? []) {
    const xp = Units.get(uid)?.Experience;
    promotions += Number(xp?.getNumPromotions ?? 0);
    levels += Number(xp?.getLevel ?? 0);
  }
  return {
    promotions, levels,
    cap: st?.settlementCap ?? -1, pop: st?.totalPopulation ?? -1, buildings,
    sci: Math.round(st?.getNetYield(YieldTypes.YIELD_SCIENCE) ?? -1),
    cul: Math.round(st?.getNetYield(YieldTypes.YIELD_CULTURE) ?? -1),
  };
}
// MINORS record: independents and city-states do not use the civ-age gates. Which tech nodes and
// unit types do they have (iteration 20261025-022511: an independent had Frigates in the Exploration
// world, and a major civ then held one before its Modern gate)?
function minorsRecord(turn) {
  try {
    const age = GameInfo.Ages.lookup(Game.age)?.AgeType;
    let n = 0;
    for (const player of Players.getAlive()) {
      if (player.isMajor || n >= 4) continue;
      n++;
      const nodes = { AQ: 0, EX: 0, MO: 0, gateEX: 0, gateMO: 0 };
      for (const node of GameInfo.ProgressionTreeNodes) {
        if (node.ProgressionTree !== "TREE_TECHS_AQ") continue;
        if (Game.ProgressionTrees.getNodeState(player.id, node.$hash) < ProgressionTreeNodeState.NODE_STATE_FULLY_UNLOCKED) continue;
        const t = node.ProgressionTreeNodeType;
        if (t === "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH") nodes.gateEX++;
        else if (t === "NODE_TECH_CA_MODERN_BREAKTHROUGH") nodes.gateMO++;
        else if (t.startsWith("NODE_TECH_AQ_")) nodes.AQ++;
        else if (t.startsWith("NODE_TECH_EX_")) nodes.EX++;
        else if (t.startsWith("NODE_TECH_MO_")) nodes.MO++;
      }
      const units = [...new Set(unitTypes(player))].slice(0, 12);
      log("MINORS", JSON.stringify({ age, turn, id: player.id, nodes, units }));
    }
  } catch (e) {
    log("ERROR", `minors record: ${e}`);
  }
}

// Policy names (POLICIES record): the policy count fell by one at the Antiquity transition.
function policyNames(player) {
  return (player.Culture?.getUnlockedTraditions(CultureSlotTypes.POLICY_CULTURE_SLOT) ?? [])
    .map((t) => (GameInfo.Traditions.lookup(t)?.TraditionType ?? `${t}`).replace("TRADITION_", "")).sort();
}
function cultureState(player) {
  const c = player.Culture;
  const name = (t) => (GameInfo.ProgressionTrees.lookup(t)?.ProgressionTreeType ?? `${t}`).replace("TREE_CIVICS_", "");
  return {
    trees: (c?.getAvailableTrees() ?? []).map(name),
    traditions: (c?.getUnlockedTraditions(CultureSlotTypes.TRADITION_CULTURE_SLOT) ?? []).length,
    policies: (c?.getUnlockedTraditions(CultureSlotTypes.POLICY_CULTURE_SLOT) ?? []).length,
  };
}
function continuityState(player) {
  let techs = 0, civics = 0;
  const civicNodes = [];
  for (const node of GameInfo.ProgressionTreeNodes) {
    if (Game.ProgressionTrees.getNodeState(player.id, node.$hash) < ProgressionTreeNodeState.NODE_STATE_FULLY_UNLOCKED) continue;
    const system = TREE_SYSTEM.get(node.ProgressionTree);
    if (system === "SYSTEM_TECH") techs++;
    else if (system === "SYSTEM_CULTURE") { civics++; civicNodes.push(node.ProgressionTreeNodeType.replace("NODE_CIVIC_", "")); }
  }
  let cities = 0, towns = 0;
  for (const id of player.Cities?.getCityIds() ?? []) {
    if (Cities.get(id)?.isTown) towns++; else cities++;
  }
  return {
    gold: Math.round(player.Treasury?.goldBalance ?? -1), cities, towns,
    units: (player.Units?.getUnitIds() ?? []).length, techs, civics, civicNodes, ...cultureState(player), ...growthState(player),
  };
}

function short(type) {
  return type.replace(/^BUILDING_/, "");
}

// Asks the engine, as the production screen does, whether the capital may build each
// Exploration building. Separates "the engine blocks it" from "the AI does not choose it".
function buildCheck(player, turn) {
  const capitalId = (player.Cities?.getCityIds() ?? []).find((id) => Cities.get(id)?.isCapital);
  const city = capitalId !== undefined ? Cities.get(capitalId) : null;
  if (!city) return;
  const results = Game.CityOperations.canStartQuery(city.id, CityOperationTypes.BUILD, CityQueryType.Constructible) ?? [];
  const byIndex = new Map(results.map(({ index, result }) => [index, result]));
  const out = { turn, id: player.id, ok: [], needUnlock: [], noPlot: [], exists: [], other: [], notListed: 0 };
  for (const def of GameInfo.Constructibles) {
    if (!EX_CONSTRUCTIBLES.has(def.ConstructibleType) || def.ConstructibleClass !== "BUILDING") continue;
    const r = byIndex.get(def.$index);
    if (!r) { out.notListed++; continue; }
    const name = short(def.ConstructibleType);
    if (r.Success) out.ok.push(name);
    else if (r.AlreadyExists) out.exists.push(name);
    else if (r.NeededUnlock !== undefined && r.NeededUnlock != -1) out.needUnlock.push(name);
    else if (!r.Plots || r.Plots.length === 0) out.noPlot.push(name);
    else out.other.push(name);
  }
  // Space check: Antiquity buildings that the city has not built yet. If these have no
  // valid plot either, the city is full (no room left, not a missing tech).
  out.aq = { ok: 0, noPlot: 0, needUnlock: 0 };
  for (const def of GameInfo.Constructibles) {
    if (EX_CONSTRUCTIBLES.has(def.ConstructibleType) || def.ConstructibleClass !== "BUILDING") continue;
    const r = byIndex.get(def.$index);
    if (!r || r.AlreadyExists) continue;
    if (r.Success) out.aq.ok++;
    else if (r.NeededUnlock !== undefined && r.NeededUnlock != -1) out.aq.needUnlock++;
    else if (!r.Plots || r.Plots.length === 0) out.aq.noPlot++;
  }
  out.cityBuildings = (city.Constructibles?.getIds() ?? []).length;
  for (const key of ["ok", "needUnlock", "noPlot", "exists", "other"]) {
    out[key] = { n: out[key].length, sample: out[key].slice(0, 4) };
  }
  log("BUILD", JSON.stringify(out));
}

// Gate check: items unlocked by a later age's techs or civics, for a civ that has not passed
// that age's gate. The engine should refuse them (NeededUnlock). Asks the production screen's query.
const LATER_ITEMS = { EX: new Set(), MO: new Set() };
for (const u of GameInfo.ProgressionTreeNodeUnlocks) {
  const n = u.ProgressionTreeNodeType;
  // Main trees only: a civ's unique tree (NODE_CIVIC_EX_ABBASID_...) is gated by the civ itself.
  const age = /^NODE_(TECH_EX|CIVIC_EX_MAIN)_/.test(n) ? "EX" : /^NODE_(TECH_MO|CIVIC_MO_MAIN)_/.test(n) ? "MO" : null;
  if (age && (u.TargetKind === "KIND_UNIT" || u.TargetKind === "KIND_CONSTRUCTIBLE")) LATER_ITEMS[age].add(u.TargetType);
}
function gateCheck(player, turn, civAge) {
  const capitalId = (player.Cities?.getCityIds() ?? []).find((id) => Cities.get(id)?.isCapital);
  if (capitalId === undefined) return;
  const locked = civAge === "AQ" ? ["EX", "MO"] : civAge === "EX" ? ["MO"] : [];
  if (locked.length === 0) return;
  const out = { age: GameInfo.Ages.lookup(Game.age)?.AgeType, turn, id: player.id, civAge, ok: [], needUnlock: 0, other: 0, notListed: 0 };
  for (const [query, table, key] of [[CityQueryType.Unit, GameInfo.Units, "UnitType"],
                                     [CityQueryType.Constructible, GameInfo.Constructibles, "ConstructibleType"]]) {
    const results = Game.CityOperations.canStartQuery(capitalId, CityOperationTypes.BUILD, query) ?? [];
    const byIndex = new Map(results.map(({ index, result }) => [index, result]));
    for (const def of table) {
      const type = def[key];
      if (!locked.some((a) => LATER_ITEMS[a].has(type))) continue;
      const r = byIndex.get(def.$index);
      if (!r) out.notListed++;
      else if (r.Success) out.ok.push(type.replace(/^(UNIT|BUILDING)_/, ""));
      else if (r.NeededUnlock !== undefined && r.NeededUnlock != -1) out.needUnlock++;
      else {
        out.other++;
        if (!out.otherSample) out.otherSample = { type, keys: Object.keys(r).slice(0, 12), reasons: r.FailureReasons ?? null };
      }
    }
  }
  if (out.ok.length > 0) {
    log("FAIL", `turn ${turn}: player ${player.id} (civ age ${civAge}) may start later-age items: ${out.ok.slice(0, 8).join(",")}`);
  }
  out.ok = { n: out.ok.length, sample: out.ok.slice(0, 6) };
  log("GATE", JSON.stringify(out));
}

// The world snapshot runs once per checked turn. Each civ is checked during its own turn:
// the engine answers placement and upgrade queries only for the player whose turn is active
// (checking all civs at once gave "no valid plot" for every civ but the active one).
function worldSnapshot(turn) {
  const ageType = GameInfo.Ages.lookup(Game.age)?.AgeType;
  log("SNAPSHOT", JSON.stringify({
    turn, age: ageType,
    ageProgress: Game.AgeProgressManager.getCurrentAgeProgressionPoints(),
    ageMax: Game.AgeProgressManager.getMaxAgeProgressionPoints(),
  }));
  if (lastAge !== null && ageType !== lastAge) {
    log("AGECHANGE", JSON.stringify({ turn, from: lastAge, to: ageType }));
  }
  lastAge = ageType;
}
let lastAge = null;

function playerCheck(player, turn) {
  const oceanIndex = GameInfo.Terrains.lookup("TERRAIN_OCEAN")?.$index;
  const id = player.id;
  const worldAge = GameInfo.Ages.lookup(Game.age)?.AgeType;
  const gate = hasNode(id, GATE);
  const moGate = hasNode(id, MO_GATE);
  const ocean = hasNode(id, OCEAN_TECH);
  const exTechs = explorationTechs(id);
  const moTechs = explorationTechs(id, "NODE_TECH_MO_");
  const civAge = moGate ? "MO" : gate ? "EX" : "AQ";
  const onOcean = oceanUnits(player, oceanIndex);
  // In an Antiquity world, deep ocean is open only to civs past their Exploration Breakthrough.
  // From the Exploration world on, the world baseline opens it to every civ.
  if (worldAge === "AGE_ANTIQUITY" && onOcean.length > 0 && !gate) {
    log("FAIL", `turn ${turn}: player ${id} has units on deep ocean without ${GATE}: ${onOcean.slice(0, 5).join(",")}`);
  }
  if (exTechs > 0 && !gate) {
    log("FAIL", `turn ${turn}: player ${id} has Exploration techs without the gate: ${completedNodes(id, "NODE_TECH_EX_").join(",")}`);
  }
  const exCivics = explorationTechs(id, "NODE_CIVIC_EX_MAIN_");
  const moCivics = explorationTechs(id, "NODE_CIVIC_MO_MAIN_");
  if ((exCivics > 0 && !gate) || (moCivics > 0 && !moGate)) {
    log("FAIL", `turn ${turn}: player ${id} has main-tree civics of an age it has not entered (EX ${exCivics}, MO ${moCivics})`);
  }
  if (moTechs > 0 && !moGate) {
    log("FAIL", `turn ${turn}: player ${id} has Modern techs without ${MO_GATE}: ${completedNodes(id, "NODE_TECH_MO_").join(",")}`);
  }
  const buildings = explorationBuildings(player);
  log("PLAYER", JSON.stringify({
    age: worldAge, turn, id, civAge,
    civ: (GameInfo.Civilizations.lookup(player.civilizationType)?.CivilizationType ?? "").replace("CIVILIZATION_", ""),
    gate, oceanTech: ocean, exTechs, moTechs, exCivics, moCivics,
    exBuildings: buildings.length, exBuildingTypes: [...new Set(buildings)].slice(0, 4).map(short),
    unitsOnOcean: onOcean.length,
    oceanProbe: oceanProbe(player, oceanIndex, gate || worldAge !== "AGE_ANTIQUITY", turn),
    upgrade: upgradeCheck(player, turn),
      gov: (GameInfo.Governments.lookup(player.Culture?.getGovernmentType())?.GovernmentType ?? "").replace("GOVERNMENT_", ""),
  }));
  const { civicNodes, ...state } = continuityState(player);
  log("STATE", JSON.stringify({ age: worldAge, turn, id, civAge, ...state }));
  if (firstCheckAfterLoad) logChunks("CIVICS", { when: "start", age: worldAge, id }, "nodes", civicNodes);
  if (firstCheckAfterLoad) logChunks("UNITS", { when: "start", age: worldAge, id }, "types", unitTypes(player));
  if (firstCheckAfterLoad) logChunks("POLICIES", { when: "start", age: worldAge, id }, "types", policyNames(player));
  // Engine state of each node in the civ's own unique trees (any age) and in the Test of Time
  // trees: a civ that kept its civ lost its unique civics at the load (Egypt, iteration 20261024-214035).
  if (firstCheckAfterLoad) {
    const civ = (GameInfo.Civilizations.lookup(player.civilizationType)?.CivilizationType ?? "").replace("CIVILIZATION_", "");
    const states = [];
    for (const node of GameInfo.ProgressionTreeNodes) {
      const tree = node.ProgressionTree;
      if (!/^TREE_CIVICS_(AQ|EX|MO)_/.test(tree) || !(tree.endsWith(`_${civ}`) || tree.endsWith("_TEST_OF_TIME"))) continue;
      states.push(`${node.ProgressionTreeNodeType.replace("NODE_CIVIC_", "")}=${Game.ProgressionTrees.getNodeState(id, node.$hash)}`);
    }
    logChunks("TREESTATE", { age: worldAge, id, civ, fully: ProgressionTreeNodeState.NODE_STATE_FULLY_UNLOCKED,
      trees: (player.Culture?.getAvailableTrees() ?? []).map((t) => GameInfo.ProgressionTrees.lookup(t)?.ProgressionTreeType ?? `${t}`) },
      "nodes", states);
  }
  if (firstCheckAfterLoad) logConstructibles("CONS", player, { when: "start", age: worldAge });
  if (turn % BUILD_CHECK_EVERY === 0) buildCheck(player, turn);
  if (turn % GATE_CHECK_EVERY === 0) gateCheck(player, turn, civAge);
}

// Civ abilities behind the gate (rule 5e): the game effects library lists modifiers. Its call shapes
// are not documented, so the first call logs them (GEPROBE); GATEMODS counts the CA_GATE_ copies per
// owner and how many are active, at the first check of each age and every 20 turns.
function safeCall(f) {
  try { return f(); } catch (e) { return `error ${e}`; }
}
let geProbed = false;
function gateModsCheck(turn) {
  const GE = typeof GameEffects !== "undefined" ? GameEffects : null;
  if (!geProbed) {
    geProbed = true;
    const info = { type: typeof GameEffects, keys: GE ? Object.keys(Object.getPrototypeOf(GE) ?? {}).concat(Object.keys(GE)).slice(0, 40) : null };
    if (GE) {
      const mods = safeCall(() => GE.getModifiers());
      const m0 = Array.isArray(mods) ? mods[0] : null;
      const id0 = m0?.id ?? m0;
      info.count = safeCall(() => GE.getModifierCount());
      info.modsType = Array.isArray(mods) ? `array ${mods.length}` : typeof mods;
      info.first = safeCall(() => JSON.stringify(m0)?.slice(0, 300));
      info.def = safeCall(() => JSON.stringify(GE.getModifierDefinition(id0))?.slice(0, 300));
      info.owner = safeCall(() => JSON.stringify(GE.getModifierOwner(id0))?.slice(0, 200));
      info.active = safeCall(() => GE.getModifierActive(id0));
    }
    log("GEPROBE", JSON.stringify(info));
  }
  if (!GE) return;
  const mods = GE.getModifiers();
  if (!Array.isArray(mods)) return;
  const owners = {};
  for (const m of mods) {
    const id = m?.id ?? m;
    const def = GE.getModifierDefinition(id);
    const name = String(def?.id ?? def?.ModifierId ?? def?.name ?? def?.type ?? "");
    const kind = ["CA_GATE_", "CA_ATTACH_REGRANT_", "CA_REGRANT_"].find((k) => name.startsWith(k));
    if (!kind) continue;
    const o = GE.getModifierOwner(id);
    const key = `${kind}${String(o?.owner ?? o?.id ?? o)}`;
    const e = owners[key] ??= [0, 0];
    e[0]++;
    if (GE.getModifierActive(id)) e[1]++;
  }
  log("GATEMODS", JSON.stringify({ turn, age: GameInfo.Ages.lookup(Game.age)?.AgeType, owners }));
}
let gateModsTurn = -1;

engine.on("PlayerTurnActivated", (data) => {
  try {
    const turn = Game.turn;
    // Also check the first turn after a load (an age transition is a load): it shows what the
    // transition kept, before the new age's turns can change it.
    if (turn % SNAPSHOT_EVERY !== 0 && lastTurnChecked !== -1 && turn !== lastTurnChecked) return;
    firstCheckAfterLoad = lastTurnChecked === -1 || (firstCheckAfterLoad && turn === lastTurnChecked);
    if (turn !== lastTurnChecked) {
      lastTurnChecked = turn;
      worldSnapshot(turn);
      if (firstCheckAfterLoad || turn % 20 === 0) minorsRecord(turn);
      if ((firstCheckAfterLoad || turn % 20 === 0) && gateModsTurn !== turn) {
        gateModsTurn = turn;
        try { gateModsCheck(turn); } catch (e) { log("GEPROBE", `gate mods error: ${e}`); }
      }
    }
    const player = Players.get(data?.player);
    if (player && player.isMajor && player.isAlive) playerCheck(player, turn);
  } catch (e) {
    log("ERROR", `${e}`);
  }
});
log("INFO", "checks loaded");
