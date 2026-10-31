// Scenario test of rule 2i (build: python build_mod.py --install --checks; suite: --set Player0Civ=<a civ with a gap
// pair>, for example CIVILIZATION_MING (Mandarin > Merchant, Exploration) or CIVILIZATION_MUGHAL (Zamindar > Settler,
// Modern)). A unique unit that waits for its Breakthrough must not block the base unit it replaces, and after the
// Breakthrough the civ trains the unique unit and not the base unit, as in the base game.
//   before the gate: the engine maps the base unit to itself (getBuildUnit) and does not disable it
//   after the gate (granted with the debug operation GRANT_TREE_NODE): the base unit is disabled
//   control: a base unit of a pair of another civ's trait stays enabled
const GATES = { AGE_EXPLORATION: ["NODE_TECH_CA_EXPLORATION_BREAKTHROUGH"],
                AGE_MODERN: ["NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", "NODE_TECH_CA_MODERN_BREAKTHROUGH"] };
const pid = GameContext.localPlayerID;
const player = Players.get(pid);
const civ = GameInfo.Civilizations.lookup(player.civilizationType)?.CivilizationType;
const traits = new Set(GameInfo.CivilizationTraits.filter((r) => r.CivilizationType === civ).map((r) => r.TraitType));
const mine = globalThis.caReplaceGaps.filter(([, , trait]) => traits.has(trait));
const others = globalThis.caReplaceGaps.filter(([, base]) => !mine.some(([, b]) => b === base));
if (mine.length === 0) return { ok: false, error: `${civ} has no gap pair; choose another Player0Civ` };
if (player.Cities.getCityIds().length === 0) await caLive.advance(2);
const hashOf = (u) => GameInfo.Units.lookup(u)?.$hash;
const typeOf = (t) => (t == null ? null : GameInfo.Units.lookup(t)?.UnitType ?? `${t}`);
const look = (u) => ({ buildUnit: typeOf(player.Units.getBuildUnit(u)), disabled: player.Units.isBuildDisabled(hashOf(u)), train: caLive.canTrain(u) });
const checks = [];
const expect = (name, value, want, detail) => {
  const ok = value === want;
  checks.push({ name, ok, value, want, detail });
  caLive.log({ scenario: "rule_2i", civ, name, ok, value, want, detail });
};
for (const [uu, base, , age] of mine) {
  const b = look(base);
  expect(`${base} maps to itself before the gate`, b.buildUnit, base, b);
  expect(`${base} not disabled before the gate`, b.disabled, false, b);
}
const ages = [...new Set(mine.map(([, , , age]) => age))];
const granted = [];
for (const node of [...new Set(ages.flatMap((a) => GATES[a]))]) granted.push({ node, ...caLive.grantNode(node) });
await new Promise((r) => setTimeout(r, 2000));
for (const [uu, base, , age] of mine) {
  for (const node of GATES[age]) expect(`${node} completed`, caLive.hasNode(node), true, {});
  const b = look(base), u = look(uu);
  expect(`${base} disabled after the gate`, b.disabled, true, b);
  expect(`${uu} not disabled after the gate`, u.disabled, false, u);
}
for (const [uu, base] of others.slice(0, 3)) {
  const b = look(base);
  expect(`control: ${base} (pair of another civ) not disabled`, b.disabled, false, b);
}
return { ok: checks.every((c) => c.ok), civ, pairs: mine, granted, failed: checks.filter((c) => !c.ok), checks: checks.length };
