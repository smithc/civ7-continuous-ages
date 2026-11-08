// Scenario test of a game updated from 0.4.0 during a world age (build: build_mod.py --install --checks --age-points 8;
// suite: ContinuousAgesLiveLoad.json --set SaveName=CA_UPD040_AQ). The save comes from make_save_040.js with the v0.4.0
// build: slot 0 completed Chart the Stars in the Antiquity world, with no tag (0.4.0 has none), and has no Mathematics.
// Engine fact (2026-11-07): a modifier row that a later version adds (TraitModifiers, GameModifiers) does not attach
// when an older save loads. Rule 2l's unlock is such a row, so in the loaded world no achievement project can be
// started (a known limit, checked here so that a change is seen). The rule's tables (RequiresUnlock) do apply.
// Phase 1 (the loaded Antiquity world): controls (the save, Chart the Stars blocked, no tag); the known limit; the
// techs for phase 2 are granted; the age is played to its end.
// Phase 2 (the Exploration world, after the transition): tests: the unlock attaches at the transition (Spherical Earth
// and Heliocentric Model can be started), and a completion leaves its tag; known limit: Chart the Stars (completed
// under 0.4.0, no tag) can be built once more.
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "update_040", phase: 1, name, ok, detail }); };
const P = () => Players.get(me);
const cap = () => P().Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const can = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
const tag = (p) => { try { return P().Identity.getNarrativeTagPoints(Database.makeHash(`NARRATIVE_TAG_CA_ONCE_${p.slice(8)}`)); } catch (e) { return `error ${e}`; } };
const triggered = (l) => { try { return P().Legacies.isTriggered(l) === true; } catch (e) { return `error ${e}`; } };
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
async function grantTo(node, d) {  // each debug grant adds one depth
  for (let i = 0; i < 4 && depth(node) < d; i++) { const b = depth(node); caLive.grantNode(node, me, 1); for (let j = 0; j < 10 && depth(node) === b; j++) await settle(500); }
  return depth(node);
}
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const s0 = { world, turn: Game.turn, human: P().isHuman, chart: can("PROJECT_CHART_THE_STARS"), chartTag: tag("PROJECT_CHART_THE_STARS"),
  math: depth("NODE_TECH_AQ_MATHEMATICS"), rule: !!GameInfo.Modifiers.lookup("CA_ONCE_UNLOCK_SPHERICAL_EARTH") };
expect("control: the 0.4.0 save loaded with this build (Antiquity, slot 0 human, rule 2l's modifiers in the database)",
  world === "AGE_ANTIQUITY" && s0.human && s0.rule, s0);
expect("control: Chart the Stars (completed under 0.4.0) cannot be started and has no tag", s0.chart === false && s0.chartTag === 0 && s0.math === 0, s0);
// The Exploration techs are granted in this world: a node granted by debug in an earlier world did not unlock its items
// after a transition in a test (religion_modern.js), but projects are unlocked by the rule's modifier, which reads the depth.
const g = { math: await grantTo("NODE_TECH_AQ_MATHEMATICS", 1), gate: await grantTo("NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", 1),
  edu: await grantTo("NODE_TECH_EX_EDUCATION", 2) };
await settle();
const s1 = { ...g, sph: can("PROJECT_SPHERICAL_EARTH"), helio: can("PROJECT_HELIOCENTRIC_MODEL") };
expect("known limit (update during a world age): the rule's unlock did not attach in the loaded world, no achievement can be started",
  s1.math === 1 && s1.edu === 2 && s1.sph === false && s1.helio === false, s1);
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
for (let i = 0; i < 30 && left() > 3; i++) await caLive.advance(1);
for (let i = 0; i < 12 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { if (left() >= 2) await caLive.advance(1); } }
expect("the age is at its end", left() <= 0, { turn: Game.turn, left: left(), max: m.getMaxAgeProgressionPoints() });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((c) => c.ok), checks, transition: { auto: true } };

//// PHASE 2: the Exploration world
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "update_040", phase: 2, name, ok, detail }); };
const P = () => Players.get(me);
const cap = () => P().Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const can = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
const tag = (p) => { try { return P().Identity.getNarrativeTagPoints(Database.makeHash(`NARRATIVE_TAG_CA_ONCE_${p.slice(8)}`)); } catch (e) { return `error ${e}`; } };
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
expect("the world is Exploration and slot 0 is human", world === "AGE_EXPLORATION" && P().isHuman, { world, turn: Game.turn });
const t = Game.turn, t0 = Date.now();
while (Game.turn === t && Date.now() - t0 < 90000) { if (P()?.isTurnActive) GameContext.sendTurnComplete(); await settle(3000); }
await settle(3000);
const s = { turn: Game.turn, math: depth("NODE_TECH_AQ_MATHEMATICS"), edu: depth("NODE_TECH_EX_EDUCATION"), nav: depth("NODE_TECH_AQ_NAVIGATION"),
  sph: can("PROJECT_SPHERICAL_EARTH"), helio: can("PROJECT_HELIOCENTRIC_MODEL"), chart: can("PROJECT_CHART_THE_STARS"), chartTag: tag("PROJECT_CHART_THE_STARS") };
expect("test: after the transition the rule's unlock works: Spherical Earth and Heliocentric Model can be started", s.sph && s.helio, s);
expect("known limit (0.4.0 completions have no tag): Chart the Stars can be built once more", s.chart === true && s.chartTag === 0, s);
if (s.helio) {
  Game.CityOperations.sendRequest(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash("PROJECT_HELIOCENTRIC_MODEL"), InsertMode: CityOperationsParametersValues.Exclusive });
  await settle();
  cap().BuildQueue.completeProduction();
  await settle(3000);
}
const d = { helio: can("PROJECT_HELIOCENTRIC_MODEL"), helioTag: tag("PROJECT_HELIOCENTRIC_MODEL") };
expect("test: Heliocentric Model completed in the updated game: its tag is there and it cannot be started again", d.helioTag === 1 && d.helio === false, d);
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
