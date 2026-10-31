// Scenario test of rule 6b (deep-ocean damage in the Antiquity world; build: build_mod.py --install --checks;
// suite: ContinuousAgesLive.json --set Player0Civ=CIVILIZATION_TONGA, the one Antiquity civ with a unit that may
// enter deep ocean, the Tehina scout).
//   behind the gate: the Tehina on deep ocean for 2 turns -> no damage (the base game's Antiquity has none)
//   past the gate (granted): the Tehina and a new Cog on deep ocean -> damage (the Exploration rule)
//   with Shipbuilding (granted): no more damage
const me = GameContext.localPlayerID;
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const OCEAN = GameInfo.Terrains.lookup("TERRAIN_OCEAN").$index;
const checks = [];
const expect = (name, ok, detail = {}) => {
  checks.push({ name, ok, detail });
  caLive.log({ scenario: "ocean_damage", name, ok, detail });
};
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
async function grant(node) {
  caLive.grantNode(node);
  for (let i = 0; i < 10 && !caLive.hasNode(node); i++) await settle(500);
  return caLive.hasNode(node);
}
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
Visibility.revealAllPlots(me);  // CREATE_ELEMENT places units only on revealed plots
await settle();
const home = (Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital)).location;
const dist = (a, b) => Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y));
const ocean = [];
for (let x = 0; x < GameplayMap.getGridWidth(); x++) for (let y = 0; y < GameplayMap.getGridHeight(); y++) {
  if (GameplayMap.getTerrainType(x, y) === OCEAN && (MapUnits.getUnits(x, y)?.length ?? 0) === 0) ocean.push({ x, y, d: dist({ x, y }, home) });
}
ocean.sort((a, b) => a.d - b.d);
const mine = (type) => Players.get(me).Units.getUnitIds().map((id) => Units.get(id)).filter((u) => GameInfo.Units.lookup(u.type)?.UnitType === type);
const onOcean = (u) => GameplayMap.getTerrainType(u.location.x, u.location.y) === OCEAN;
const state = (u) => u ? { x: u.location.x, y: u.location.y, ocean: onOcean(u), damage: u.Health?.damage } : null;
// Behind the gate: the Tehina on deep ocean.
const hasTehina = !!GameInfo.Units.lookup("UNIT_TEHINA");
let tehina = null;
if (hasTehina) {
  caLive.createUnit("UNIT_TEHINA", ocean[0].x, ocean[0].y);
  await settle();
  tehina = mine("UNIT_TEHINA").find(onOcean);
  expect("behind the gate: a Tehina on deep ocean", !!tehina, { asked: ocean[0], tehinas: mine("UNIT_TEHINA").map(state) });
  if (tehina) {
    await caLive.endTurn();
    await caLive.endTurn();
    tehina = Units.get(tehina.id);
    expect("behind the gate: no damage after 2 turns on deep ocean", tehina && onOcean(tehina) && tehina.Health.damage === 0, state(tehina));
  }
}
// Past the gate: damage until Shipbuilding.
expect("gate granted", await grant(GATE));
caLive.createUnit("UNIT_COG", ocean[1].x, ocean[1].y);
await settle();
let cog = mine("UNIT_COG").find(onOcean);
expect("past the gate: a Cog on deep ocean", !!cog, { asked: ocean[1], cogs: mine("UNIT_COG").map(state) });
const before = { cog: cog?.Health.damage, tehina: tehina ? Units.get(tehina.id)?.Health.damage : null };
await caLive.endTurn();
cog = cog ? Units.get(cog.id) : null;
expect("past the gate: the Cog takes damage on deep ocean", !!cog && cog.Health.damage > before.cog, { before: before.cog, now: state(cog) });
if (tehina) {
  const t = Units.get(tehina.id);
  expect("past the gate: the Tehina takes damage too", !!t && t.Health.damage > before.tehina, { before: before.tehina, now: state(t) });
}
expect("Shipbuilding granted", await grant(SHIPBUILDING));
const withShipbuilding = cog?.Health.damage;
await caLive.endTurn();
cog = cog ? Units.get(cog.id) : null;
expect("with Shipbuilding: no more damage", !!cog && cog.Health.damage === withShipbuilding, { before: withShipbuilding, now: state(cog) });
return { ok: checks.every((c) => c.ok), tehina: hasTehina, failed: checks.filter((c) => !c.ok), checks };
