// Scenario test of rule 2l (build: build_mod.py --install --checks --age-points 8; suite: ContinuousAgesLive.json).
// Achievement projects are built at the civ's own age in any world, once per game, and the triumph of their age reads
// the record (a narrative tag), so a project built early counts when the world reaches that age.
// Phase 1, Antiquity world (a leading civ):
//   Chart the Stars (Antiquity) and Heliocentric Model (Exploration) can be started (rule 2k alone blocks the second);
//   both are completed (debug completeProduction), then neither can be started again
// Phase 2, Exploration world, after the world transition:
//   test: Chart the Stars and Heliocentric Model cannot be started (the record survived the transition)
//   control: Spherical Earth (never built) can be started in the later world
//   test: when Invent Calculus is completed, the Exploration science triumph (Heliocentric Model + Invent Calculus)
//         triggers: Heliocentric Model counts through its tag from the Antiquity world
//   Without the rule (--disable-rule achieve) the projects can be started again and the triumph does not trigger.
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => {
  checks.push({ name, ok, detail });
  caLive.log({ scenario: "project_achievements", phase: 1, name, ok, detail });
};
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const canStart = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
// Each debug grant adds one depth: grant until the node has the depth.
async function grantTo(node, depth) {
  const hash = GameInfo.ProgressionTreeNodes.lookup(node)?.$hash;
  const now = () => Game.ProgressionTrees.getNode(me, hash)?.depthUnlocked ?? 0;
  for (let i = 0; i < 4 && now() < depth; i++) {
    const before = now();
    caLive.grantNode(node, me, 1);
    for (let j = 0; j < 10 && now() === before; j++) await settle(500);
  }
  return now();
}
async function complete(p) {
  Game.CityOperations.sendRequest(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p), InsertMode: CityOperationsParametersValues.Exclusive });
  await settle();
  cap().BuildQueue.completeProduction();
  await settle(3000);
}
const tagPoints = (p) => { try { return Players.get(me).Identity?.getNarrativeTagPoints?.(Database.makeHash(`NARRATIVE_TAG_CA_ONCE_${p.slice(8)}`)); } catch (e) { return `error ${e}`; } };
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
// A leading civ: past its Exploration Breakthrough (without it the in-game check fails: Exploration techs before the gate).
const depths = { gate: await grantTo("NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", 1), nav: await grantTo("NODE_TECH_AQ_NAVIGATION", 1),
  edu: await grantTo("NODE_TECH_EX_EDUCATION", 2) };
await settle();
expect("Antiquity world: Chart the Stars can be started", canStart("PROJECT_CHART_THE_STARS"), depths);
expect("Antiquity world: a leading civ can start Heliocentric Model (an Exploration achievement)", canStart("PROJECT_HELIOCENTRIC_MODEL"), depths);
await complete("PROJECT_CHART_THE_STARS");
await complete("PROJECT_HELIOCENTRIC_MODEL");
expect("after completion, neither can be started again", !canStart("PROJECT_CHART_THE_STARS") && !canStart("PROJECT_HELIOCENTRIC_MODEL"),
  { tags: { chart: tagPoints("PROJECT_CHART_THE_STARS"), helio: tagPoints("PROJECT_HELIOCENTRIC_MODEL") } });
// To the last turn of the age (a build with --age-points 8). Autoplay must not run into the age end.
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
for (let i = 0; i < 30 && left() > 3; i++) await caLive.advance(1);
for (let i = 0; i < 12 && left() > 0; i++) {
  try { await caLive.endTurn(60000); } catch (e) { if (left() >= 2) await caLive.advance(1); }
}
expect("the age is at its end", left() <= 0, { turn: Game.turn, left: left() });
// The next end of turn ends the age, and the automation game makes the transition itself. The timer stops with the page.
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);
return { ok: checks.every((c) => c.ok), checks, transition: { auto: true } };

//// PHASE 2: the Exploration world
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => {
  checks.push({ name, ok, detail });
  caLive.log({ scenario: "project_achievements", phase: 2, name, ok, detail });
};
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const canStart = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
async function grantTo(node, depth) {
  const hash = GameInfo.ProgressionTreeNodes.lookup(node)?.$hash;
  const now = () => Game.ProgressionTrees.getNode(me, hash)?.depthUnlocked ?? 0;
  for (let i = 0; i < 4 && now() < depth; i++) {
    const before = now();
    caLive.grantNode(node, me, 1);
    for (let j = 0; j < 10 && now() === before; j++) await settle(500);
  }
  return now();
}
const triggered = (l) => { try { return !!Players.get(me).Legacies?.isTriggered(l); } catch (e) { return `error ${e}`; } };
const tagPoints = (p) => { try { return Players.get(me).Identity?.getNarrativeTagPoints?.(Database.makeHash(`NARRATIVE_TAG_CA_ONCE_${p.slice(8)}`)); } catch (e) { return `error ${e}`; } };
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
expect("the world is Exploration and slot 0 is human", world === "AGE_EXPLORATION" && Players.get(me).isHuman, { world, turn: Game.turn });
const depths = { math: await grantTo("NODE_TECH_AQ_MATHEMATICS", 1), up: await grantTo("NODE_TECH_EX_URBAN_PLANNING", 2),
  nav: await grantTo("NODE_TECH_AQ_NAVIGATION", 1), edu: await grantTo("NODE_TECH_EX_EDUCATION", 2) };
await settle();
const tags = { chart: tagPoints("PROJECT_CHART_THE_STARS"), helio: tagPoints("PROJECT_HELIOCENTRIC_MODEL") };
expect("test: Chart the Stars (built in the Antiquity world) cannot be started again", !canStart("PROJECT_CHART_THE_STARS"), { tags, depths });
expect("test: Heliocentric Model (built early) cannot be started again", !canStart("PROJECT_HELIOCENTRIC_MODEL"), { tags, depths });
expect("control: Spherical Earth (never built) can be started in the later world", canStart("PROJECT_SPHERICAL_EARTH"), depths);
expect("control: Invent Calculus can be started", canStart("PROJECT_INVENT_CALCULUS"), depths);
const before = { ex2: triggered("LEGACY_EX_SCIENTIFIC_2"), ex2race: triggered("LEGACY_EX_SCIENTIFIC_2_RACE") };
Game.CityOperations.sendRequest(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash("PROJECT_INVENT_CALCULUS"), InsertMode: CityOperationsParametersValues.Exclusive });
await settle();
cap().BuildQueue.completeProduction();
await settle(3000);
let after = { ex2: triggered("LEGACY_EX_SCIENTIFIC_2"), ex2race: triggered("LEGACY_EX_SCIENTIFIC_2_RACE") };
for (let i = 0; i < 2 && after.ex2 !== true; i++) {
  await caLive.endTurn();
  await settle(3000);
  after = { ex2: triggered("LEGACY_EX_SCIENTIFIC_2"), ex2race: triggered("LEGACY_EX_SCIENTIFIC_2_RACE") };
}
expect("test: the Exploration science triumph triggers (Heliocentric Model counts through its tag)", after.ex2 === true,
  { before, after, turn: Game.turn, calculusTag: tagPoints("PROJECT_INVENT_CALCULUS") });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
