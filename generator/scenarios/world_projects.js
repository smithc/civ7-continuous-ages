// Scenario test of rules 2k and 2l (build: build_mod.py --install --checks; suite: ContinuousAgesLive.json, Antiquity
// world, or --set StartAge=AGE_EXPLORATION). Projects that feed a world system (victory points, a legacy path) are FINAL
// (built only in their own world age, rule 2k) or ACHIEVEMENTS (built at the civ's own age in any world, once per game,
// rule 2l; once per game is proven by project_achievements.js).
// For each such project with no building prerequisite, the civ gets its tech (with its mastery when the project needs
// it), then the capital is asked whether it can start the project:
//   control: a project of this world age can be started
//   test: an achievement of another world age can be started (rule 2l: RequiresUnlock + the unlock while the civ has
//   the tech); a final project of another world age cannot (rule 2k; all finals need a building today, so none is
//   tested here).
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => {
  checks.push({ name, ok, detail });
  caLive.log({ scenario: "world_projects", name, ok, detail });
};
const age = GameInfo.Ages.lookup(Game.age)?.AgeType;
const list = globalThis.caWorldProjects ?? {};
if (Object.keys(list).length === 0) return { ok: false, error: "caWorldProjects is empty (a --checks build of this version?)" };
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
const cap = Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const canStart = (p) => !!Game.CityOperations.canStart(cap.id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
// GameInfo tables can be iterated but are not arrays.
const unlocks = Array.from(GameInfo.ProgressionTreeNodeUnlocks).filter((u) => u.TargetKind === "KIND_PROJECT");
const tested = { own: 0, other: 0 }, skipped = [];
// Rule 2l (branch explore/project-achievements): an ACHIEVEMENT can be started in any world once its tech is done; a
// FINAL project only in its own world age (rule 2k). caWorldProjects: {project: {ages, final, why, node, depth, tag}}.
for (const [p, group] of Object.entries(list)) {
  const ages = group.ages;
  const info = GameInfo.Projects.lookup(p);
  const u = unlocks.find((r) => r.TargetType === p);
  if (!info || !u || info.PrereqConstructible) {
    skipped.push({ p, reason: !info ? "not in this world's data" : !u ? "no tech unlock" : `needs ${info.PrereqConstructible}` });
    continue;
  }
  // Each debug grant adds one depth (FullyUnlock does not give the mastery; live test 2026-11-07), so grant until the
  // node has the depth that the project needs (Heliocentric Model: the mastery of Education).
  const nodeHash = GameInfo.ProgressionTreeNodes.lookup(u.ProgressionTreeNodeType)?.$hash;
  const depth = () => Game.ProgressionTrees.getNode(me, nodeHash)?.depthUnlocked ?? 0;
  for (let i = 0; i < 4 && depth() < u.UnlockDepth; i++) {
    const before = depth();
    caLive.grantNode(u.ProgressionTreeNodeType, me, 1);
    for (let j = 0; j < 10 && depth() === before; j++) await settle(500);
  }
  await settle(1500);
  const own = ages.includes(age);
  const want = own || !group.final;
  const can = canStart(p);
  tested[own ? "own" : "other"]++;
  expect(`${p}: its tech has the depth the project needs`, depth() >= u.UnlockDepth, { node: u.ProgressionTreeNodeType, need: u.UnlockDepth, depth: depth() });
  expect(own ? `control: ${p} (this world age) can be started`
    : group.final ? `test: final ${p} (${ages.join("/")}) cannot be started in ${age}`
    : `test: achievement ${p} (${ages.join("/")}) can be started in ${age} by a civ with its tech`,
    can === want, { can, final: group.final, node: u.ProgressionTreeNodeType, depth: depth(), need: u.UnlockDepth, requiresUnlock: info.RequiresUnlock });
}
expect("at least one project of this world age and one of another age were tested", tested.own > 0 && tested.other > 0, { tested, skipped });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks, skipped };
