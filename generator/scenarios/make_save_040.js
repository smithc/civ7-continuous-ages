// Makes the save CA_UPD040_AQ for update_040.js (manual: run it with the v0.4.0 test build installed, suite
// ContinuousAgesLive.json; see docs/testing.md). Slot 0 completes Chart the Stars in the Antiquity world under 0.4.0
// (no tag: 0.4.0 has none), and Mathematics stays unresearched, so that Spherical Earth is still to come after the update.
const me = GameContext.localPlayerID;
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "make_save_040", name, ok, detail }); };
const cap = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const can = (p) => !!Game.CityOperations.canStart(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash(p) }, false)?.Success;
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
caLive.grantNode("NODE_TECH_AQ_NAVIGATION", me, 1);
for (let i = 0; i < 10 && depth("NODE_TECH_AQ_NAVIGATION") < 1; i++) await settle(500);
await settle();
const s0 = { nav: depth("NODE_TECH_AQ_NAVIGATION"), math: depth("NODE_TECH_AQ_MATHEMATICS"), chart: can("PROJECT_CHART_THE_STARS"), turn: Game.turn,
  version: Modding.getInstalledMods?.().find?.((m) => /continuous/i.test(m.id ?? ""))?.version ?? null };
expect("setup: Navigation, no Mathematics, Chart the Stars can be started", s0.nav >= 1 && s0.math === 0 && s0.chart, s0);
Game.CityOperations.sendRequest(cap().id, CityOperationTypes.BUILD, { ProjectType: Database.makeHash("PROJECT_CHART_THE_STARS"), InsertMode: CityOperationsParametersValues.Exclusive });
await settle();
cap().BuildQueue.completeProduction();
await settle(3000);
await caLive.endTurn();
await settle(3000);
const s1 = { chart: can("PROJECT_CHART_THE_STARS"), turn: Game.turn };
expect("Chart the Stars completed: it cannot be started again", s1.chart === false, s1);
const params = { Location: SaveLocations.LOCAL_STORAGE, LocationCategories: SaveLocationCategories.NORMAL,
  Type: GameStateStorage.getGameConfigurationSaveType(), ContentType: SaveFileTypes.GAME_STATE, FileName: "CA_UPD040_AQ" };
const saved = Network.saveGame({ ...params, Overwrite: true });
await settle(6000);
expect("the game saved (CA_UPD040_AQ)", saved !== false, { saved, turn: Game.turn });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
