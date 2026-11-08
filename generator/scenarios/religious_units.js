// Scenario test of rule 2m in the Antiquity world (build: build_mod.py --install --checks; suite: ContinuousAgesLive.json).
// Religious units follow religion, a world system: trained, bought and kept only in the Exploration world (a player
// report of 2026-11-01: missionaries in the Modern world only gave gold). Slot 0 is a leading civ (its Exploration
// Breakthrough is granted) with Piety, a Temple (placed by debug), gold and a religion (founded by the direct operation:
// the game offers none in the Antiquity world, and it refuses a missionary to a civ without one). Control unit: the
// Swordsman, which the same Breakthrough unlocks and which needs no building.
//   the Swordsman can be trained and bought (controls); the Missionary cannot (tests)
// Without the rule (--disable-rule religion) the tests fail (20261107-204010-w1: the Missionary could be trained and
// bought). The Exploration and Modern worlds: religion_modern.js and religion_lagging.js. One game, no transition: a node
// granted by debug in an earlier world did not unlock its units after a transition in a test (normal research does).
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "religious_units", phase: 1, name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const train = (u) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { UnitType: Database.makeHash(u) }, false)?.Success;
const buy = (u) => !!Game.CityCommands.canStart(cap().id, CityCommandTypes.PURCHASE, { UnitType: Database.makeHash(u) }, false)?.Success;
const consAt = (x, y) => (MapConstructibles.getConstructibles(x, y) ?? []).map((id) => GameInfo.Constructibles.lookup(Constructibles.getByComponentID(id)?.type)?.ConstructibleType);
const hasBuilding = (b) => GameplayMap.getPlotIndicesInRadius(cap().location.x, cap().location.y, 3).some((i) => { const l = GameplayMap.getLocationFromIndex(i); return consAt(l.x, l.y).includes(b); });
async function place(b) {
  if (hasBuilding(b)) return true;
  const plots = [cap().location, ...GameplayMap.getPlotIndicesInRadius(cap().location.x, cap().location.y, 2).map((i) => GameplayMap.getLocationFromIndex(i))
    .filter((l) => GameplayMap.getOwner(l.x, l.y) === me && MapCities.getDistrict(l.x, l.y) != null)];
  for (const l of plots) {
    Game.PlayerOperations.sendRequest(me, "CREATE_ELEMENT", { Kind: "CONSTRUCTIBLE", Type: b, Location: { x: l.x, y: l.y }, Owner: me });
    await settle(1500);
    if (hasBuilding(b)) return true;
  }
  return false;
}
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
async function grant(n) { caLive.grantNode(n, me, 1); for (let i = 0; i < 10 && !caLive.hasNode(n); i++) await settle(500); return caLive.hasNode(n); }
// The game refuses a missionary to a civ without a founded religion (live test 2026-11-07), so the civ founds one.
// In the Antiquity world the game offers no religion (canCreateReligion is false even with Piety): the direct operation
// FOUND_RELIGION is test setup beyond normal play, so that the missionary check is not refused for that reason alone.
const grants = { gate: await grant("NODE_TECH_CA_EXPLORATION_BREAKTHROUGH"), cgate: await grant("NODE_CIVIC_CA_EXPLORATION_BREAKTHROUGH"),
  piety: await grant("NODE_CIVIC_EX_MAIN_PIETY") };
const temple = await place("BUILDING_TEMPLE");
const offered = Players.get(me).Religion.canCreateReligion();
const relType = Array.from(GameInfo.Religions).find((r) => !r.RequiresCustomName)?.ReligionType;
Game.PlayerOperations.sendRequest(me, PlayerOperationTypes.FOUND_RELIGION, { ReligionType: Database.makeHash(relType) });
for (let i = 0; i < 10 && !Players.get(me).Religion.hasCreatedReligion(); i++) await settle(500);
Players.get(me).Treasury.changeGoldBalance(3000, -1);
await settle();
const s = { grants, temple, offered, religion: Players.get(me).Religion.hasCreatedReligion(), gold: Players.get(me).Treasury.goldBalance,
  swordsman: { train: train("UNIT_SWORDSMAN"), buy: buy("UNIT_SWORDSMAN") }, missionary: { train: train("UNIT_MISSIONARY"), buy: buy("UNIT_MISSIONARY") } };
expect("observation: in the Antiquity world the game offers no religion (normal play)", offered === false, s);
expect("setup: past the gate, Piety, a Temple, a religion (direct operation) and gold", grants.gate && grants.piety && temple && s.religion && s.gold >= 1000, s);
expect("control: the Swordsman (same Breakthrough) can be trained and bought in the Antiquity world", s.swordsman.train && s.swordsman.buy, s);
expect("test: the Missionary cannot be trained in the Antiquity world", !s.missionary.train, s);
expect("test: the Missionary cannot be bought in the Antiquity world", !s.missionary.buy, s);
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
