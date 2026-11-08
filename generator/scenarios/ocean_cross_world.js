// Scenario test of deep-ocean damage across the world transition, with Shipbuilding RESEARCHED (not granted) in the
// Antiquity world (build: build_mod.py --install --checks --age-points 8 --fast-test 0.01; suite: ContinuousAgesLive.json).
// A player report of 2026-11-08: "Exploration, Antiquity: no deep-sea penalty; Exploration, Exploration: the penalty is
// back". An earlier test (2026-11-07) granted Shipbuilding by debug, and a node granted by debug in an earlier world did
// not unlock its units after a transition (religion tests): so this test researches it the normal way.
// Phase 1 (Antiquity world): the gate (granted); a Cog on deep ocean takes damage (rule 6b, control); Shipbuilding
// researched (its prerequisites granted, then SET_TECH_TREE_NODE and turns); a new Cog then takes no damage; age end.
// Phase 2 (Exploration world): the kept Cog and new ships on deep ocean for 2 turns: no damage (the test).
// Negative control: the same build with --probe ocean_unprotected (Shipbuilding's protection removed): both "no damage"
// checks must fail, which shows that deep-ocean damage is active in both worlds of this setup.
const me = GameContext.localPlayerID;
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const OCEAN = GameInfo.Terrains.lookup("TERRAIN_OCEAN").$index;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "ocean_cross_world", phase: 1, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
async function grant(node) { caLive.grantNode(node); for (let i = 0; i < 10 && depth(node) < 1; i++) await settle(500); return depth(node) >= 1; }
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
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
  const p = freeOcean()[skip];
  const u = p ? await caLive.createUnitAndWait(type, p.x, p.y) : null;
  return u && onOcean(Units.get(u.id)) ? Units.get(u.id) : null;
}
expect("setup: the gate is granted", await grant(GATE), { gate: depth(GATE) });
// Control (rule 6b): past the gate, without Shipbuilding, deep ocean damages a ship.
const cogA = await shipOnOcean("UNIT_COG", 0);
const a0 = cogA?.Health.damage;
await caLive.endTurn();
const a1 = cogA ? Units.get(cogA.id) : null;
expect("control: without Shipbuilding, a Cog on deep ocean takes damage in the Antiquity world (rule 6b)",
  !!a1 && a1.Health.damage > a0, { before: a0, now: state(a1), shipbuilding: depth(SHIPBUILDING) });
// Shipbuilding by normal research: its prerequisites granted, then the research order and turns.
const pre = Array.from(GameInfo.ProgressionTreePrereqs).filter((r) => r.Node === SHIPBUILDING).map((r) => r.PrereqNode);
const preOk = {};
for (const n of pre) preOk[n] = depth(n) >= 1 || await grant(n);
const args = { ProgressionTreeNodeType: GameInfo.ProgressionTreeNodes.lookup(SHIPBUILDING).$hash };
const canResearch = !!Game.PlayerOperations.canStart(me, PlayerOperationTypes.SET_TECH_TREE_NODE, args, false)?.Success;
if (canResearch) Game.PlayerOperations.sendRequest(me, PlayerOperationTypes.SET_TECH_TREE_NODE, args);
await settle();
const researching = GameInfo.ProgressionTreeNodes.lookup(Players.get(me).Techs.getResearching?.()?.type ?? Players.get(me).Techs.getResearching?.())?.ProgressionTreeNodeType ?? null;
let turns = 0;
for (; turns < 6 && depth(SHIPBUILDING) < 1; turns++) await caLive.endTurn();
expect("setup: Shipbuilding researched the normal way (prerequisites granted, then research)",
  canResearch && depth(SHIPBUILDING) >= 1, { pre: preOk, canResearch, researching, turns, depth: depth(SHIPBUILDING) });
const cogB = await shipOnOcean("UNIT_COG", 1);
const b0 = cogB?.Health.damage;
await caLive.endTurn();
const b1 = cogB ? Units.get(cogB.id) : null;
expect("with researched Shipbuilding, a new Cog on deep ocean takes no damage in the Antiquity world",
  !!b1 && onOcean(b1) && b1.Health.damage === b0, { before: b0, now: state(b1) });
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
for (let i = 0; i < 30 && left() > 3; i++) await caLive.advance(1);
for (let i = 0; i < 12 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { if (left() >= 2) await caLive.advance(1); } }
expect("the age is at its end", left() <= 0, { turn: Game.turn, left: left() });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((c) => c.ok), checks, transition: { auto: true } };

//// PHASE 2: the Exploration world
const me = GameContext.localPlayerID;
const SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const OCEAN = GameInfo.Terrains.lookup("TERRAIN_OCEAN").$index;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "ocean_cross_world", phase: 2, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
expect("the world is Exploration, slot 0 is human and has Shipbuilding", world === "AGE_EXPLORATION" && Players.get(me).isHuman && depth(SHIPBUILDING) >= 1,
  { world, turn: Game.turn, shipbuilding: depth(SHIPBUILDING), civ: GameInfo.Civilizations.lookup(Players.get(me).civilizationType)?.CivilizationType });
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
const ships = mine().filter((u) => GameInfo.Units.lookup(u.type)?.Domain === "DOMAIN_SEA" && onOcean(u)).map((u) => u.id);
for (const [i, type] of ["UNIT_COG", "UNIT_CARRACK"].entries()) {
  const p = freeOcean[i * 3];
  const u = p ? await caLive.createUnitAndWait(type, p.x, p.y) : null;
  if (u && onOcean(Units.get(u.id))) ships.push(u.id);
}
const before = new Map(ships.map((id) => [id, Units.get(id)?.Health?.damage]));
expect("setup: ships on deep ocean (kept and new)", ships.length >= 2, { ships: ships.map((id) => state(Units.get(id))) });
await caLive.endTurn();
await caLive.endTurn();
const after = ships.map((id) => ({ before: before.get(id), now: state(Units.get(id)) }));
const damaged = after.filter((s) => s.now?.ocean && s.now.damage > (s.before ?? 0));
expect("test: with Shipbuilding researched in the Antiquity world, no ship of slot 0 takes deep-ocean damage in the Exploration world",
  after.length >= 2 && damaged.length === 0, { after });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
