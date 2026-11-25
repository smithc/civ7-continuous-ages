// Scenario test of rule 6c: land units on deep ocean in the Antiquity world (a player report of 2026-11-21: "Scouts do
// not cross the ocean until the main game reaches Exploration, even when I have reached Modern").
// Build: build_mod.py --install --checks; suite: ContinuousAgesLive.json. Antiquity world (the test) and
// StartAge=AGE_EXPLORATION (the reference: the Exploration world has no ocean block for land units).
// The Antiquity world makes deep ocean invalid terrain for every unit (AGE_ANTIQUITY_MOD_OCEAN_TERRAIN_INVALID). The mod
// opens it at the Exploration Breakthrough for naval units; rule 6c opens it for land units too, so that, as in the
// Exploration world, the embarkation type decides: shallow water at the Exploration Breakthrough, deep water with the
// Modern Breakthrough or with Shipbuilding's mastery.
//   control (Exploration Breakthrough only, shallow embarkation): a Scout on the coast does not enter deep ocean
//   test (CAPath=modern: the Modern Breakthrough; CAPath=shipbuilding: Shipbuilding mastered): a Scout enters deep ocean;
//   so do the control's Scout (made before the grant) and a Settler
const me = GameContext.localPlayerID;
const EXG = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", MOG = "NODE_TECH_CA_MODERN_BREAKTHROUGH", SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const path = (() => { try { return Automation.getParameter("CurrentTest", "CAPath") ?? "modern"; } catch (e) { return "modern"; } })();
const OCEAN = GameInfo.Terrains.lookup("TERRAIN_OCEAN").$index, COAST = GameInfo.Terrains.lookup("TERRAIN_COAST").$index;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "ocean_land", world, path, name, ok, detail }); };
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
async function grantTo(node, d) {
  for (let k = 0; k < 4 && depth(node) < d; k++) {
    const was = depth(node);
    caLive.grantNode(node);
    for (let i = 0; i < 10 && depth(node) <= was; i++) await settle(500);
  }
  return depth(node) >= d;
}
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
Visibility.revealAllPlots(me);
await settle();
const dirs = Object.entries(DirectionTypes).filter(([k]) => k !== "NO_DIRECTION").map(([, v]) => v);
const adj = (p) => dirs.map((d) => GameplayMap.getAdjacentPlotLocation(p, d)).filter((q) => q && q.x >= 0 && q.y >= 0);
const terr = (p) => GameplayMap.getTerrainType(p.x, p.y);
const free = (p) => (MapUnits.getUnits(p.x, p.y)?.length ?? 0) === 0;
const home = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital).location;
// Free coast plots C next to a free deep-ocean plot O, near home (two routes: control and test).
const routes = [];
for (let r = 1; r < 30 && routes.length < 3; r++) {
  for (const i of GameplayMap.getPlotIndicesInRadius(home.x, home.y, r)) {
    const c = GameplayMap.getLocationFromIndex(i);
    if (terr(c) !== COAST || !free(c) || routes.some((x) => GameplayMap.getPlotDistance(x.c.x, x.c.y, c.x, c.y) < 3)) continue;
    const o = adj(c).find((q) => terr(q) === OCEAN && free(q));
    if (o) { routes.push({ c, o }); if (routes.length >= 3) break; }
  }
}
if (routes.length < 3) return { ok: false, error: "fewer than three coast plots next to deep ocean" };
const at = (u) => u ? { x: u.location.x, y: u.location.y, terrain: GameInfo.Terrains.lookup(terr(u.location))?.TerrainType } : null;
async function wade(route, label, type = "UNIT_SCOUT", existing = null) {
  const u0 = existing ?? await caLive.createUnitAndWait(type, route.c.x, route.c.y);
  const u = u0 ? Units.get(u0.id) : null;
  if (!u) return { label, placed: false };
  const start = at(u);
  const onCoast = start.x === route.c.x && start.y === route.c.y;
  const args = { X: route.o.x, Y: route.o.y };
  const can = Game.UnitOperations.canStart(u.id, UnitOperationTypes.MOVE_TO, args, false);
  if (can?.Success) Game.UnitOperations.sendRequest(u.id, UnitOperationTypes.MOVE_TO, args);
  // The move is handled a moment later: wait up to 10 s for the Scout to reach O.
  for (let i = 0; i < 20; i++) {
    const v = Units.get(u.id);
    if (v && v.location.x === route.o.x && v.location.y === route.o.y) break;
    await settle(500);
  }
  const end = at(Units.get(u.id));
  return { label, placed: true, id: u.id, start, onCoast, canStart: !!can?.Success, end, onOcean: !!end && end.x === route.o.x && end.y === route.o.y,
           embarked: Units.get(u.id)?.isEmbarked ?? null };
}
expect("setup: the Exploration Breakthrough is granted", await grantTo(EXG, 1), { gate: depth(EXG) });
await settle();
const control = await wade(routes[0], "Exploration Breakthrough only");
expect("control: with shallow embarkation, a Scout on the coast does not enter deep ocean", control.placed && control.onCoast && !control.onOcean, control);
let granted;
if (path === "shipbuilding") granted = { shipbuilding: await grantTo(SHIPBUILDING, 2), depth: depth(SHIPBUILDING) };
else granted = { modern: await grantTo(MOG, 1), depth: depth(MOG) };
expect(`setup: ${path === "shipbuilding" ? "Shipbuilding mastered" : "the Modern Breakthrough granted"}`, granted.shipbuilding ?? granted.modern, granted);
await settle();
const test = await wade(routes[1], path === "shipbuilding" ? "Shipbuilding mastered" : "Modern Breakthrough");
expect(`test: with deep-water embarkation, a Scout on the coast enters deep ocean (${world})`, test.placed && test.onCoast && test.onOcean, test);
// The control's Scout was made before the grant; it is still on its coast plot. A unit that existed before the grant
// crosses too, and so does a Settler (every land unit: a leading civ can reach the Distant Lands).
await caLive.endTurn();  // a new turn: the control Scout's moves are back
const older = control.id && Units.get(control.id) ? await wade(routes[0], "the control's Scout, made before the grant", "UNIT_SCOUT", { id: control.id }) : { placed: false };
expect("test: a Scout made before the grant enters deep ocean too", older.placed && older.onCoast && older.onOcean, older);
const settler = await wade(routes[2], "a Settler", "UNIT_SETTLER");
expect("test: a Settler on the coast enters deep ocean", settler.placed && settler.onCoast && settler.onOcean, settler);
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
