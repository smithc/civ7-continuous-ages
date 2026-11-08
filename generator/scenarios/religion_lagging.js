// Scenario test of rule 2m in the units' own world (build: build_mod.py --install --checks; suite: ContinuousAgesLive.json
// --set StartAge=AGE_EXPLORATION). In the base game the Missionary needs no tech: a Temple and the civ's founded religion.
// Rules 2b and 2d had added the Exploration Breakthrough, so a civ behind it had no missionaries while religions spread.
//   setup: a civ WITHOUT its tech Breakthrough (Exploration start) gets the civic Breakthrough and Piety (debug), a Temple
//          (debug) and founds a religion through the normal offer (canCreateReligion)
//   test: it can train and buy the Missionary. Without the rule (--disable-rule religion) it cannot: this check fails.
//   control: the Swordsman, which the tech Breakthrough unlocks, cannot be trained (the civ is behind that gate)
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "religion_lagging", name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const train = (u) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { UnitType: Database.makeHash(u) }, false)?.Success;
const buy = (u) => !!Game.CityCommands.canStart(cap().id, CityCommandTypes.PURCHASE, { UnitType: Database.makeHash(u) }, false)?.Success;
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
await caLive.endTurn();  // not the first turn of the world (a city refused even the control unit then, in a test)
await settle(3000);
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const setup = { world, turn: Game.turn, techGate: caLive.hasNode("NODE_TECH_CA_EXPLORATION_BREAKTHROUGH"),
  cgate: await grant("NODE_CIVIC_CA_EXPLORATION_BREAKTHROUGH"), piety: await grant("NODE_CIVIC_EX_MAIN_PIETY"), temple: await place("BUILDING_TEMPLE") };
setup.offered = Players.get(me).Religion.canCreateReligion();
const relType = Array.from(GameInfo.Religions).find((r) => !r.RequiresCustomName)?.ReligionType;
if (setup.offered) Game.PlayerOperations.sendRequest(me, PlayerOperationTypes.FOUND_RELIGION, { ReligionType: Database.makeHash(relType) });
for (let i = 0; i < 10 && !Players.get(me).Religion.hasCreatedReligion(); i++) await settle(500);
setup.religion = Players.get(me).Religion.hasCreatedReligion();
Players.get(me).Treasury.changeGoldBalance(3000, -1);
await settle();
expect("setup: Exploration world, a civ behind its tech Breakthrough, with Piety, a Temple and a religion (normal offer)",
  world === "AGE_EXPLORATION" && !setup.techGate && setup.piety && setup.temple && setup.offered && setup.religion, setup);
const s = { missionary: { train: train("UNIT_MISSIONARY"), buy: buy("UNIT_MISSIONARY") }, swordsman: { train: train("UNIT_SWORDSMAN") } };
expect("control: the Swordsman (tech Breakthrough) cannot be trained by a civ behind that gate", !s.swordsman.train, s);
expect("test: the Missionary can be trained without the tech Breakthrough (as in the base game)", s.missionary.train, s);
expect("test: the Missionary can be bought without the tech Breakthrough", s.missionary.buy, s);
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
