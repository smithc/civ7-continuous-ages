// Scenario test of a later-age DLC wonder whose node is researched in an earlier world (a player report of 2026-11-14:
// "somewhere along the way the Battersea Power Station disappeared"). Build: build_mod.py --install --checks
// --age-points 8 --fast-test 0.01; suite: ContinuousAgesLive.json --set StartAge=AGE_EXPLORATION. Needs the Great
// Britain DLC (the scenario fails at its first check without it).
// The DLC loads the wonder and its unlock (Electricity's mastery) only from the Modern world on. The base game's
// Electricity unlock (the Laboratory) is copied by the mod into the earlier worlds.
// Phase 1 (Exploration world): the Modern Breakthrough (granted); Electricity researched the normal way to its mastery.
// The Laboratory needs no unlock (control); the wonder has no row in this world.
// Phase 2 (Modern world): the Laboratory needs no unlock (control); the Battersea Power Station needs no unlock (the test).
const me = GameContext.localPlayerID;
const MOG = "NODE_TECH_CA_MODERN_BREAKTHROUGH", ELECTRICITY = "NODE_TECH_MO_ELECTRICITY";
const WONDER = "WONDER_BATTERSEA_POWER_STATION", LAB = "BUILDING_LABORATORY";
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "dlc_wonder_world", phase: 1, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
// The grant is sent up to 3 times, 10 s each: in the set 20261125-111722 (6 games at once) one request did not take
// effect (20261125-113556-w1, gate depth 0).
async function grant(node) {
  for (let t = 0; t < 3 && depth(node) < 1; t++) { caLive.grantNode(node); for (let i = 0; i < 20 && depth(node) < 1; i++) await settle(500); }
  return depth(node) >= 1;
}
async function research(node, target) {
  const pre = {};
  for (const r of Array.from(GameInfo.ProgressionTreePrereqs).filter((p) => p.Node === node)) pre[r.PrereqNode] = depth(r.PrereqNode) >= 1 || await grant(r.PrereqNode);
  const args = { ProgressionTreeNodeType: GameInfo.ProgressionTreeNodes.lookup(node).$hash };
  const can = !!Game.PlayerOperations.canStart(me, PlayerOperationTypes.SET_TECH_TREE_NODE, args, false)?.Success;
  if (can) Game.PlayerOperations.sendRequest(me, PlayerOperationTypes.SET_TECH_TREE_NODE, args);
  await settle();
  let turns = 0;
  for (; turns < 10 && depth(node) < target; turns++) await caLive.endTurn();
  return { node, target, pre, can, turns, depth: depth(node), turn: Game.turn };
}
const capital = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const query = (type) => {
  const def = GameInfo.Constructibles.lookup(type);
  const r = (Game.CityOperations.canStartQuery(capital().id, CityOperationTypes.BUILD, CityQueryType.Constructible) ?? []).find((x) => x.index === def?.$index)?.result;
  const fields = {};
  if (r) for (const k of Object.keys(r)) fields[k] = Array.isArray(r[k]) ? r[k].length : r[k];
  return { listed: !!r, ok: !!r?.Success, locked: r?.Locked === true, neededUnlock: r?.NeededUnlock ?? null, fields };
};
// Locked: the query's Locked field, or a node in NeededUnlock (probe 2026-11-24, Modern world: Battersea without
// Electricity Locked true, NeededUnlock a node; with Electricity mastered Success true, NeededUnlock -1).
const needs = (r) => r.locked || (r.neededUnlock !== null && r.neededUnlock !== undefined && r.neededUnlock != -1);
// The DLC loads the wonder from the Modern world on (its "persist" group: the Modern age and later), so the Exploration
// world has no row for it. The DLC's own text shows that the DLC is loaded.
const dlcText = Locale.compose("LOC_WONDER_BATTERSEA_POWER_STATION_NAME");
expect("setup: the Great Britain DLC is loaded (its text exists); the wonder has no row in the Exploration world",
  dlcText !== "LOC_WONDER_BATTERSEA_POWER_STATION_NAME" && !GameInfo.Constructibles.lookup(WONDER), { dlcText, row: !!GameInfo.Constructibles.lookup(WONDER) });
if (dlcText === "LOC_WONDER_BATTERSEA_POWER_STATION_NAME") return { ok: false, checks };
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
expect("setup: the Modern Breakthrough is granted", await grant(MOG), { gate: depth(MOG) });
const e1 = await research(ELECTRICITY, 1);
const e2 = await research(ELECTRICITY, 2);
expect("setup: Electricity researched to its mastery", depth(ELECTRICITY) >= 2, { e1, e2 });
const lab1 = query(LAB);
expect("control: the Laboratory needs no unlock in the Exploration world", lab1.listed && !needs(lab1), lab1);
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
for (let i = 0; i < 30 && left() > 3; i++) await caLive.advance(1);
for (let i = 0; i < 12 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { if (left() >= 2) await caLive.advance(1); } }
expect("the age is at its end", left() <= 0, { turn: Game.turn, left: left() });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((c) => c.ok), checks, transition: { auto: true } };

//// PHASE 2: the Modern world
const me = GameContext.localPlayerID;
const ELECTRICITY = "NODE_TECH_MO_ELECTRICITY", WONDER = "WONDER_BATTERSEA_POWER_STATION", LAB = "BUILDING_LABORATORY";
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "dlc_wonder_world", phase: 2, name, ok, detail }); };
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const capital = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const query = (type) => {
  const def = GameInfo.Constructibles.lookup(type);
  const r = (Game.CityOperations.canStartQuery(capital().id, CityOperationTypes.BUILD, CityQueryType.Constructible) ?? []).find((x) => x.index === def?.$index)?.result;
  const fields = {};
  if (r) for (const k of Object.keys(r)) fields[k] = Array.isArray(r[k]) ? r[k].length : r[k];
  return { listed: !!r, ok: !!r?.Success, locked: r?.Locked === true, neededUnlock: r?.NeededUnlock ?? null, fields };
};
// Locked: the query's Locked field, or a node in NeededUnlock (probe 2026-11-24, Modern world: Battersea without
// Electricity Locked true, NeededUnlock a node; with Electricity mastered Success true, NeededUnlock -1).
const needs = (r) => r.locked || (r.neededUnlock !== null && r.neededUnlock !== undefined && r.neededUnlock != -1);
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
expect("the world is Modern, slot 0 is human and has Electricity mastered", world === "AGE_MODERN" && Players.get(me).isHuman && depth(ELECTRICITY) >= 2,
  { world, turn: Game.turn, electricity: depth(ELECTRICITY) });
const lab = query(LAB), won = query(WONDER);
const rows = Array.from(GameInfo.ProgressionTreeNodeUnlocks).filter((r) => r.TargetType === WONDER).map((r) => `${r.ProgressionTreeNodeType}@${r.UnlockDepth}`);
expect("control: the Laboratory needs no unlock in the Modern world", lab.listed && !needs(lab), lab);
// Positive control of the query: a Modern wonder whose only unlock nodes slot 0 does not have needs an unlock.
const wonderRows = Array.from(GameInfo.ProgressionTreeNodeUnlocks).filter((r) => r.TargetKind === "KIND_CONSTRUCTIBLE"
  && GameInfo.Constructibles.lookup(r.TargetType)?.ConstructibleClass === "WONDER" && r.TargetType !== WONDER);
const lockedWonder = [...new Set(wonderRows.map((r) => r.TargetType))].find((w) => GameInfo.Constructibles.lookup(w)?.Age === "AGE_MODERN"
  && wonderRows.filter((r) => r.TargetType === w).every((r) => depth(r.ProgressionTreeNodeType) < (r.UnlockDepth ?? 1)));
const locked = lockedWonder ? query(lockedWonder) : null;
expect("control: a Modern wonder whose node slot 0 lacks needs an unlock (the query can show a lock)",
  !!locked && locked.listed && needs(locked), { wonder: lockedWonder, ...locked });
expect("test: the Battersea Power Station needs no unlock in the Modern world (Electricity mastered in the Exploration world)",
  won.listed && !needs(won), { ...won, rows });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
