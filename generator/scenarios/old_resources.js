// Scenario test of rule 2j (build: build_mod.py --install --checks; suite: ContinuousAgesLive.json --set
// StartAge=AGE_EXPLORATION). A resource of an earlier age that stays on the map, not valid in this world, keeps the
// effects of its last valid age (a player report of 2026-11-01: such resources did nothing).
// The game counts these effects only for a resource ASSIGNED to a settlement, with its matching improvement. In these test
// games resources can be assigned only on turn 1, so the scenario runs on turn 1 and does not end a turn.
//   control: the capital's assigned resource R is unassigned (its yields go), then put back and assigned (they return)
//   test: a kept resource K that the same improvement takes (Hides on a Camp) is put on R's plot and assigned:
//         the capital's yields rise (K's effect). Without the rule (--disable-rule oldres) they do not: this check fails.
const me = GameContext.localPlayerID;
const settle = (ms = 3000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => {
  checks.push({ name, ok, detail });
  caLive.log({ scenario: "old_resources", name, ok, detail });
};
const age = GameInfo.Ages.lookup(Game.age)?.AgeType;
const pr = Players.get(me).Resources;
if (age === "AGE_ANTIQUITY") return { ok: false, error: "run it in a later world: --set StartAge=AGE_EXPLORATION" };
if (pr.isResourceAssignmentLocked()) return { ok: false, error: `resource assignment is locked (turn ${Game.turn}); run on turn 1` };
const cap = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const tid = cap.id;
const city = () => Cities.get(tid);
const Y = ["YIELD_FOOD", "YIELD_PRODUCTION", "YIELD_GOLD", "YIELD_HAPPINESS", "YIELD_SCIENCE", "YIELD_CULTURE"];
const yields = () => Object.fromEntries(Y.map((y) => [y, Math.round(city().Yields.getYield(YieldTypes[y]) * 10) / 10]));
const diff = (a, b) => Object.fromEntries(Y.map((y) => [y, Math.round((a[y] - b[y]) * 10) / 10]).filter(([, v]) => v !== 0));
const gain = (d) => Object.values(d).some((v) => v > 0);
const typeAt = (v) => GameInfo.Resources.lookup(Game.Resources.getResourceOnPlot(v)?.resource)?.ResourceType ?? null;
const assigned = () => city().Resources.getAssignedResources().map((v) => typeAt(v.value));
const cons = (p) => (MapConstructibles.getConstructibles(p.x, p.y) ?? [])
  .map((c) => GameInfo.Constructibles.lookup(Constructibles.getByComponentID(c)?.type)?.ConstructibleType);
const op = (a) => {
  const c = Game.PlayerOperations.canStart(me, PlayerOperationTypes.ASSIGN_RESOURCE, a, false);
  if (c?.Success) Game.PlayerOperations.sendRequest(me, PlayerOperationTypes.ASSIGN_RESOURCE, a);
  return !!c?.Success;
};
const on = (p) => ({ Location: p, City: tid.id, Flags: false, ID: -1 });
const off = (p) => ({ Location: p, City: tid.id, ID: -1, Action: PlayerOperationParameters.Deactivate });
// setResource does not replace a resource: clear the plot first.
async function put(p, type) {
  WorldBuilder.MapPlots.setResource(ResourceTypes.NO_RESOURCE, p, 0);
  await settle(1500);
  WorldBuilder.MapPlots.setResource(GameInfo.Resources.lookup(type).$index, p, 1);
  await settle();
  return typeAt(GameplayMap.getIndexFromLocation(p));
}
// Kept resources of this world: valid in an earlier age, not in this one.
const AGES = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"];
const earlier = new Set(AGES.slice(0, AGES.indexOf(age)));
// GameInfo tables can be iterated but are not arrays.
const validAges = Array.from(GameInfo.Resource_ValidAges);
const validIn = (r) => validAges.filter((v) => v.ResourceType === r).map((v) => v.AgeType);
const kept = new Set(Array.from(GameInfo.Resources).map((r) => r.ResourceType)
  .filter((r) => { const v = validIn(r); return !v.includes(age) && v.some((a) => earlier.has(a)); }));
// An assigned resource R whose improvement also takes a kept resource K (Hides first: one effect, +3 Production).
const validResources = Array.from(GameInfo.Constructible_ValidResources);
const takes = (imp) => validResources.filter((v) => v.ConstructibleType === imp).map((v) => v.ResourceType);
let pick = null;
for (const v of city().Resources.getAssignedResources()) {
  const p = GameplayMap.getLocationFromIndex(v.value);
  for (const imp of cons(p)) {
    const ks = takes(imp).filter((r) => kept.has(r)).sort((a, b) => (b === "RESOURCE_HIDES") - (a === "RESOURCE_HIDES"));
    if (ks.length) { pick = { p, r: typeAt(v.value), imp, k: ks[0] }; break; }
  }
  if (pick) break;
}
if (!pick) return { ok: false, error: "no assigned resource of the capital with an improvement that takes a kept resource",
  assigned: assigned(), kept: [...kept] };
const { p, r, k } = pick;
// Control, step 1: unassign R.
let y = yields();
const r1 = op(off(p));
await settle();
const lossR = diff(yields(), y);
expect(`control: unassigning ${r} changes the capital's yields`, r1 && Object.keys(lossR).length > 0, { lossR, assigned: assigned() });
// Test: K on R's plot, assigned.
const onPlot = await put(p, k);
y = yields();
const kAssign = op(on(p));
await settle();
const gainK = diff(yields(), y);
expect(`${k} is on the ${pick.imp} plot and can be assigned`, onPlot === k && kAssign && assigned().includes(k), { onPlot, kAssign, assigned: assigned() });
expect(`test: assigned ${k} (not valid in ${age}) gives its last valid age's effect`, gain(gainK), { gainK });
// Control, step 2: R back on the plot and assigned again.
op(off(p));
await settle();
const back = await put(p, r);
y = yields();
const rAssign = op(on(p));
await settle();
const gainR = diff(yields(), y);
expect(`control: ${r} put back and assigned again gives its effect back`, back === r && rAssign && gain(gainR), { gainR, assigned: assigned() });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks, pick };
