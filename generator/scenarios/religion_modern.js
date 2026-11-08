// Scenario test of rule 2m at the Modern transition (build: build_mod.py --install --checks --age-points 8; suite:
// ContinuousAgesLive.json --set StartAge=AGE_EXPLORATION). All grants happen in the Exploration world (a node granted by
// debug in an earlier world did not unlock its units after a transition in a test).
// Exploration: slot 0 gets both Breakthroughs and Piety (debug), a Temple (debug), founds a religion (the normal offer),
// and buys a Missionary (controls: it can be trained and bought, and it appears).
// Modern, after the transition: the kept Missionary is gone and no unit replaced it; the civ still has its religion and
// its Temple, and the Missionary cannot be trained or bought (tests); the Scout can be trained (a city control).
// Without the rule (--disable-rule religion) the Missionary stays and can be trained and bought: the tests fail.
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "religion_modern", phase: 1, name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const train = (u) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { UnitType: Database.makeHash(u) }, false)?.Success;
const buy = (u) => Game.CityCommands.canStart(cap().id, CityCommandTypes.PURCHASE, { UnitType: Database.makeHash(u) }, false);
const types = () => Players.get(me).Units.getUnitIds().map((id) => GameInfo.Units.lookup(Units.get(id)?.type)?.UnitType).filter(Boolean);
const count = (t) => types().filter((x) => x === t).length;
const consAt = (x, y) => (MapConstructibles.getConstructibles(x, y) ?? []).map((id) => GameInfo.Constructibles.lookup(Constructibles.getByComponentID(id)?.type)?.ConstructibleType);
const hasBuilding = (b) => GameplayMap.getPlotIndicesInRadius(cap().location.x, cap().location.y, 3).some((i) => { const l = GameplayMap.getLocationFromIndex(i); return consAt(l.x, l.y).includes(b); });
async function place(b) {
  if (hasBuilding(b)) return true;
  const plots = [cap().location, ...GameplayMap.getPlotIndicesInRadius(cap().location.x, cap().location.y, 2).map((i) => GameplayMap.getLocationFromIndex(i))
    .filter((l) => GameplayMap.getOwner(l.x, l.y) === me && MapCities.getDistrict(l.x, l.y) != null)];
  for (const l of plots) { Game.PlayerOperations.sendRequest(me, "CREATE_ELEMENT", { Kind: "CONSTRUCTIBLE", Type: b, Location: { x: l.x, y: l.y }, Owner: me }); await settle(1500); if (hasBuilding(b)) return true; }
  return false;
}
async function grant(n) { caLive.grantNode(n, me, 1); for (let i = 0; i < 10 && !caLive.hasNode(n); i++) await settle(500); return caLive.hasNode(n); }
await caLive.endTurn();  // not the first turn of the world
await settle(3000);
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const setup = { world, turn: Game.turn, gate: await grant("NODE_TECH_CA_EXPLORATION_BREAKTHROUGH"), cgate: await grant("NODE_CIVIC_CA_EXPLORATION_BREAKTHROUGH"),
  piety: await grant("NODE_CIVIC_EX_MAIN_PIETY"), temple: await place("BUILDING_TEMPLE") };
setup.offered = Players.get(me).Religion.canCreateReligion();
const relType = Array.from(GameInfo.Religions).find((r) => !r.RequiresCustomName)?.ReligionType;
if (setup.offered) Game.PlayerOperations.sendRequest(me, PlayerOperationTypes.FOUND_RELIGION, { ReligionType: Database.makeHash(relType) });
for (let i = 0; i < 10 && !Players.get(me).Religion.hasCreatedReligion(); i++) await settle(500);
setup.religion = Players.get(me).Religion.hasCreatedReligion();
Players.get(me).Treasury.changeGoldBalance(3000, -1);
await settle();
expect("setup: Exploration world, both Breakthroughs, Piety, a Temple, a religion (normal offer)",
  world === "AGE_EXPLORATION" && setup.gate && setup.piety && setup.temple && setup.offered && setup.religion, setup);
const b0 = buy("UNIT_MISSIONARY");
const s = { train: train("UNIT_MISSIONARY"), buy: !!b0?.Success, buyWhy: b0?.FailureReasons ?? null };
expect("control: the Missionary can be trained and bought in its own world", s.train && s.buy, s);
const before = { n: count("UNIT_MISSIONARY"), gold: Players.get(me).Treasury.goldBalance };
if (s.buy) Game.CityCommands.sendRequest(cap().id, CityCommandTypes.PURCHASE, { UnitType: Database.makeHash("UNIT_MISSIONARY") });
for (let i = 0; i < 10 && count("UNIT_MISSIONARY") === before.n; i++) await settle(500);
const after = { n: count("UNIT_MISSIONARY"), gold: Players.get(me).Treasury.goldBalance };
expect("control: a bought Missionary appears and the gold is spent", after.n === before.n + 1 && after.gold < before.gold, { before, after });
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
for (let i = 0; i < 30 && left() > 3; i++) await caLive.advance(1);
for (let i = 0; i < 12 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { if (left() >= 2) await caLive.advance(1); } }
const atEnd = { types: types(), missionaries: count("UNIT_MISSIONARY") };
expect("the age is at its end, with the Missionary still there", left() <= 0 && atEnd.missionaries >= 1, { turn: Game.turn, left: left(), atEnd });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((c) => c.ok), checks, transition: { auto: true }, atEnd };

//// PHASE 2: the Modern world
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "religion_modern", phase: 2, name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const train = (u) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { UnitType: Database.makeHash(u) }, false)?.Success;
const buy = (u) => Game.CityCommands.canStart(cap().id, CityCommandTypes.PURCHASE, { UnitType: Database.makeHash(u) }, false);
const types = () => Players.get(me).Units.getUnitIds().map((id) => GameInfo.Units.lookup(Units.get(id)?.type)?.UnitType).filter(Boolean);
const tally = (list) => list.reduce((o, t) => (o[t] = (o[t] ?? 0) + 1, o), {});
const consAt = (x, y) => (MapConstructibles.getConstructibles(x, y) ?? []).map((id) => GameInfo.Constructibles.lookup(Constructibles.getByComponentID(id)?.type)?.ConstructibleType);
const hasBuilding = (b) => GameplayMap.getPlotIndicesInRadius(cap().location.x, cap().location.y, 3).some((i) => { const l = GameplayMap.getLocationFromIndex(i); return consAt(l.x, l.y).includes(b); });
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
expect("the world is Modern and slot 0 is human", world === "AGE_MODERN" && Players.get(me).isHuman, { world, turn: Game.turn });
const prev = globalThis.caPrev.filter((v) => v?.atEnd).pop()?.atEnd ?? { types: [] };
const was = tally(prev.types), now = tally(types());
const gone = Object.fromEntries(Object.entries(was).filter(([t, n]) => (now[t] ?? 0) < n).map(([t, n]) => [t, n - (now[t] ?? 0)]));
const added = Object.fromEntries(Object.entries(now).filter(([t, n]) => (was[t] ?? 0) < n).map(([t, n]) => [t, n - (was[t] ?? 0)]));
const religious = new Set(Array.from(GameInfo.TypeTags).filter((r) => r.Tag === "UNIT_CLASS_RELIGIOUS").map((r) => r.Type));
expect("test: the kept Missionary is gone at the Modern load", (was.UNIT_MISSIONARY ?? 0) >= 1 && (now.UNIT_MISSIONARY ?? 0) === 0, { was: was.UNIT_MISSIONARY, gone, added });
expect("test: no religious unit in the Modern world, and no civilian unit made in its place",
  Object.keys(now).every((t) => !religious.has(t)) && Object.keys(added).every((t) => GameInfo.Units.lookup(t)?.CoreClass === "CORE_CLASS_MILITARY"), { gone, added, now });
const t = Game.turn, t0 = Date.now();
while (Game.turn === t && Date.now() - t0 < 90000) { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); await settle(3000); }
await settle(3000);
Players.get(me).Treasury.changeGoldBalance(3000, -1);
await settle();
const b = buy("UNIT_MISSIONARY");
const s = { turn: Game.turn, religion: Players.get(me).Religion.hasCreatedReligion(), temple: hasBuilding("BUILDING_TEMPLE"),
  missionary: { train: train("UNIT_MISSIONARY"), buy: !!b?.Success, buyWhy: b?.FailureReasons ?? null }, scout: train("UNIT_SCOUT") };
expect("setup: the civ still has its religion and its Temple (else the game refuses missionaries anyway)", s.religion === true && s.temple === true, s);
expect("control: the city can train a unit (Scout)", s.scout === true, s);
expect("test: the Missionary cannot be trained in the Modern world", !s.missionary.train, s);
expect("test: the Missionary cannot be bought in the Modern world", !s.missionary.buy, s);
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
