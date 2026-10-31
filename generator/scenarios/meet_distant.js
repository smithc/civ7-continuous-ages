// Scenario test of the Exploration baseline's meeting flag (CA_EX_MEET_DISTANT_LAND_CIVS; build: build_mod.py
// --install --checks; suite: ContinuousAgesLive.json, Antiquity world, continents map).
// In the Antiquity world the engine does not let a civ meet the civs of the Distant Lands; the per-player effect
// EFFECT_PLAYER_CAN_MEET_DISTANT_LAND_CIVS lifts it (base game: Tonga only). A civ past its Exploration
// Breakthrough has ocean travel, and its ships can reach and see those civs, so it must be able to meet them
// (a player report of 2026-10-30: "I can see their cities ... but I never receive a Diplomatic meeting").
//   behind the gate: a ship on the coast next to a distant civ's capital for 2 turns -> not met
//   past the gate (granted with GRANT_TREE_NODE): the next turn -> met. Only slot 0 has the flag: one side is enough.
// Live findings used here: CREATE_ELEMENT needs a revealed plot and moves the unit to the nearest valid plot.
const me = GameContext.localPlayerID;
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH";
const SHIP = "UNIT_QUADRIREME";
const checks = [];
const expect = (name, value, want, detail = {}) => {
  checks.push({ name, ok: value === want, value, want, detail });
  caLive.log({ scenario: "meet_distant", name, ok: value === want, value, want, detail });
};
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
const capital = (p) => (p.Cities?.getCityIds() ?? []).map((id) => Cities.get(id)).find((c) => c?.isCapital);
const home = capital(Players.get(me)).location;
const dist = (a, b) => Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y));
const distant = Players.getAlive().filter((p) => p.isMajor && p.id !== me && capital(p) && Players.get(me).isDistantLands(capital(p).location))
  .sort((a, b) => dist(capital(a).location, home) - dist(capital(b).location, home));
if (distant.length === 0) return { ok: false, error: "no major civ in the Distant Lands (map?)" };
const target = distant[0];
const tc = capital(target).location;
Visibility.revealAllPlots(me);  // CREATE_ELEMENT places units only on revealed plots
await settle();
expect("not met at the start (map revealed)", Game.Diplomacy.hasMet(me, target.id), false, { target: target.id, tc });
const coast = [];
for (let dx = -4; dx <= 4; dx++) for (let dy = -4; dy <= 4; dy++) {
  const x = tc.x + dx, y = tc.y + dy;
  if (GameplayMap.isWater(x, y) && GameplayMap.getOwner(x, y) === -1 && (MapUnits.getUnits(x, y)?.length ?? 0) === 0) coast.push({ x, y, d: dist({ x, y }, tc) });
}
coast.sort((a, b) => a.d - b.d);
if (coast.length === 0) return { ok: false, error: "no free water near the target capital", tc };
const ships = () => Players.get(me).Units.getUnitIds().map((id) => Units.get(id))
  .filter((u) => GameInfo.Units.lookup(u.type)?.UnitType === SHIP).map((u) => ({ x: u.location.x, y: u.location.y, d: dist(u.location, tc) }));
caLive.createUnit(SHIP, coast[0].x, coast[0].y);
await settle();
const near = ships().filter((s) => s.d <= 4);
expect("behind the gate: a ship near the distant capital", near.length > 0, true, { asked: coast[0], ships: ships() });
await caLive.endTurn();
await caLive.endTurn();
expect("behind the gate: not met after 2 turns in sight", Game.Diplomacy.hasMet(me, target.id), false, { ships: ships() });
caLive.grantNode(GATE);
for (let i = 0; i < 10 && !caLive.hasNode(GATE); i++) await settle(500);
expect("gate granted", caLive.hasNode(GATE), true);
await caLive.endTurn();
let met = Game.Diplomacy.hasMet(me, target.id);
let how = "same ship, next turn";
if (!met) {  // a new sight event, in case the engine checks contact only when sight changes
  caLive.createUnit(SHIP, coast[Math.min(1, coast.length - 1)].x, coast[Math.min(1, coast.length - 1)].y);
  await settle();
  await caLive.endTurn();
  met = Game.Diplomacy.hasMet(me, target.id);
  how = "second ship, next turn";
}
expect("past the gate: met", met, true, { how, ships: ships() });
return { ok: checks.every((c) => c.ok), target: { id: target.id, capital: tc }, how, failed: checks.filter((c) => !c.ok), checks };
