// Scenario test of units packed in a commander across the world transition (a player report of 2026-11-13: "all the
// units I had packed in commanders were extracted and stacked in my capital; the ones on the map stayed where they were").
// Build: build_mod.py --install --checks --age-points 8 --fast-test 0.01; suite: ContinuousAgesLive.json.
// Phase 1: an Army Commander away from the capital packs its units: in the Antiquity world a mixed army (a Warrior and
// two Slingers: two classes; a Slinger has no double shadow count in the mod's shadow step, so a shadow left over would
// make an extra unit); in the Exploration world two Warriors. A Warrior stays on the map (control: a
// unit on the map keeps its plot). Slot 0 then only ends its turns; the game makes the transition.
// CAPack=MEDJAY+SLINGER (not in scenarios.json) reproduces the known limit "a unique unit of the previous civ lost at a
// civ change": the game removes a packed Medjay at the change to another civ, and no replacement comes back (run
// 20261124-232601-w1; with the Medjays outside the army, nothing is lost: 232351-w1).
// Phase 2 (the next world): the army holds as many units as before, of the same classes, with no plot of their own (the
// test); slot 0 has as many land military units as before (no extra unit made from a shadow of a packed unit, none
// lost); the loose Warrior is on its plot (control).
// CAFleet=1 with StartAge=AGE_EXPLORATION: a Fleet Commander packs a Cog and a Carrack as well (a Carrack has several
// class tags; its shadow can carry any of them), across the Modern transition.
// Negative control: --disable-rule army (the kept units are not put back into their army).
const me = GameContext.localPlayerID;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "army_transition", phase: 1, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
Visibility.revealAllPlots(me);
await settle();
const startWorld = GameInfo.Ages.lookup(Game.age)?.AgeType;
// CAPack=<unit types joined by +> sets the army (for example WARRIOR+SLINGER+SLINGER; live.py --set cuts at a comma).
const packSet = (() => { try { return Automation.getParameter("CurrentTest", "CAPack") ?? null; } catch (e) { return null; } })();
const PACK = packSet ? `${packSet}`.split("+").map((t) => `UNIT_${t.trim().replace(/^UNIT_/, "")}`)
  : startWorld === "AGE_ANTIQUITY" ? ["UNIT_WARRIOR", "UNIT_SLINGER", "UNIT_SLINGER"] : ["UNIT_WARRIOR", "UNIT_WARRIOR"];
const home = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital).location;
const dirs = Object.entries(DirectionTypes).filter(([k]) => k !== "NO_DIRECTION").map(([, v]) => v);
const adj = (p) => dirs.map((d) => GameplayMap.getAdjacentPlotLocation(p, d)).filter((q) => q && q.x >= 0 && q.y >= 0);
const any = (p) => !GameplayMap.isWater(p.x, p.y) && !GameplayMap.isImpassable(p.x, p.y) && !MapCities.getCity(p.x, p.y) && (MapUnits.getUnits(p.x, p.y)?.length ?? 0) === 0;
const own = (p) => any(p) && GameplayMap.getOwner(p.x, p.y) === me;
// The commander's plot P (2 or more plots from the capital, inside slot 0's land if possible) with a free land plot next
// to it for each unit to pack.
// CAFar=1: the commander 6 or more plots from the capital (AI armies in whole games came back empty in other ways).
const far = (() => { try { return Number(Automation.getParameter("CurrentTest", "CAFar") ?? 0) === 1; } catch (e) { return false; } })();
const minDist = far ? 6 : 2;
let spot = null;
for (const ok of far ? [any] : [own, any]) {
  for (let r = minDist; r < minDist + 6 && !spot; r++) {
    for (const i of GameplayMap.getPlotIndicesInRadius(home.x, home.y, r)) {
      const p = GameplayMap.getLocationFromIndex(i);
      if (GameplayMap.getPlotDistance(p.x, p.y, home.x, home.y) < minDist || !ok(p)) continue;
      const n = adj(p).filter(ok);
      if (n.length >= PACK.length) { spot = { p, n: n.slice(0, PACK.length) }; break; }
    }
  }
}
if (!spot) return { ok: false, error: `no free land plot with ${PACK.length} free land plots next to it` };
// The loose Warrior: 3 or more plots from the commander ("pack army" takes the units next to the commander).
for (let r = 2; r < 10 && !spot.loose; r++) {
  for (const i of GameplayMap.getPlotIndicesInRadius(home.x, home.y, r)) {
    const p = GameplayMap.getLocationFromIndex(i);
    if (any(p) && GameplayMap.getPlotDistance(p.x, p.y, spot.p.x, spot.p.y) >= 3) { spot.loose = p; break; }
  }
}
if (!spot.loose) return { ok: false, error: "no free land plot for the loose Warrior" };
// CAGarrison=1: a unit of the first packed unit's type stands on the capital's plot, made before the army's units (so
// it is older: units of one rank and distance are taken in id order). The game puts the units it takes out of the army
// there too; the garrison must stay out of the army (the repack must not take it).
const garrisonOn = (() => { try { return Number(Automation.getParameter("CurrentTest", "CAGarrison") ?? 0) === 1; } catch (e) { return false; } })();
// CAGarrisonType=<unit type>: the garrison's type (default: the first packed unit's type).
const garrisonType = (() => { try { const t = Automation.getParameter("CurrentTest", "CAGarrisonType"); return t ? `UNIT_${`${t}`.trim().replace(/^UNIT_/, "")}` : PACK[0]; } catch (e) { return PACK[0]; } })();
const garrison = garrisonOn ? await caLive.createUnitAndWait(garrisonType, home.x, home.y) : null;
const cmd = await caLive.createUnitAndWait("UNIT_ARMY_COMMANDER", spot.p.x, spot.p.y);
const made = [];
for (const [i, type] of PACK.entries()) made.push(await caLive.createUnitAndWait(type, spot.n[i].x, spot.n[i].y));
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
// The class of a unit as shadows carry it (its tag that names a row of Unit_ShadowReplacements).
const shadowTags = new Set(Array.from(GameInfo.Unit_ShadowReplacements).map((r) => r.Tag));
const classOf = (u) => Array.from(GameInfo.TypeTags).find((t) => t.Type === GameInfo.Units.lookup(u.type)?.UnitType && shadowTags.has(t.Tag))?.Tag ?? "none";
const landMilitary = () => Players.get(me).Units.getUnitIds().map((id) => Units.get(id)).filter((u) => u && !u.isCommanderUnit
  && GameInfo.Units.lookup(u.type)?.Domain === "DOMAIN_LAND" && GameInfo.Units.lookup(u.type)?.CoreClass === "CORE_CLASS_MILITARY");
// The army's unitCount does not count the commander (run 20261124-221155-w1: 2 for two Warriors).
expect(`setup: the commander packed its ${PACK.length} units`, !!army && army.unitCount === PACK.length && packedIds.length === PACK.length,
  { canPack: !!can?.Success, unitCount: army?.unitCount, commander: c ? state(cmd.id) : null, made: made.map((u) => u ? state(u.id) : null), packedIds });
const before = { commander: c ? { x: c.location.x, y: c.location.y } : null, packed: packedIds.length, loose: loose ? state(loose.id) : null,
                 unitCount: army?.unitCount, capital: home, world: startWorld,
                 classes: packedIds.map((id) => classOf(Units.get(id))).sort(),
                 types: packedIds.map((id) => GameInfo.Units.lookup(Units.get(id)?.type)?.UnitType).sort() };
if (garrisonOn) {
  const gu = garrison ? Units.get(garrison.id) : null;
  before.garrison = gu ? { id: garrison.id.id, type: GameInfo.Units.lookup(gu.type)?.UnitType, x: gu.location.x, y: gu.location.y } : null;
  expect("setup: a garrison of the packed type on the capital's plot", !!gu && gu.location.x === home.x && gu.location.y === home.y, { garrison: before.garrison, capital: home });
}
// CAFleet=1 (a game that starts in the Exploration world): a Fleet Commander on the coast packs a Cog and a Carrack.
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
  if (fs) { await caLive.createUnitAndWait("UNIT_COG", fs.a.x, fs.a.y); await caLive.createUnitAndWait("UNIT_CARRACK", fs.b.x, fs.b.y); }
  await settle();
  const fcan = fleetCmd ? Game.UnitCommands.canStart(fleetCmd.id, "UNITCOMMAND_PACK_ARMY", {}, false) : null;
  if (fcan?.Success) Game.UnitCommands.sendRequest(fleetCmd.id, "UNITCOMMAND_PACK_ARMY", {});
  await settle(3000);
  const f = fleetCmd ? Units.get(fleetCmd.id) : null;
  const fleet = f ? Armies.get(f.armyId) : null;
  expect("setup: the Fleet Commander packed the Cog and the Carrack",!!fleet && fleet.unitCount === 2, { found: !!fs, canPack: !!fcan?.Success, unitCount: fleet?.unitCount,
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
before.landMilitary = landMilitary().length;
before.landTypes = landMilitary().map((u) => GameInfo.Units.lookup(u.type)?.UnitType.replace(/^UNIT_/, "")).sort();
expect(`before the age end: the army still holds its ${PACK.length} units`, (army2?.unitCount ?? 0) === PACK.length, { unitCount: army2?.unitCount, commander: before.commander });
if (fleetCmd) {
  const f2 = Units.get(fleetCmd.id);
  before.fleet = f2 ? { x: f2.location.x, y: f2.location.y, count: Armies.get(f2.armyId)?.unitCount } : null;
  expect("before the age end: the fleet still holds its two ships",before.fleet?.count === 2, before.fleet);
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
const shadowTags = new Set(Array.from(GameInfo.Unit_ShadowReplacements).map((r) => r.Tag));
const classOf = (u) => Array.from(GameInfo.TypeTags).find((t) => t.Type === GameInfo.Units.lookup(u.type)?.UnitType && shadowTags.has(t.Tag))?.Tag ?? "none";
const commanders = units.filter((u) => u.isCommanderUnit);
const cmd = commanders.find((u) => prev.commander && u.location.x === prev.commander.x && u.location.y === prev.commander.y)
  ?? commanders.find((u) => GameInfo.Units.lookup(u.type)?.UnitType !== "UNIT_FLEET_COMMANDER");
const army = cmd ? Armies.get(cmd.armyId) : null;
const inArmy = cmd ? units.filter((u) => u.id.id !== cmd.id.id && u.armyId?.id === cmd.armyId?.id) : [];
const warriors = units.filter((u) => GameInfo.Units.lookup(u.type)?.UnitType === "UNIT_WARRIOR");
const landMilitary = units.filter((u) => !u.isCommanderUnit && GameInfo.Units.lookup(u.type)?.Domain === "DOMAIN_LAND"
  && GameInfo.Units.lookup(u.type)?.CoreClass === "CORE_CLASS_MILITARY");
const NEXT = { AGE_ANTIQUITY: "AGE_EXPLORATION", AGE_EXPLORATION: "AGE_MODERN" };
expect("the world is the next age and slot 0 is human", world === NEXT[prev.world] && Players.get(me).isHuman, { world, from: prev.world, turn: Game.turn });
if (prev.fleet) {
  const fc = commanders.find((u) => u.location.x === prev.fleet.x && u.location.y === prev.fleet.y);
  const fleet = fc ? Armies.get(fc.armyId) : null;
  const inFleet = fc ? units.filter((u) => u.id.id !== fc.id.id && u.armyId?.id === fc.armyId?.id) : [];
  const cogs = units.filter((u) => ["UNIT_COG", "UNIT_CARRACK"].includes(GameInfo.Units.lookup(u.type)?.UnitType));
  expect("test: the Fleet Commander's fleet still holds its two ships (a Cog and a Carrack), with no plot of their own", (fleet?.unitCount ?? 0) === 2 && inFleet.length === 2
    && inFleet.some((u) => GameInfo.Units.lookup(u.type)?.UnitType === "UNIT_CARRACK")
    && inFleet.every((u) => u.location.x < 0 || (u.location.x === fc.location.x && u.location.y === fc.location.y)),
    { fleetCommander: fc ? info(fc) : null, unitCount: fleet?.unitCount, inFleet: inFleet.map(info), cogs: cogs.map(info) });
}
expect("the commander was kept on its plot", !!cmd && !!prev.commander && cmd.location.x === prev.commander.x && cmd.location.y === prev.commander.y,
  { commander: cmd ? info(cmd) : null, before: prev.commander });
expect(`test: the commander's army still holds its ${prev.packed} units`, (army?.unitCount ?? 0) === prev.packed && inArmy.length === prev.packed,
  { unitCount: army?.unitCount, inArmy: inArmy.map(info), capital: prev.capital });
const classes = inArmy.map(classOf).sort();
expect("test: the army holds units of the same classes as before", JSON.stringify(classes) === JSON.stringify(prev.classes),
  { before: prev.classes, now: classes, inArmy: inArmy.map(info) });
const types = inArmy.map((u) => GameInfo.Units.lookup(u.type)?.UnitType).sort();
expect("test: the army holds units of the same types as before", JSON.stringify(types) === JSON.stringify(prev.types),
  { before: prev.types, now: types, inArmy: inArmy.map(info) });
// A packed unit has no plot of its own (-9999, -9999); one on the commander's plot counts too.
expect("test: the packed units are with the commander (no plot of their own)", inArmy.length === prev.packed
  && inArmy.every((u) => u.location.x < 0 || (u.location.x === cmd.location.x && u.location.y === cmd.location.y)), { inArmy: inArmy.map(info) });
expect("test: slot 0 has as many land military units as at the age end (no extra unit, none lost)",
  landMilitary.length === prev.landMilitary,
  { before: prev.landMilitary, now: landMilitary.length, beforeTypes: prev.landTypes, nowTypes: landMilitary.map((u) => GameInfo.Units.lookup(u.type)?.UnitType.replace(/^UNIT_/, "")).sort() });
if (prev.garrison) {
  // The load can renumber unit ids: the high part changed and the low 16 bits stayed (run 20261125-105727-w1: 589831
  // before, 524295 after). Match by the low 16 bits.
  const g = units.find((u) => (u.id.id & 0xFFFF) === (prev.garrison.id & 0xFFFF));
  expect("test: the garrison on the capital's plot stays there, out of the army", !!g && !inArmy.includes(g)
    && g.location.x === prev.garrison.x && g.location.y === prev.garrison.y, { before: prev.garrison, now: g ? info(g) : null, inArmy: inArmy.map(info) });
}
const looseNow = prev.loose ? warriors.find((u) => u.location.x === prev.loose.x && u.location.y === prev.loose.y && !inArmy.includes(u)) : null;
expect("control: the Warrior on the map kept its plot", !!looseNow, { before: prev.loose, warriors: warriors.map(info) });
return { ok: checks.every((x) => x.ok), failed: checks.filter((x) => !x.ok), checks, units: units.map(info) };
