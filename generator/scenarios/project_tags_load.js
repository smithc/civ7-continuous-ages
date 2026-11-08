// Scenario test of rule 2l's record in a new game process (suite: ContinuousAgesLiveLoad.json, which loads the save
// CA_TAGTEST_EX that project_achievements.js wrote in phase 3; same build as that run).
//   test: the tags of the 4 achievements built in the Antiquity world and of Trans-Oceanic Flight (built in phase 3) are
//         in the loaded game, and none of these projects can be started
//   test: the final project Break the Sound Barrier stays blocked in the loaded Exploration game (rule 2k)
//   test: the Exploration science triumph (earned from the tags at world start in phase 3) is in the loaded game
//   control: the loaded game is the Exploration world
const me = GameContext.localPlayerID;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "project_tags_load", name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const can = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
const tag = (p) => { try { return Players.get(me).Identity.getNarrativeTagPoints(Database.makeHash(`NARRATIVE_TAG_CA_ONCE_${p.slice(8)}`)); } catch (e) { return `error ${e}`; } };
const triggered = (l) => { try { return Players.get(me).Legacies.isTriggered(l) === true; } catch (e) { return `error ${e}`; } };
const FOUR = ["PROJECT_CHART_THE_STARS", "PROJECT_SPHERICAL_EARTH", "PROJECT_HELIOCENTRIC_MODEL", "PROJECT_INVENT_CALCULUS"];
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
expect("control: the loaded game is the Exploration world, slot 0 human", world === "AGE_EXPLORATION" && Players.get(me).isHuman, { world, turn: Game.turn });
expect("test: the Exploration science triumph (earned from the tags at world start) is in the loaded game", triggered("LEGACY_EX_SCIENTIFIC_2") === true);
const s = Object.fromEntries(FOUR.map((p) => [p.slice(8), { can: can(p), tag: tag(p) }]));
expect("test: in a new game process, the 4 tags are there", FOUR.every((p) => s[p.slice(8)].tag === 1), s);
expect("test: in a new game process, none of the 4 can be started", FOUR.every((p) => !s[p.slice(8)].can), s);
const flight = { tag: tag("PROJECT_TRANS_OCEANIC_FLIGHT"), can: can("PROJECT_TRANS_OCEANIC_FLIGHT") };
expect("test: Trans-Oceanic Flight (built in the Exploration world) keeps its tag and stays blocked", flight.tag === 1 && !flight.can, flight);
expect("test: the final project Break the Sound Barrier stays blocked in the loaded Exploration game", !can("PROJECT_BREAK_SOUND_BARRIER"));
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
