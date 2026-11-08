// Scenario test of rules 2l and 2k through two world transitions and a load (build: build_mod.py --install --checks
// --age-points 8; suite: ContinuousAgesLive.json). Slot 0 is a leading civ (its Breakthroughs are granted).
// Rule 2l: achievement projects are built at the civ's own age in any world, once per game (a narrative tag), and the
// triumphs of their age read the tag. Rule 2k: final projects only in their own world age.
// Break the Sound Barrier is final (its Modern science triumph has one winner): blocked in the Exploration world, built
// in the Modern world with the base game's triumph; Trans-Oceanic Flight is the Modern achievement under test.
// Checks that must pass without the rules too (controls): no project before its tech; each project can be started once
// its tech is done; the rewritten Antiquity triumph triggers in its own world; final projects in their own world.
// Checks that fail without the rules (--disable-rule achieve --disable-rule worldproj): the tags, the projects blocked
// in later worlds, the triumphs at world start, the final project blocked outside its world.
// Phase 3's save CA_TAGTEST_EX is read by project_tags_load.js in a new game process (suite ContinuousAgesLiveLoad.json).
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "project_achievements", phase: 1, name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const can = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
const tag = (p) => { try { return Players.get(me).Identity.getNarrativeTagPoints(Database.makeHash(`NARRATIVE_TAG_CA_ONCE_${p.slice(8)}`)); } catch (e) { return `error ${e}`; } };
const triggered = (l) => { try { return Players.get(me).Legacies.isTriggered(l) === true; } catch (e) { return `error ${e}`; } };
async function grantTo(node, depth) {  // each debug grant adds one depth
  const hash = GameInfo.ProgressionTreeNodes.lookup(node)?.$hash;
  const now = () => Game.ProgressionTrees.getNode(me, hash)?.depthUnlocked ?? 0;
  for (let i = 0; i < 4 && now() < depth; i++) { const b = now(); caLive.grantNode(node, me, 1); for (let j = 0; j < 10 && now() === b; j++) await settle(500); }
  return now();
}
async function complete(p) {
  Game.CityOperations.sendRequest(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p), InsertMode: CityOperationsParametersValues.Exclusive });
  await settle();
  cap().BuildQueue.completeProduction();
  await settle(3000);
}
const AQ = ["PROJECT_CHART_THE_STARS", "PROJECT_SPHERICAL_EARTH"], EX = ["PROJECT_HELIOCENTRIC_MODEL", "PROJECT_INVENT_CALCULUS"];
const FOUR = [...AQ, ...EX];
const state = () => Object.fromEntries(FOUR.map((p) => [p.slice(8), { can: can(p), tag: tag(p) }]));
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
expect("control: before their techs, no achievement project can be started", FOUR.every((p) => !can(p)), state());
const depths = { gate: await grantTo("NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", 1), nav: await grantTo("NODE_TECH_AQ_NAVIGATION", 1),
  math: await grantTo("NODE_TECH_AQ_MATHEMATICS", 1), edu: await grantTo("NODE_TECH_EX_EDUCATION", 2), up: await grantTo("NODE_TECH_EX_URBAN_PLANNING", 2) };
await settle();
expect("control: with their techs, the 2 Antiquity and 2 Exploration achievements can be started (a leading civ)", FOUR.every(can), { depths, state: state() });
for (const p of AQ) await complete(p);
for (let i = 0; i < 2 && triggered("LEGACY_AQ_SCIENTIFIC_1") !== true; i++) await caLive.endTurn();
expect("control: the Antiquity science triumph triggers in its own world (the rewritten set works as before)",
  triggered("LEGACY_AQ_SCIENTIFIC_1") === true, { turn: Game.turn });
for (const p of EX) await complete(p);
const s1 = state();
expect("after completion, none can be started again (same world)", FOUR.every((p) => !s1[p.slice(8)].can), s1);
expect("test: each completed achievement left its tag", FOUR.every((p) => s1[p.slice(8)].tag === 1), s1);
// Save, then load it in this game process (the next phase runs in the loaded game).
const params = { Location: SaveLocations.LOCAL_STORAGE, LocationCategories: SaveLocationCategories.NORMAL,
  Type: GameStateStorage.getGameConfigurationSaveType(), ContentType: SaveFileTypes.GAME_STATE, FileName: "CA_TAGTEST_AQ" };
const saved = Network.saveGame({ ...params, Overwrite: true });
await settle(6000);
expect("the game saved (CA_TAGTEST_AQ)", saved !== false, { saved, turn: Game.turn });
globalThis.caAwaitReload = true;
setTimeout(() => Network.loadGame(params, ServerType.SERVER_TYPE_NONE), 1500);
return { ok: checks.every((c) => c.ok), checks, reload: true, savedTurn: Game.turn };

//// PHASE 2: the same Antiquity game, loaded from CA_TAGTEST_AQ
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "project_achievements", phase: 2, name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const can = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
const tag = (p) => { try { return Players.get(me).Identity.getNarrativeTagPoints(Database.makeHash(`NARRATIVE_TAG_CA_ONCE_${p.slice(8)}`)); } catch (e) { return `error ${e}`; } };
const triggered = (l) => { try { return Players.get(me).Legacies.isTriggered(l) === true; } catch (e) { return `error ${e}`; } };
const FOUR = ["PROJECT_CHART_THE_STARS", "PROJECT_SPHERICAL_EARTH", "PROJECT_HELIOCENTRIC_MODEL", "PROJECT_INVENT_CALCULUS"];
const state = () => Object.fromEntries(FOUR.map((p) => [p.slice(8), { can: can(p), tag: tag(p) }]));
const prev = globalThis.caPrev[0];
const s = state();
expect("the loaded game is the saved one (same turn, Antiquity)", Game.turn === prev.savedTurn && GameInfo.Ages.lookup(Game.age)?.AgeType === "AGE_ANTIQUITY",
  { turn: Game.turn, savedTurn: prev.savedTurn });
expect("test: after a load, the 4 tags are still there", FOUR.every((p) => s[p.slice(8)].tag === 1), s);
expect("after a load, none of the 4 can be started", FOUR.every((p) => !s[p.slice(8)].can), s);
expect("after a load, the Antiquity triumph is still earned", triggered("LEGACY_AQ_SCIENTIFIC_1") === true);
// To the last turn of the age; autoplay must not run into the age end.
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
for (let i = 0; i < 30 && left() > 3; i++) await caLive.advance(1);
for (let i = 0; i < 12 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { if (left() >= 2) await caLive.advance(1); } }
expect("the age is at its end", left() <= 0, { turn: Game.turn, left: left() });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((c) => c.ok), checks, transition: { auto: true } };

//// PHASE 3: the Exploration world
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "project_achievements", phase: 3, name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const can = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
const tag = (p) => { try { return Players.get(me).Identity.getNarrativeTagPoints(Database.makeHash(`NARRATIVE_TAG_CA_ONCE_${p.slice(8)}`)); } catch (e) { return `error ${e}`; } };
const triggered = (l) => { try { return Players.get(me).Legacies.isTriggered(l) === true; } catch (e) { return `error ${e}`; } };
async function grantTo(node, depth) {
  const hash = GameInfo.ProgressionTreeNodes.lookup(node)?.$hash;
  const now = () => Game.ProgressionTrees.getNode(me, hash)?.depthUnlocked ?? 0;
  for (let i = 0; i < 4 && now() < depth; i++) { const b = now(); caLive.grantNode(node, me, 1); for (let j = 0; j < 10 && now() === b; j++) await settle(500); }
  return now();
}
async function complete(p) {
  Game.CityOperations.sendRequest(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p), InsertMode: CityOperationsParametersValues.Exclusive });
  await settle();
  cap().BuildQueue.completeProduction();
  await settle(3000);
}
const consAt = (x, y) => (MapConstructibles.getConstructibles(x, y) ?? []).map((id) => GameInfo.Constructibles.lookup(Constructibles.getByComponentID(id)?.type)?.ConstructibleType);
const hasBuilding = (b) => GameplayMap.getPlotIndicesInRadius(cap().location.x, cap().location.y, 3).some((i) => { const l = GameplayMap.getLocationFromIndex(i); return consAt(l.x, l.y).includes(b); });
async function place(b) {  // debug CREATE_ELEMENT: the city centre, then the capital's other urban plots
  if (hasBuilding(b)) return true;
  const plots = [cap().location, ...GameplayMap.getPlotIndicesInRadius(cap().location.x, cap().location.y, 2).map((i) => GameplayMap.getLocationFromIndex(i))
    .filter((l) => GameplayMap.getOwner(l.x, l.y) === me && MapCities.getDistrict(l.x, l.y) != null)];
  for (const l of plots) {
    Game.PlayerOperations.sendRequest(me, "CREATE_ELEMENT", { Kind: "CONSTRUCTIBLE", Type: b, Location: { x: l.x, y: l.y }, Owner: me });
    await settle(1500);
    if (hasBuilding(b)) return true;
  }
  return false;
}
const FOUR = ["PROJECT_CHART_THE_STARS", "PROJECT_SPHERICAL_EARTH", "PROJECT_HELIOCENTRIC_MODEL", "PROJECT_INVENT_CALCULUS"];
const state = () => Object.fromEntries(FOUR.map((p) => [p.slice(8), { can: can(p), tag: tag(p) }]));
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
expect("the world is Exploration and slot 0 is human", world === "AGE_EXPLORATION" && Players.get(me).isHuman, { world, turn: Game.turn });
// The triumph at world start: both projects were built in the Antiquity world; nothing is completed here before this check.
const t0 = { turn: Game.turn, ex2: triggered("LEGACY_EX_SCIENTIFIC_2"), race: triggered("LEGACY_EX_SCIENTIFIC_2_RACE") };
for (let i = 0; i < 2 && triggered("LEGACY_EX_SCIENTIFIC_2") !== true; i++) await caLive.endTurn();
const t1 = { turn: Game.turn, ex2: triggered("LEGACY_EX_SCIENTIFIC_2"), race: triggered("LEGACY_EX_SCIENTIFIC_2_RACE") };
expect("test: the Exploration science triumph triggers at world start (both projects built in the Antiquity world)", t1.ex2 === true, { t0, t1 });
const s = state();
expect("test: after the transition, the 4 tags are still there", FOUR.every((p) => s[p.slice(8)].tag === 1), s);
expect("test: after the transition, none of the 4 can be started again", FOUR.every((p) => !s[p.slice(8)].can), s);
// Modern projects in the Exploration world (a civ past its Modern Breakthrough). They need a building, placed by debug.
const wp = globalThis.caWorldProjects ?? {};
const nodeOf = (p) => wp[p] ? [wp[p].node, wp[p].depth] : null;
await grantTo("NODE_TECH_CA_MODERN_BREAKTHROUGH", 1);
for (const p of ["PROJECT_LAUNCH_SATELLITE", "PROJECT_CREWED_SPACE_FLIGHT_PREP", "PROJECT_BREAK_SOUND_BARRIER", "PROJECT_TRANS_OCEANIC_FLIGHT"]) {
  const n = nodeOf(p); if (n?.[0]) await grantTo(n[0], n[1]);
}
const pad = await place("BUILDING_LAUNCH_PAD"), air = await place("BUILDING_AIRFIELD");
await settle();
const modern = { pad, air, satellite: can("PROJECT_LAUNCH_SATELLITE"), prep: can("PROJECT_CREWED_SPACE_FLIGHT_PREP"), sound: can("PROJECT_BREAK_SOUND_BARRIER"),
  flight: can("PROJECT_TRANS_OCEANIC_FLIGHT"),
  groups: { satellite: wp.PROJECT_LAUNCH_SATELLITE?.final, prep: wp.PROJECT_CREWED_SPACE_FLIGHT_PREP?.final, sound: wp.PROJECT_BREAK_SOUND_BARRIER?.final,
    flight: wp.PROJECT_TRANS_OCEANIC_FLIGHT?.final } };
if (pad) {
  expect("Modern achievement in the Exploration world: Launch Satellite can be started (Launch Pad placed)", modern.satellite === true, modern);
  expect("test: final project outside its world: Crewed Space Flight Prep cannot be started (rule 2k, repeatable)", modern.prep === false, modern);
} else expect("a Launch Pad was placed (without it the Modern achievement and the final project are not tested: FAIL, not a skip)", false, modern);
if (air) {
  // Break the Sound Barrier is final: its Modern science triumph has one winner (option A of 2026-11-07).
  expect("test: final project outside its world: Break the Sound Barrier cannot be started (rule 2k, one-winner triumph)", modern.sound === false, modern);
  expect("Modern achievement in the Exploration world: Trans-Oceanic Flight can be started (Airfield placed)", modern.flight === true, modern);
  await complete("PROJECT_TRANS_OCEANIC_FLIGHT");
  expect("Trans-Oceanic Flight completed: its tag is there and it cannot be started again",
    tag("PROJECT_TRANS_OCEANIC_FLIGHT") === 1 && !can("PROJECT_TRANS_OCEANIC_FLIGHT"), { tag: tag("PROJECT_TRANS_OCEANIC_FLIGHT") });
} else expect("an Airfield was placed (without it Trans-Oceanic Flight and Break the Sound Barrier are not tested: FAIL, not a skip)", false, modern);
// A save for the test in a new game process (project_tags_load.js).
const saved = Network.saveGame({ Location: SaveLocations.LOCAL_STORAGE, LocationCategories: SaveLocationCategories.NORMAL,
  Type: GameStateStorage.getGameConfigurationSaveType(), ContentType: SaveFileTypes.GAME_STATE, FileName: "CA_TAGTEST_EX", Overwrite: true });
await settle(6000);
expect("the game saved (CA_TAGTEST_EX)", saved !== false, { saved, turn: Game.turn });
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
for (let i = 0; i < 30 && left() > 3; i++) await caLive.advance(1);
for (let i = 0; i < 12 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { if (left() >= 2) await caLive.advance(1); } }
expect("the age is at its end", left() <= 0, { turn: Game.turn, left: left() });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);
return { ok: checks.every((c) => c.ok), checks, transition: { auto: true }, modern: { pad, air } };

//// PHASE 4: the Modern world
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "project_achievements", phase: 4, name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const can = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
const tag = (p) => { try { return Players.get(me).Identity.getNarrativeTagPoints(Database.makeHash(`NARRATIVE_TAG_CA_ONCE_${p.slice(8)}`)); } catch (e) { return `error ${e}`; } };
const triggered = (l) => { try { return Players.get(me).Legacies.isTriggered(l) === true; } catch (e) { return `error ${e}`; } };
const FOUR = ["PROJECT_CHART_THE_STARS", "PROJECT_SPHERICAL_EARTH", "PROJECT_HELIOCENTRIC_MODEL", "PROJECT_INVENT_CALCULUS"];
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const modern = globalThis.caPrev.filter((v) => v?.modern).pop()?.modern ?? {};
// caLive.endTurn returned at once in the Modern world of a test (its ageEnded flag): wait for the turn number itself.
async function nextTurn() {
  const t = Game.turn, t0 = Date.now();
  while (Game.turn === t && Date.now() - t0 < 90000) { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); await settle(3000); }
  return Game.turn;
}
const consAt = (x, y) => (MapConstructibles.getConstructibles(x, y) ?? []).map((id) => GameInfo.Constructibles.lookup(Constructibles.getByComponentID(id)?.type)?.ConstructibleType);
const hasBuilding = (b) => GameplayMap.getPlotIndicesInRadius(cap().location.x, cap().location.y, 3).some((i) => { const l = GameplayMap.getLocationFromIndex(i); return consAt(l.x, l.y).includes(b); });
const why = (p) => { const r = Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false); return { ok: !!r?.Success, reasons: r?.FailureReasons ?? null }; };
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? null;
const diag = () => ({ turn: Game.turn, capital: { name: cap()?.name, x: cap()?.location.x, y: cap()?.location.y, cities: Players.get(me).Cities.getCityIds().length },
  pad: hasBuilding("BUILDING_LAUNCH_PAD"), air: hasBuilding("BUILDING_AIRFIELD"), rocketry: depth("NODE_TECH_MO_ROCKETRY"), flight: depth("NODE_TECH_MO_FLIGHT"),
  prep: why("PROJECT_CREWED_SPACE_FLIGHT_PREP"), satellite: why("PROJECT_LAUNCH_SATELLITE"), sound: why("PROJECT_BREAK_SOUND_BARRIER") });
caLive.log({ scenario: "project_achievements", phase: 4, diag: diag() });
expect("the world is Modern and slot 0 is human", world === "AGE_MODERN" && Players.get(me).isHuman, { world, turn: Game.turn });
const s = Object.fromEntries(FOUR.map((p) => [p.slice(8), { can: can(p), tag: tag(p) }]));
expect("test: after two transitions, the 4 tags are still there", FOUR.every((p) => s[p.slice(8)].tag === 1), s);
expect("test: after two transitions, none of the 4 can be started again", FOUR.every((p) => !s[p.slice(8)].can), s);
if (modern.air) {
  // A Modern achievement through the transition to its own world.
  expect("test: Trans-Oceanic Flight (built in the Exploration world) keeps its tag and cannot be started in its own world",
    tag("PROJECT_TRANS_OCEANIC_FLIGHT") === 1 && !can("PROJECT_TRANS_OCEANIC_FLIGHT"), { tag: tag("PROJECT_TRANS_OCEANIC_FLIGHT"), d: diag() });
  // Break the Sound Barrier is final (its Modern science triumph has one winner): base-game behavior in its own world.
  const before = { mo2: triggered("LEGACY_MO_SCIENTIFIC_2"), can: can("PROJECT_BREAK_SOUND_BARRIER") };
  expect("control: the final project Break the Sound Barrier can be started in its own world", before.can === true, { before, d: diag() });
  expect("control: the Modern science triumph is not earned before Break the Sound Barrier is built", before.mo2 === false, before);
  if (before.can) {
    Game.CityOperations.sendRequest(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash("PROJECT_BREAK_SOUND_BARRIER"), InsertMode: CityOperationsParametersValues.Exclusive });
    await settle();
    cap().BuildQueue.completeProduction();
    await settle(3000);
    for (let i = 0; i < 2 && triggered("LEGACY_MO_SCIENTIFIC_2") !== true; i++) await nextTurn();
  }
  expect("control: Break the Sound Barrier built in its own world earns the Modern science triumph (the base game's rule)",
    triggered("LEGACY_MO_SCIENTIFIC_2") === true, { turn: Game.turn });
  expect("Break the Sound Barrier is not an achievement: it leaves no tag", tag("PROJECT_BREAK_SOUND_BARRIER") === 0, { tag: tag("PROJECT_BREAK_SOUND_BARRIER") });
}
if (modern.pad) {
  const d = diag();
  expect("control: the final project Crewed Space Flight Prep can be started in its own world", can("PROJECT_CREWED_SPACE_FLIGHT_PREP"), d);
  expect("control: Launch Satellite (never built) can be started", can("PROJECT_LAUNCH_SATELLITE"), d);
}
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
