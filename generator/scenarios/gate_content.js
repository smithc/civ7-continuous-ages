// Scenario test of the positive side of the tech gate (design goals 3 and 5; build: build_mod.py --install --checks;
// suite: ContinuousAgesLive.json, Antiquity world). Content of a later age is locked before the civ's Breakthrough
// and can be used after it:
//   behind the gate: an Exploration unit and an Exploration building need an unlock in slot 0's capital
//   past the gate (the gate and the item's tech granted): neither needs an unlock any more; the unit can be trained
const me = GameContext.localPlayerID;
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH";
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "gate_content", name, ok, detail }); };
async function grant(node) {
  caLive.grantNode(node);
  for (let i = 0; i < 10 && !caLive.hasNode(node); i++) await settle(500);
  return caLive.hasNode(node);
}
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
const city = Players.get(me).Cities.getCityIds().find((id) => Cities.get(id)?.isCapital);
const exUnlock = (kind) => GameInfo.ProgressionTreeNodeUnlocks.filter((u) => u.TargetKind === kind && /^NODE_TECH_EX_/.test(u.ProgressionTreeNodeType));
// A generic land unit of the Exploration techs, without a strategic resource or a trait.
const unitRow = exUnlock("KIND_UNIT").find((u) => {
  const d = GameInfo.Units.lookup(u.TargetType);
  return d && d.CanTrain && !d.TraitType && d.Domain === "DOMAIN_LAND" && !d.StrategicResource;
});
// A generic building of the Exploration techs.
const buildingRow = exUnlock("KIND_CONSTRUCTIBLE").find((u) => GameInfo.Constructibles.lookup(u.TargetType)?.ConstructibleClass === "BUILDING"
  && !GameInfo.Buildings.lookup(u.TargetType)?.TraitType);
if (!unitRow || !buildingRow) return { ok: false, error: "no Exploration unit or building found", unitRow, buildingRow };
const unit = unitRow.TargetType, building = buildingRow.TargetType;
const buildingQuery = () => {
  const def = GameInfo.Constructibles.lookup(building);
  const r = (Game.CityOperations.canStartQuery(city, CityOperationTypes.BUILD, CityQueryType.Constructible) ?? []).find((x) => x.index === def.$index)?.result;
  return { listed: !!r, ok: !!r?.Success, neededUnlock: r?.NeededUnlock ?? null, plots: r?.Plots?.length ?? 0 };
};
const needs = (r) => r.neededUnlock !== null && r.neededUnlock !== undefined && r.neededUnlock != -1;
const u0 = caLive.canTrain(unit), b0 = buildingQuery();
// (The unit query has no NeededUnlock field for units: "cannot be trained" before and "can be trained" after is the proof.)
expect(`behind the gate: ${unit} cannot be trained`, !u0.ok && !u0.queryOk, u0);
expect(`behind the gate: ${building} needs an unlock`, needs(b0), b0);
expect("gate granted", await grant(GATE));
expect(`${unitRow.ProgressionTreeNodeType} granted`, await grant(unitRow.ProgressionTreeNodeType));
expect(`${buildingRow.ProgressionTreeNodeType} granted`, await grant(buildingRow.ProgressionTreeNodeType));
await settle();
const u1 = caLive.canTrain(unit), b1 = buildingQuery();
expect(`past the gate: ${unit} can be trained`, u1.ok, u1);
expect(`past the gate: ${building} needs no unlock`, !needs(b1), b1);
return { ok: checks.every((c) => c.ok), unit, building, failed: checks.filter((c) => !c.ok), checks };
