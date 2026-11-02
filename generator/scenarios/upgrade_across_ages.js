// Scenario test of rule 2g, unit upgrades across ages (build: build_mod.py --install --checks; suite:
// ContinuousAgesLive.json, Antiquity world). The base game has no upgrade from one age's units to the next age's;
// the mod adds them, and an upgrade needs the civ to be able to build the target (its gate). No run ever showed one.
//   behind the gate: a last-tier Antiquity unit cannot upgrade to its Exploration successor
//   past the gate (the gate and the target's tech granted): the upgrade is allowed, and the unit becomes the target
const me = GameContext.localPlayerID;
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH";
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "upgrade_across_ages", name, ok, detail }); };
async function grant(node) {
  caLive.grantNode(node);
  for (let i = 0; i < 10 && !caLive.hasNode(node); i++) await settle(500);
  return caLive.hasNode(node);
}
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
const unlocksOf = (t) => GameInfo.ProgressionTreeNodeUnlocks.filter((u) => u.TargetKind === "KIND_UNIT" && u.TargetType === t).map((u) => u.ProgressionTreeNodeType);
// A cross-age upgrade (rule 2g): the source has no Exploration unlock, the target has one; a land unit without a trait.
const row = GameInfo.UnitUpgrades.find((r) => {
  const a = GameInfo.Units.lookup(r.Unit), b = GameInfo.Units.lookup(r.UpgradeUnit);
  return a && b && a.Domain === "DOMAIN_LAND" && !a.TraitType && !b.TraitType && !b.StrategicResource
    && !unlocksOf(r.Unit).some((n) => /^NODE_TECH_EX_/.test(n)) && unlocksOf(r.UpgradeUnit).some((n) => /^NODE_TECH_EX_/.test(n));
});
if (!row) return { ok: false, error: "no cross-age upgrade found" };
const from = row.Unit, to = row.UpgradeUnit;
const capital = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital).location;
const unitsOf = (type) => Players.get(me).Units.getUnitIds().map((id) => Units.get(id)).filter((u) => GameInfo.Units.lookup(u.type)?.UnitType === type);
Players.grantYield(me, YieldTypes.YIELD_GOLD, 5000);
const unit = await caLive.createUnitAndWait(from, capital.x, capital.y);  // up to 15 s (a fixed 2 s can be too short)
if (!unit) return { ok: false, error: `no ${from} was placed`, checks };
const can = () => { const r = Game.UnitCommands.canStart(unit.id, "UNITCOMMAND_UPGRADE", {}, false); return { ok: !!r?.Success, reasons: r?.FailureReasons ?? [] }; };
const c0 = can();
expect(`behind the gate: ${from} cannot upgrade to ${to}`, !c0.ok, c0);
expect("gate granted", await grant(GATE));
for (const node of unlocksOf(to).filter((n) => /^NODE_TECH_EX_/.test(n)).slice(0, 1)) expect(`${node} granted`, await grant(node));
await settle();
const c1 = can();
expect(`past the gate: ${from} may upgrade to ${to}`, c1.ok, { ...c1, gold: Players.get(me).Treasury?.goldBalance });
if (c1.ok) {
  const before = unitsOf(to).length;
  Game.UnitCommands.sendRequest(unit.id, "UNITCOMMAND_UPGRADE", {});
  await caLive.waitFor(() => unitsOf(to).length > before);  // up to 15 s (a fixed 3 s can be too short)
  expect(`the unit is now a ${to}`, unitsOf(to).length === before + 1, { from: unitsOf(from).length, to: unitsOf(to).length });
}
return { ok: checks.every((c) => c.ok), from, to, failed: checks.filter((c) => !c.ok), checks };
