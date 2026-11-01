// Scenario test of rule 6 (build: build_mod.py --install --checks; suite: ContinuousAgesLive.json, Antiquity world).
// The Exploration rule that deep ocean ends a unit's turn until Shipbuilding applies to a civ past its gate in the
// Antiquity world, so Shipbuilding keeps its meaning for a leading civ.
//   behind the gate: a ship on the coast may not move onto deep ocean
//   past the gate, without Shipbuilding: a ship ordered across two deep-ocean plots stops on the first one
//   with Shipbuilding: a ship ordered the same way gets past the first deep-ocean plot
const me = GameContext.localPlayerID;
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const OCEAN = GameInfo.Terrains.lookup("TERRAIN_OCEAN").$index, COAST = GameInfo.Terrains.lookup("TERRAIN_COAST").$index;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "deep_ocean_turn", name, ok, detail }); };
async function grant(node) {
  caLive.grantNode(node);
  for (let i = 0; i < 10 && !caLive.hasNode(node); i++) await settle(500);
  return caLive.hasNode(node);
}
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
Visibility.revealAllPlots(me);  // CREATE_ELEMENT places units only on revealed plots
await settle();
const dirs = Object.entries(DirectionTypes).filter(([k]) => k !== "NO_DIRECTION").map(([, v]) => v);
const adj = (p) => dirs.map((d) => GameplayMap.getAdjacentPlotLocation(p, d)).filter((q) => q && q.x >= 0 && q.y >= 0);
const terr = (p) => GameplayMap.getTerrainType(p.x, p.y);
const free = (p) => (MapUnits.getUnits(p.x, p.y)?.length ?? 0) === 0;
const home = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital).location;
// A free coast plot C next to a deep-ocean plot O1, which is next to another deep-ocean plot O2 (two steps from C), near home.
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
if (!route) return { ok: false, error: "no coast plot with two deep-ocean plots beyond it" };
const SHIP = "UNIT_COG";
const shipAt = (p) => Players.get(me).Units.getUnitIds().map((id) => Units.get(id))
  .find((u) => GameInfo.Units.lookup(u.type)?.UnitType === SHIP && u.location.x === p.x && u.location.y === p.y);
async function sail(label) {
  caLive.createUnit(SHIP, route.c.x, route.c.y);
  await settle();
  const ship = shipAt(route.c);
  if (!ship) return { placed: false };
  const args = { X: route.o2.x, Y: route.o2.y };
  const can = Game.UnitOperations.canStart(ship.id, UnitOperationTypes.MOVE_TO, args, false);
  if (can?.Success) Game.UnitOperations.sendRequest(ship.id, UnitOperationTypes.MOVE_TO, args);
  await settle(4000);
  const u = Units.get(ship.id);
  const at = u ? { x: u.location.x, y: u.location.y } : null;
  return { placed: true, label, canStart: !!can?.Success, at, onO1: !!at && at.x === route.o1.x && at.y === route.o1.y,
           onO2: !!at && at.x === route.o2.x && at.y === route.o2.y, movesLeft: u?.Movement?.movementMovesRemaining };
}
// Behind the gate the engine's canStart(MOVE_TO) says yes (the open check in docs/known-limits.md), but the ship does
// not move onto deep ocean: where it ends is the proof (live test 20261031-133303: it stayed on the coast).
const behind = await sail("behind the gate");
expect("behind the gate: the ship does not move onto deep ocean", behind.placed && !behind.onO1 && !behind.onO2, behind);
expect("gate granted", await grant(GATE));
await settle();
const past = await sail("past the gate");
expect("past the gate: the ship stops on the first deep-ocean plot", past.placed && past.canStart && past.onO1, past);
expect("Shipbuilding granted", await grant(SHIPBUILDING));
await settle();
const ship2 = await sail("with Shipbuilding");
expect("with Shipbuilding: the ship gets past the first deep-ocean plot", ship2.placed && ship2.canStart && !ship2.onO1 && ship2.at
       && (ship2.at.x !== route.c.x || ship2.at.y !== route.c.y), ship2);
return { ok: checks.every((c) => c.ok), route, failed: checks.filter((c) => !c.ok), checks };
