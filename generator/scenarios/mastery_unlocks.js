// Scenario test of rule 2n with normal research: a mastered node's depth-1 modifier unlocks across a world transition
// (a player report of 2026-11-10, build/player-reports/2026-11-11.md: Shipbuilding mastered in the Antiquity world,
// deep-ocean damage in the Exploration world). Build: build_mod.py --install --checks --age-points 12 --fast-test 0.01;
// suite: ContinuousAgesLive.json --set GameSpeed=GAMESPEED_MARATHON (36 turns: the script needs about 25) and:
//   --set CAMaster=0                 the control run: the nodes stay at depth 1. It measures the change of the capital's
//                                    specialist cap at the transition (the result field "workerDelta").
//   --set CAMaster=1 --set CADelta=N the test run: the nodes mastered (depth 2) by normal research; N is the control's
//                                    workerDelta. Without CADelta the specialist cap check fails (it cannot run).
// Three effects, one of each kind:
//   additive: Currency's specialist cap (+1 in each city). Lost at a transition without the rule (the cap is not carried).
//   switch:   Shipbuilding's deep-ocean protection, and "deep ocean does not end the move". Lost at a transition without
//             the rule.
//   carried:  Feudalism's settlement cap (+1). The engine carries the cap itself, so the rule leaves it; the checks
//             record the known limit: at depth 1 the row is attached again at the load (+1), mastered it is not (+0).
// Phase 1 (Antiquity world): the gate (granted); a Cog on deep ocean takes damage while Currency is researched (control);
// each node gives its effect at depth 1 and no more at the mastery; a new Cog takes no damage with Shipbuilding; slot 0
// ends its own turns to the age's end (no AI research), and the values there.
// Phase 2 (Exploration world): the specialist cap changes as in the control run (the test); the settlement cap (known
// limit); two new ships on deep ocean take no damage in 2 turns (the test); a new Cog crosses two deep-ocean plots in
// one move (the test).
const me = GameContext.localPlayerID;
const MASTER = Number(Automation.getParameter("CurrentTest", "CAMaster", 1)) !== 0;
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", CURRENCY = "NODE_TECH_AQ_CURRENCY", FEUDALISM = "NODE_TECH_EX_FEUDALISM", SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const OCEAN = GameInfo.Terrains.lookup("TERRAIN_OCEAN").$index;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "mastery_unlocks", phase: 1, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const capital = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const cap = () => Players.get(me).Stats?.settlementCap ?? -1;
const worker = () => capital()?.Workers?.getCityWorkerCap() ?? -1;
async function grant(node) { caLive.grantNode(node); for (let i = 0; i < 10 && depth(node) < 1; i++) await settle(500); return depth(node) >= 1; }
// Normal research of a node up to a depth: its missing prerequisites granted, then the research order and turns.
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
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
Visibility.revealAllPlots(me);
await settle();
const home = capital().location;
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
  const p = freeOcean()[skip];
  const u = p ? await caLive.createUnitAndWait(type, p.x, p.y) : null;
  return u && onOcean(Units.get(u.id)) ? Units.get(u.id) : null;
}
const start = { currency: depth(CURRENCY), feudalism: depth(FEUDALISM), shipbuilding: depth(SHIPBUILDING) };
expect("setup: the gate is granted, and slot 0 has none of the three nodes", (await grant(GATE)) && start.currency === 0 && start.feudalism === 0 && start.shipbuilding === 0,
  { gate: depth(GATE), master: MASTER, start });
// Control (rule 6b): past the gate, without Shipbuilding, deep ocean damages a ship (while Currency is researched).
const cogA = await shipOnOcean("UNIT_COG", 0);
const a0 = cogA?.Health.damage;
const w0 = worker();
const cur1 = await research(CURRENCY, 1);
const a1 = cogA ? Units.get(cogA.id) : null;
expect("control: without Shipbuilding, a Cog on deep ocean takes damage in the Antiquity world (rule 6b)",
  !!cogA && cur1.turns >= 1 && (!a1 || a1.Health.damage > a0), { before: a0, now: state(a1), gone: !!cogA && !a1, turns: cur1.turns, shipbuilding: depth(SHIPBUILDING) });
const w1 = worker();
expect("Currency researched (depth 1) gives +1 specialist cap in the capital", cur1.depth === 1 && w0 >= 0 && w1 === w0 + 1, { w0, w1, cur1 });
const c0 = cap();
const feud1 = await research(FEUDALISM, 1);
const c1 = cap();
expect("Feudalism researched (depth 1) gives +1 settlement cap", feud1.depth === 1 && c0 >= 0 && c1 === c0 + 1, { c0, c1, feud1 });
if (MASTER) {
  const cur2 = await research(CURRENCY, 2);
  expect("Currency mastered (depth 2) by research: the specialist cap does not change in the same world (no double)", cur2.depth === 2 && worker() === w1, { w1, now: worker(), cur2 });
  const feud2 = await research(FEUDALISM, 2);
  expect("Feudalism mastered (depth 2) by research: the settlement cap does not change in the same world", feud2.depth === 2 && cap() === c1, { c1, now: cap(), feud2 });
}
const ship1 = await research(SHIPBUILDING, 1);
const ship2 = MASTER ? await research(SHIPBUILDING, 2) : null;
expect(`setup: Shipbuilding researched to depth ${MASTER ? 2 : 1} the normal way`, depth(SHIPBUILDING) === (MASTER ? 2 : 1), { ship1, ship2 });
const cogB = await shipOnOcean("UNIT_COG", 1);
const b0 = cogB?.Health.damage;
await caLive.endTurn();
const b1 = cogB ? Units.get(cogB.id) : null;
expect("with Shipbuilding, a new Cog on deep ocean takes no damage in the Antiquity world", !!b1 && onOcean(b1) && b1.Health.damage === b0, { before: b0, now: state(b1) });
// Slot 0 ends its own turns to the age's end: the AI would research more nodes, and the two runs must differ only in the mastery.
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
for (let i = 0; i < 60 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { /* the request is sent again */ } }
const want = MASTER ? 2 : 1;
const end = { worker: worker(), cap: cap(), currency: depth(CURRENCY), feudalism: depth(FEUDALISM), shipbuilding: depth(SHIPBUILDING), turn: Game.turn };
expect("the age is at its end, with the depths of this run", left() <= 0 && end.currency === want && end.feudalism === want && end.shipbuilding === want, { left: left(), end });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((c) => c.ok), checks, end, master: MASTER, transition: { auto: true } };

//// PHASE 2: the Exploration world
const me = GameContext.localPlayerID;
const CURRENCY = "NODE_TECH_AQ_CURRENCY", FEUDALISM = "NODE_TECH_EX_FEUDALISM", SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const OCEAN = GameInfo.Terrains.lookup("TERRAIN_OCEAN").$index;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "mastery_unlocks", phase: 2, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const capital = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const prev = (globalThis.caPrev ?? [])[0] ?? {};
const want = prev.master ? 2 : 1;
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
expect("the world is Exploration, slot 0 is human and kept the depths", world === "AGE_EXPLORATION" && Players.get(me).isHuman && depth(CURRENCY) === want && depth(FEUDALISM) === want && depth(SHIPBUILDING) === want,
  { world, turn: Game.turn, currency: depth(CURRENCY), feudalism: depth(FEUDALISM), shipbuilding: depth(SHIPBUILDING), want, civ: GameInfo.Civilizations.lookup(Players.get(me).civilizationType)?.CivilizationType });
const workerNow = capital()?.Workers?.getCityWorkerCap() ?? -1;
const workerDelta = workerNow - (prev.end?.worker ?? NaN);
const wantDelta = Number(Automation.getParameter("CurrentTest", "CADelta", NaN));
const wDetail = { workerBefore: prev.end?.worker, workerNow, workerDelta, wantDelta };
if (prev.master) expect("test: the capital's specialist cap changes at the transition as in the control run (the mastered Currency keeps its +1)", workerDelta === wantDelta, wDetail);
// The control pins the world's own change: +1 (2026-11-11, game 1.5.1). If a game patch changes it, this check fails:
// measure it again, and change CADelta of the test entry and the note in update_051.js.
else expect("control: the capital's specialist cap changes by +1 at the transition (the world's own change; the test entry's CADelta)", workerDelta === 1, wDetail);
const capNow = Players.get(me).Stats?.settlementCap ?? -1;
const capDelta = capNow - (prev.end?.cap ?? NaN);
expect(`known limit (the engine carries the settlement cap): Feudalism ${prev.master ? "mastered: its row is not attached again (+0)" : "at depth 1: its row is attached again at the load (+1)"}`,
  capDelta === (prev.master ? 0 : 1), { capBefore: prev.end?.cap, capNow, capDelta });
Visibility.revealAllPlots(me);
await settle();
const mine = () => Players.get(me).Units.getUnitIds().map((id) => Units.get(id)).filter(Boolean);
const home = capital()?.location ?? mine()[0].location;
const dist = (a, b) => Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y));
const onOcean = (u) => GameplayMap.getTerrainType(u.location.x, u.location.y) === OCEAN;
const state = (u) => u ? { id: u.id, type: GameInfo.Units.lookup(u.type)?.UnitType, x: u.location.x, y: u.location.y, ocean: onOcean(u), damage: u.Health?.damage } : null;
const freeOcean = [];
for (let x = 0; x < GameplayMap.getGridWidth(); x++) for (let y = 0; y < GameplayMap.getGridHeight(); y++)
  if (GameplayMap.getTerrainType(x, y) === OCEAN && (MapUnits.getUnits(x, y)?.length ?? 0) === 0) freeOcean.push({ x, y, d: dist({ x, y }, home) });
freeOcean.sort((a, b) => a.d - b.d);
const ships = mine().filter((u) => GameInfo.Units.lookup(u.type)?.Domain === "DOMAIN_SEA" && onOcean(u)).map((u) => u.id);
// Two new ships on deep ocean (the game moves a new unit to the nearest valid plot, which can be a coast plot: try more
// plots). A ship kept from the Antiquity world counts too.
const kept = ships.length;
let made = 0;
for (let i = 0; i < 8 && made < 2; i++) {
  const p = freeOcean[i * 3];
  const u = p ? await caLive.createUnitAndWait(i % 2 ? "UNIT_COG" : "UNIT_CARRACK", p.x, p.y) : null;
  if (u && onOcean(Units.get(u.id))) { ships.push(u.id); made++; }
}
const before = new Map(ships.map((id) => [id, Units.get(id)?.Health?.damage]));
expect("setup: two new ships on deep ocean (and the kept ones)", made >= 2, { kept, made, ships: ships.map((id) => state(Units.get(id))) });
await caLive.endTurn();
await caLive.endTurn();
const after = ships.map((id) => ({ before: before.get(id), now: state(Units.get(id)) }));
const damaged = after.filter((s) => !s.now || (s.now.ocean && s.now.damage > (s.before ?? 0)));
expect("test: no ship of slot 0 takes deep-ocean damage in the Exploration world", after.length >= 2 && damaged.length === 0, { after });
// Shipbuilding's other depth-1 unlock, "deep ocean does not end the move": a new Cog on a coast plot C, ordered to a
// deep-ocean plot O2 two steps away across the deep-ocean plot O1, gets past O1 (as in scenarios/deep_ocean_turn.js;
// without the modifier the ship stops on O1).
const COAST = GameInfo.Terrains.lookup("TERRAIN_COAST").$index;
const dirs = Object.entries(DirectionTypes).filter(([k]) => k !== "NO_DIRECTION").map(([, v]) => v);
const adj = (p) => dirs.map((d) => GameplayMap.getAdjacentPlotLocation(p, d)).filter((q) => q && q.x >= 0 && q.y >= 0);
const terr = (p) => GameplayMap.getTerrainType(p.x, p.y);
const free = (p) => (MapUnits.getUnits(p.x, p.y)?.length ?? 0) === 0;
let route = null;
for (let r = 1; r < 30 && !route; r++) {
  for (const i of GameplayMap.getPlotIndicesInRadius(home.x, home.y, r)) {
    const c = GameplayMap.getLocationFromIndex(i);
    if (terr(c) !== COAST || !free(c)) continue;
    for (const o1 of adj(c).filter((q) => terr(q) === OCEAN && free(q))) {
      const o2 = adj(o1).find((q) => terr(q) === OCEAN && free(q) && GameplayMap.getPlotDistance(q.x, q.y, c.x, c.y) === 2);
      if (o2) { route = { c, o1, o2 }; break; }
    }
    if (route) break;
  }
}
const move = { route, placed: false };
if (route) {
  await caLive.createUnitAndWait("UNIT_COG", route.c.x, route.c.y);
  const ship = mine().find((u) => GameInfo.Units.lookup(u.type)?.UnitType === "UNIT_COG" && u.location.x === route.c.x && u.location.y === route.c.y);
  if (ship) {
    move.placed = true;
    const args = { X: route.o2.x, Y: route.o2.y };
    const can = Game.UnitOperations.canStart(ship.id, UnitOperationTypes.MOVE_TO, args, false);
    move.canStart = !!can?.Success;
    if (can?.Success) Game.UnitOperations.sendRequest(ship.id, UnitOperationTypes.MOVE_TO, args);
    // The game handles the move a moment later: wait (up to 15 s) until the ship is on O2, or has left C and kept its plot for 2 s.
    const pos = () => { const v = Units.get(ship.id); return v ? `${v.location.x},${v.location.y}` : "gone"; };
    const t0 = Date.now();
    let last = pos(), since = Date.now();
    while (can?.Success && Date.now() - t0 < 15000) {
      const p = pos();
      if (p !== last) { last = p; since = Date.now(); }
      if (p === `${route.o2.x},${route.o2.y}` || (p !== `${route.c.x},${route.c.y}` && Date.now() - since >= 2000)) break;
      await settle(500);
    }
    const u = Units.get(ship.id);
    move.at = u ? { x: u.location.x, y: u.location.y } : null;
    move.onC = !!move.at && move.at.x === route.c.x && move.at.y === route.c.y;
    move.onO1 = !!move.at && move.at.x === route.o1.x && move.at.y === route.o1.y;
    move.onO2 = !!move.at && move.at.x === route.o2.x && move.at.y === route.o2.y;
  }
}
expect("test: a Cog ordered across two deep-ocean plots gets past the first one (deep ocean does not end the move)",
  move.placed && move.canStart && !!move.at && !move.onC && !move.onO1, move);
// A save of this state, for a load with another build. Not a check.
Network.saveGame({ Location: SaveLocations.LOCAL_STORAGE, LocationCategories: SaveLocationCategories.NORMAL,
  Type: GameStateStorage.getGameConfigurationSaveType(), ContentType: SaveFileTypes.GAME_STATE, FileName: "CA_MASTERY_EX", Overwrite: true });
await settle(6000);
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks, workerDelta, capDelta };
