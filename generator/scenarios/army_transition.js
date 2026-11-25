// Scenario test of units packed in a commander across the world transition (a player report of 2026-11-13: "all the
// units I had packed in commanders were extracted and stacked in my capital; the ones on the map stayed where they were").
// Build: build_mod.py --install --checks --age-points 8; suite: ContinuousAgesLive.json, Antiquity world.
// Phase 1 (Antiquity world): an Army Commander away from the capital packs two Warriors; a third Warrior stays on the map
// (control: a unit on the map keeps its plot); the age ends and the game makes the transition.
// Phase 2 (the next world): the commander's army still holds its two units, with no plot of their own (the test); the
// loose Warrior is still on its plot (control).
// CAFleet=1 with StartAge=AGE_EXPLORATION: a Fleet Commander packs two Cogs as well, across the Modern transition.
// Negative control: --disable-rule army (the kept units are not put back into their army).
const me = GameContext.localPlayerID;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "army_transition", phase: 1, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
Visibility.revealAllPlots(me);
await settle();
const home = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital).location;
const dirs = Object.entries(DirectionTypes).filter(([k]) => k !== "NO_DIRECTION").map(([, v]) => v);
const adj = (p) => dirs.map((d) => GameplayMap.getAdjacentPlotLocation(p, d)).filter((q) => q && q.x >= 0 && q.y >= 0);
const land = (p) => !GameplayMap.isWater(p.x, p.y) && !GameplayMap.isImpassable(p.x, p.y) && GameplayMap.getOwner(p.x, p.y) === me
  && !MapCities.getCity(p.x, p.y) && (MapUnits.getUnits(p.x, p.y)?.length ?? 0) === 0;
// The commander's plot P (inside slot 0's land, 2 or more plots from the capital) with two free land plots next to it for
// the Warriors to pack, and a fourth free plot for the loose Warrior.
let spot = null;
for (let r = 2; r < 6 && !spot; r++) {
  for (const i of GameplayMap.getPlotIndicesInRadius(home.x, home.y, r)) {
    const p = GameplayMap.getLocationFromIndex(i);
    if (GameplayMap.getPlotDistance(p.x, p.y, home.x, home.y) < 2 || !land(p)) continue;
    const n = adj(p).filter(land);
    if (n.length >= 2) { spot = { p, a: n[0], b: n[1] }; break; }
  }
}
// Slot 0's land is small on turn 3: else any free land plot near the capital.
const any = (p) => !GameplayMap.isWater(p.x, p.y) && !GameplayMap.isImpassable(p.x, p.y) && !MapCities.getCity(p.x, p.y) && (MapUnits.getUnits(p.x, p.y)?.length ?? 0) === 0;
for (let r = 2; r < 8 && !spot; r++) {
  for (const i of GameplayMap.getPlotIndicesInRadius(home.x, home.y, r)) {
    const p = GameplayMap.getLocationFromIndex(i);
    if (GameplayMap.getPlotDistance(p.x, p.y, home.x, home.y) < 2 || !any(p)) continue;
    const n = adj(p).filter(any);
    if (n.length >= 2) { spot = { p, a: n[0], b: n[1] }; break; }
  }
}
if (!spot) return { ok: false, error: "no free land plot with two free land plots next to it" };
// The loose Warrior: 3 or more plots from the commander ("pack army" takes the units next to the commander).
for (let r = 2; r < 10 && !spot.loose; r++) {
  for (const i of GameplayMap.getPlotIndicesInRadius(home.x, home.y, r)) {
    const p = GameplayMap.getLocationFromIndex(i);
    if (any(p) && GameplayMap.getPlotDistance(p.x, p.y, spot.p.x, spot.p.y) >= 3) { spot.loose = p; break; }
  }
}
if (!spot.loose) return { ok: false, error: "no free land plot for the loose Warrior" };
const cmd = await caLive.createUnitAndWait("UNIT_ARMY_COMMANDER", spot.p.x, spot.p.y);
const w1 = await caLive.createUnitAndWait("UNIT_WARRIOR", spot.a.x, spot.a.y);
const w2 = await caLive.createUnitAndWait("UNIT_WARRIOR", spot.b.x, spot.b.y);
const loose = await caLive.createUnitAndWait("UNIT_WARRIOR", spot.loose.x, spot.loose.y);
await settle();
const state = (id) => { const u = Units.get(id); return u ? { id, type: GameInfo.Units.lookup(u.type)?.UnitType, x: u.location.x, y: u.location.y, armyId: u.armyId } : null; };
const can = cmd ? Game.UnitCommands.canStart(cmd.id, "UNITCOMMAND_PACK_ARMY", {}, false) : null;
if (can?.Success) Game.UnitCommands.sendRequest(cmd.id, "UNITCOMMAND_PACK_ARMY", {});
await settle(3000);
const c = cmd ? Units.get(cmd.id) : null;
const army = c ? Armies.get(c.armyId) : null;
// A packed unit shares the commander's army id and has no plot (-9999, -9999: live run 20261124-220017-w1).
const packedIds = Players.get(me).Units.getUnitIds().filter((id) => id.id !== cmd?.id?.id && Units.get(id)?.armyId && c && Units.get(id).armyId.id === c.armyId.id);
// The army's unitCount does not count the commander (run 20261124-221155-w1: 2 for two Warriors).
expect("setup: the commander packed the two Warriors", !!army && army.unitCount === 2 && packedIds.length === 2,
  { canPack: !!can?.Success, unitCount: army?.unitCount, commander: c ? state(cmd.id) : null, w1: w1 ? state(w1.id) : null, w2: w2 ? state(w2.id) : null, packedIds });
const before = { commander: c ? { x: c.location.x, y: c.location.y } : null, packed: packedIds.length, loose: loose ? state(loose.id) : null,
                 unitCount: army?.unitCount, capital: home, world: GameInfo.Ages.lookup(Game.age)?.AgeType };
// CAFleet=1 (a game that starts in the Exploration world): a Fleet Commander on the coast packs two Cogs as well.
const fleetOn = (() => { try { return Number(Automation.getParameter("CurrentTest", "CAFleet") ?? 0) === 1; } catch (e) { return false; } })();
let fleetCmd = null;
if (fleetOn) {
  const COAST = GameInfo.Terrains.lookup("TERRAIN_COAST").$index;
  const coast = (p) => GameplayMap.getTerrainType(p.x, p.y) === COAST && (MapUnits.getUnits(p.x, p.y)?.length ?? 0) === 0;
  let fs = null;
  for (let r = 1; r < 12 && !fs; r++) {
    for (const i of GameplayMap.getPlotIndicesInRadius(home.x, home.y, r)) {
      const p = GameplayMap.getLocationFromIndex(i);
      if (!coast(p) || GameplayMap.getPlotDistance(p.x, p.y, spot.p.x, spot.p.y) < 3) continue;
      const n = adj(p).filter(coast);
      if (n.length >= 2) { fs = { p, a: n[0], b: n[1] }; break; }
    }
  }
  fleetCmd = fs ? await caLive.createUnitAndWait("UNIT_FLEET_COMMANDER", fs.p.x, fs.p.y) : null;
  if (fs) { await caLive.createUnitAndWait("UNIT_COG", fs.a.x, fs.a.y); await caLive.createUnitAndWait("UNIT_COG", fs.b.x, fs.b.y); }
  await settle();
  const fcan = fleetCmd ? Game.UnitCommands.canStart(fleetCmd.id, "UNITCOMMAND_PACK_ARMY", {}, false) : null;
  if (fcan?.Success) Game.UnitCommands.sendRequest(fleetCmd.id, "UNITCOMMAND_PACK_ARMY", {});
  await settle(3000);
  const f = fleetCmd ? Units.get(fleetCmd.id) : null;
  const fleet = f ? Armies.get(f.armyId) : null;
  expect("setup: the Fleet Commander packed the two Cogs", !!fleet && fleet.unitCount === 2, { found: !!fs, canPack: !!fcan?.Success, unitCount: fleet?.unitCount,
    at: f ? { x: f.location.x, y: f.location.y } : null });
}
// To the age end, slot 0 only ending its turns (with caLive.advance the AI plays slot 0 and unpacked the army: run
// 20261124-220017-w1); the game then makes the transition itself.
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
for (let i = 0; i < 60 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { /* the request is sent again */ } }
const c2 = cmd ? Units.get(cmd.id) : null;
const army2 = c2 ? Armies.get(c2.armyId) : null;
before.commander = c2 ? { x: c2.location.x, y: c2.location.y } : before.commander;  // the AI does not move slot 0's units
before.unitCount = army2?.unitCount ?? before.unitCount;
before.loose = loose ? state(loose.id) : before.loose;
expect("before the age end: the army still holds the two Warriors", (army2?.unitCount ?? 0) === 2,{ unitCount: army2?.unitCount, commander: before.commander });
if (fleetCmd) {
  const f2 = Units.get(fleetCmd.id);
  before.fleet = f2 ? { x: f2.location.x, y: f2.location.y, count: Armies.get(f2.armyId)?.unitCount } : null;
  expect("before the age end: the fleet still holds the two Cogs", before.fleet?.count === 2, before.fleet);
}
expect("the age is at its end", left() <= 0, { turn: Game.turn, left: left() });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((x) => x.ok), checks, before, transition: { auto: true } };

//// PHASE 2: the next world
const me = GameContext.localPlayerID;
const prev = globalThis.caPrev?.[0]?.before ?? {};
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "army_transition", phase: 2, name, ok, detail }); };
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const units = Players.get(me).Units.getUnitIds().map((id) => Units.get(id)).filter(Boolean);
const info = (u) => ({ id: u.id.id, type: GameInfo.Units.lookup(u.type)?.UnitType, x: u.location.x, y: u.location.y, army: u.armyId?.id ?? null });
const commanders = units.filter((u) => u.isCommanderUnit);
const cmd = commanders.find((u) => prev.commander && u.location.x === prev.commander.x && u.location.y === prev.commander.y)
  ?? commanders.find((u) => GameInfo.Units.lookup(u.type)?.UnitType !== "UNIT_FLEET_COMMANDER");
const army = cmd ? Armies.get(cmd.armyId) : null;
const inArmy = cmd ? units.filter((u) => u.id.id !== cmd.id.id && u.armyId?.id === cmd.armyId?.id) : [];
const warriors = units.filter((u) => GameInfo.Units.lookup(u.type)?.UnitType === "UNIT_WARRIOR");
const NEXT = { AGE_ANTIQUITY: "AGE_EXPLORATION", AGE_EXPLORATION: "AGE_MODERN" };
expect("the world is the next age and slot 0 is human", world === NEXT[prev.world] && Players.get(me).isHuman, { world, from: prev.world, turn: Game.turn });
if (prev.fleet) {
  const fc = commanders.find((u) => u.location.x === prev.fleet.x && u.location.y === prev.fleet.y);
  const fleet = fc ? Armies.get(fc.armyId) : null;
  const inFleet = fc ? units.filter((u) => u.id.id !== fc.id.id && u.armyId?.id === fc.armyId?.id) : [];
  const cogs = units.filter((u) => GameInfo.Units.lookup(u.type)?.UnitType === "UNIT_COG");
  expect("test: the Fleet Commander's fleet still holds its two Cogs, with no plot of their own", (fleet?.unitCount ?? 0) === 2 && inFleet.length === 2
    && inFleet.every((u) => u.location.x < 0 || (u.location.x === fc.location.x && u.location.y === fc.location.y)),
    { fleetCommander: fc ? info(fc) : null, unitCount: fleet?.unitCount, inFleet: inFleet.map(info), cogs: cogs.map(info) });
}
expect("the commander was kept on its plot", !!cmd && !!prev.commander && cmd.location.x === prev.commander.x && cmd.location.y === prev.commander.y,
  { commander: cmd ? info(cmd) : null, before: prev.commander });
expect("test: the commander's army still holds its two units", (army?.unitCount ?? 0) === 2 && inArmy.length === 2,
  { unitCount: army?.unitCount, inArmy: inArmy.map(info), warriors: warriors.map(info), capital: prev.capital });
// A packed unit has no plot of its own (-9999, -9999); one on the commander's plot counts too.
expect("test: the packed units are with the commander (no plot of their own)", inArmy.length === 2
  && inArmy.every((u) => u.location.x < 0 || (u.location.x === cmd.location.x && u.location.y === cmd.location.y)), { inArmy: inArmy.map(info) });
const looseNow = prev.loose ? warriors.find((u) => u.location.x === prev.loose.x && u.location.y === prev.loose.y && !inArmy.includes(u)) : null;
expect("control: the Warrior on the map kept its plot", !!looseNow, { before: prev.loose, warriors: warriors.map(info) });
return { ok: checks.every((x) => x.ok), failed: checks.filter((x) => !x.ok), checks, units: units.map(info) };
