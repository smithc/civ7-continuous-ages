// Scenario test of rule 2n in a game updated from 0.5.1 during a world age (build: build_mod.py --install --checks
// --age-points 12 --fast-test 0.01; suite: ContinuousAgesLiveLoad.json --set SaveName=CA_UPD051_AQ). The save comes from
// make_save_051.js with the rules of 0.5.1: slot 0 is past its Exploration Breakthrough and has Currency at depth 1 (its
// original modifier attached), and no Shipbuilding. Rule 2n works through the nodes' own unlock rows, so:
// Phase 1 (the loaded Antiquity world): controls (the save, the rule's rows in the database, the original modifier still
// active, a Cog takes deep-ocean damage without Shipbuilding); tests: Shipbuilding researched AFTER the update gives its
// protection at once, and its mastery attaches the hidden copy; known limit, checked so that a change is seen: the
// mastery of a node whose ADDITIVE depth-1 modifier was attached before the update adds the effect once more until the
// next world (Currency: +1 specialist cap again; the old instance cannot be stopped).
// Phase 2 (the Exploration world): tests: the copies of depth 2 are active, the original modifier and the double are
// gone (the capital's specialist cap changes by the world's own amount less the double), and ships take no deep-ocean
// damage.
const me = GameContext.localPlayerID;
const CURRENCY = "NODE_TECH_AQ_CURRENCY", SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const CAP = "MOD_AQ_SPECIALIST_CAP_INCREASE", WATER = "MOD_TECH_EX_NO_OCEAN_DAMAGE";
const OCEAN = GameInfo.Terrains.lookup("TERRAIN_OCEAN").$index;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "update_051", phase: 1, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const capital = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const worker = () => capital()?.Workers?.getCityWorkerCap() ?? -1;
const active = () => new Set(Players.get(me).Modifiers.getModifiers().map((m) => GameEffects.getModifierDefinitionFromTypeId(m.modifierType)?.ID));
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const rows = ((globalThis.caMasterySplit ?? {})[world] ?? []);
const row = (node, modifier) => rows.find((e) => e.node === node && e.modifier === modifier) ?? {};
const cur = row(CURRENCY, CAP), ship = row(SHIPBUILDING, WATER);
const has = (set) => ({ original: set.has(CAP), curLow: set.has(cur.low), curHigh: set.has(cur.high), water: set.has(WATER), shipLow: set.has(ship.low), shipHigh: set.has(ship.high) });
async function research(node, target) {
  const pre = {};
  for (const r of Array.from(GameInfo.ProgressionTreePrereqs).filter((p) => p.Node === node)) {
    if (depth(r.PrereqNode) < 1) { caLive.grantNode(r.PrereqNode); for (let i = 0; i < 10 && depth(r.PrereqNode) < 1; i++) await settle(500); }
    pre[r.PrereqNode] = depth(r.PrereqNode) >= 1;
  }
  const args = { ProgressionTreeNodeType: GameInfo.ProgressionTreeNodes.lookup(node).$hash };
  const can = !!Game.PlayerOperations.canStart(me, PlayerOperationTypes.SET_TECH_TREE_NODE, args, false)?.Success;
  if (can) Game.PlayerOperations.sendRequest(me, PlayerOperationTypes.SET_TECH_TREE_NODE, args);
  await settle();
  let turns = 0;
  for (; turns < 10 && depth(node) < target; turns++) await caLive.endTurn();
  return { node, target, pre, can, turns, depth: depth(node), turn: Game.turn };
}
Visibility.revealAllPlots(me);
await settle();
const home = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital).location;
const dist = (a, b) => Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y));
const freeOcean = () => {
  const out = [];
  for (let x = 0; x < GameplayMap.getGridWidth(); x++) for (let y = 0; y < GameplayMap.getGridHeight(); y++)
    if (GameplayMap.getTerrainType(x, y) === OCEAN && (MapUnits.getUnits(x, y)?.length ?? 0) === 0) out.push({ x, y, d: dist({ x, y }, home) });
  return out.sort((a, b) => a.d - b.d);
};
const onOcean = (u) => GameplayMap.getTerrainType(u.location.x, u.location.y) === OCEAN;
const state = (u) => u ? { id: u.id, x: u.location.x, y: u.location.y, ocean: onOcean(u), damage: u.Health?.damage } : null;
async function shipOnOcean(type, skip = 0) {
  for (let i = skip; i < skip + 6; i++) {
    const p = freeOcean()[i * 2];
    const u = p ? await caLive.createUnitAndWait(type, p.x, p.y) : null;
    if (u && onOcean(Units.get(u.id))) return Units.get(u.id);
  }
  return null;
}
const s0 = { world, turn: Game.turn, human: Players.get(me).isHuman, currency: depth(CURRENCY), shipbuilding: depth(SHIPBUILDING), worker: worker(),
  rows: { cur: [cur.low, cur.high], ship: [ship.low, ship.high] }, active: has(active()),
  // the game's own unlock table has the rule's rows (not only the build's list): Currency names its copy at depth 1, and both hidden rows are at depth 2
  inDatabase: [[CURRENCY, cur.low, 1], [CURRENCY, cur.high, 2], [SHIPBUILDING, ship.high, 2], [SHIPBUILDING, WATER, 1]].map(([n, t, d]) =>
    Array.from(GameInfo.ProgressionTreeNodeUnlocks).some((u) => u.ProgressionTreeNodeType === n && u.TargetType === t && u.UnlockDepth === d)) };
expect("control: the 0.5.1 save loaded with this build (Antiquity, slot 0 human, Currency 1, no Shipbuilding, rule 2n's rows in the database)",
  world === "AGE_ANTIQUITY" && s0.human && s0.currency === 1 && s0.shipbuilding === 0 && cur.kind === "additive" && !!cur.low && !!cur.high
  && ship.kind === "switch" && !ship.low && !!ship.high && s0.inDatabase.every((x) => x === true), s0);
expect("control: Currency's original modifier, attached under 0.5.1, is still active (and no copy)", s0.active.original && !s0.active.curLow && !s0.active.curHigh, s0.active);
// Control (rule 6b), and the research of Shipbuilding after the update.
const cogA = await shipOnOcean("UNIT_COG", 0);
const a0 = cogA?.Health.damage;
const ship1 = await research(SHIPBUILDING, 1);
const a1 = cogA ? Units.get(cogA.id) : null;
expect("control: without Shipbuilding, a Cog on deep ocean takes damage (rule 6b)", !!cogA && ship1.turns >= 1 && (!a1 || a1.Health.damage > a0),
  { before: a0, now: state(a1), gone: !!cogA && !a1, turns: ship1.turns });
const s1 = has(active());
expect("test: Shipbuilding researched after the update: its modifier is active (a switch effect: the row is as in the base game), not the depth-2 copy",
  ship1.depth === 1 && s1.water && !s1.shipHigh, { ship1, active: s1 });
const cogB = await shipOnOcean("UNIT_COG", 1);
const b0 = cogB?.Health.damage;
await caLive.endTurn();
const b1 = cogB ? Units.get(cogB.id) : null;
expect("test: with Shipbuilding researched after the update, a new Cog on deep ocean takes no damage", !!b1 && onOcean(b1) && b1.Health.damage === b0, { before: b0, now: state(b1) });
const ship2 = await research(SHIPBUILDING, 2);
const s2 = has(active());
expect("test: Shipbuilding mastered: the depth-2 copy is active too", ship2.depth === 2 && s2.shipHigh, { ship2, active: s2 });
const cogC = await shipOnOcean("UNIT_COG", 2);
const c0 = cogC?.Health.damage;
await caLive.endTurn();
const c1 = cogC ? Units.get(cogC.id) : null;
expect("test: with Shipbuilding mastered, a new Cog on deep ocean takes no damage", !!c1 && onOcean(c1) && c1.Health.damage === c0, { before: c0, now: state(c1) });
const workerBefore = worker();
const cur2 = await research(CURRENCY, 2);
const s3 = has(active());
expect("known limit: Currency mastered after the update: its original modifier (attached before the update) and the depth-2 copy are both active, +1 specialist cap until the next world",
  cur2.depth === 2 && s3.original && s3.curHigh && worker() === workerBefore + 1, { workerBefore, workerNow: worker(), cur2, active: s3 });
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
// Slot 0 ends its own turns to the age's end (no AI research: the specialist cap check of phase 2 needs the same nodes).
for (let i = 0; i < 60 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { /* the request is sent again */ } }
const end = { worker: worker(), currency: depth(CURRENCY), shipbuilding: depth(SHIPBUILDING), turn: Game.turn };
expect("the age is at its end, with both nodes at depth 2", left() <= 0 && end.currency === 2 && end.shipbuilding === 2, { left: left(), end });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((c) => c.ok), checks, end, transition: { auto: true } };

//// PHASE 2: the Exploration world
const me = GameContext.localPlayerID;
const CURRENCY = "NODE_TECH_AQ_CURRENCY", SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const CAP = "MOD_AQ_SPECIALIST_CAP_INCREASE", WATER = "MOD_TECH_EX_NO_OCEAN_DAMAGE";
const OCEAN = GameInfo.Terrains.lookup("TERRAIN_OCEAN").$index;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "update_051", phase: 2, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const rows = ((globalThis.caMasterySplit ?? {})[world] ?? []);
const row = (node, modifier) => rows.find((e) => e.node === node && e.modifier === modifier) ?? {};
const cur = row(CURRENCY, CAP), ship = row(SHIPBUILDING, WATER);
const set = new Set(Players.get(me).Modifiers.getModifiers().map((m) => GameEffects.getModifierDefinitionFromTypeId(m.modifierType)?.ID));
const act = { original: set.has(CAP), curLow: set.has(cur.low), curHigh: set.has(cur.high), water: set.has(WATER), shipLow: set.has(ship.low), shipHigh: set.has(ship.high) };
const prev = (globalThis.caPrev ?? []).find((v) => v?.end) ?? {};
expect("the world is Exploration, slot 0 is human, both nodes at depth 2", world === "AGE_EXPLORATION" && Players.get(me).isHuman && depth(CURRENCY) === 2 && depth(SHIPBUILDING) === 2,
  { world, turn: Game.turn, currency: depth(CURRENCY), shipbuilding: depth(SHIPBUILDING) });
expect("test: after the transition the depth-2 copies are active, and the original modifiers and the depth-1 copy are not",
  act.curHigh && act.shipHigh && !act.original && !act.curLow && !act.water, act);
// The world's own change of the capital's specialist cap is +1 in this game (mastery_unlocks.js, control run: workerDelta);
// the double of phase 1 ends: no change in sum.
const workerNow = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital)?.Workers?.getCityWorkerCap() ?? -1;
expect("test: the capital's specialist cap is the old world's less the double, plus the world's own +1 (no change in sum)", workerNow === prev.end?.worker,
  { workerBefore: prev.end?.worker, workerNow });
Visibility.revealAllPlots(me);
await settle();
const mine = () => Players.get(me).Units.getUnitIds().map((id) => Units.get(id)).filter(Boolean);
const home = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital)?.location ?? mine()[0].location;
const dist = (a, b) => Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y));
const onOcean = (u) => GameplayMap.getTerrainType(u.location.x, u.location.y) === OCEAN;
const state = (u) => u ? { id: u.id, type: GameInfo.Units.lookup(u.type)?.UnitType, x: u.location.x, y: u.location.y, ocean: onOcean(u), damage: u.Health?.damage } : null;
const freeOcean = [];
for (let x = 0; x < GameplayMap.getGridWidth(); x++) for (let y = 0; y < GameplayMap.getGridHeight(); y++)
  if (GameplayMap.getTerrainType(x, y) === OCEAN && (MapUnits.getUnits(x, y)?.length ?? 0) === 0) freeOcean.push({ x, y, d: dist({ x, y }, home) });
freeOcean.sort((a, b) => a.d - b.d);
const ships = [];
for (let i = 0; i < 8 && ships.length < 2; i++) {
  const p = freeOcean[i * 3];
  const u = p ? await caLive.createUnitAndWait(i % 2 ? "UNIT_COG" : "UNIT_CARRACK", p.x, p.y) : null;
  if (u && onOcean(Units.get(u.id))) ships.push(u.id);
}
const before = new Map(ships.map((id) => [id, Units.get(id)?.Health?.damage]));
expect("setup: two new ships on deep ocean", ships.length >= 2, { ships: ships.map((id) => state(Units.get(id))) });
await caLive.endTurn();
await caLive.endTurn();
const after = ships.map((id) => ({ before: before.get(id), now: state(Units.get(id)) }));
const damaged = after.filter((s) => !s.now || (s.now.ocean && s.now.damage > (s.before ?? 0)));
expect("test: no ship of slot 0 takes deep-ocean damage in the Exploration world", after.length >= 2 && damaged.length === 0, { after });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
