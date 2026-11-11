// Makes the save CA_UPD051_AQ for update_051.js (manual: run it with a build that has the rules of 0.5.1, that is
// build_mod.py --install --checks --age-points 12 --fast-test 0.01 --disable-rule mastery, or the v0.5.1 test build; suite
// ContinuousAgesLive.json --set GameSpeed=GAMESPEED_MARATHON; see docs/testing.md). Slot 0 is past its Exploration
// Breakthrough and has Currency at depth 1 by normal research, so the original modifier MOD_AQ_SPECIALIST_CAP_INCREASE
// is attached under the old rules. Shipbuilding stays unresearched: update_051.js researches it after the update.
const me = GameContext.localPlayerID;
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", CURRENCY = "NODE_TECH_AQ_CURRENCY", SHIPBUILDING = "NODE_TECH_EX_SHIPBUILDING";
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "make_save_051", name, ok, detail }); };
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const capital = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const worker = () => capital()?.Workers?.getCityWorkerCap() ?? -1;
const active = () => new Set(Players.get(me).Modifiers.getModifiers().map((m) => GameEffects.getModifierDefinitionFromTypeId(m.modifierType)?.ID));
async function grant(node) { caLive.grantNode(node); for (let i = 0; i < 10 && depth(node) < 1; i++) await settle(500); return depth(node) >= 1; }
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
await grant(GATE);
const w0 = worker();
for (const r of Array.from(GameInfo.ProgressionTreePrereqs).filter((p) => p.Node === CURRENCY)) if (depth(r.PrereqNode) < 1) await grant(r.PrereqNode);
const args = { ProgressionTreeNodeType: GameInfo.ProgressionTreeNodes.lookup(CURRENCY).$hash };
const can = !!Game.PlayerOperations.canStart(me, PlayerOperationTypes.SET_TECH_TREE_NODE, args, false)?.Success;
if (can) Game.PlayerOperations.sendRequest(me, PlayerOperationTypes.SET_TECH_TREE_NODE, args);
await settle();
let turns = 0;
for (; turns < 10 && depth(CURRENCY) < 1; turns++) await caLive.endTurn();
const s = { gate: depth(GATE), currency: depth(CURRENCY), shipbuilding: depth(SHIPBUILDING), w0, w1: worker(), can, turns, turn: Game.turn,
  original: active().has("MOD_AQ_SPECIALIST_CAP_INCREASE"), ruleRows: ((globalThis.caMasterySplit ?? {}).AGE_ANTIQUITY ?? []).filter((e) => e.high).length };
expect("setup: the old rules (no kept rows); the gate; Currency researched to depth 1 with its original modifier and +1 specialist cap; no Shipbuilding",
  s.ruleRows === 0 && s.gate === 1 && s.currency === 1 && s.shipbuilding === 0 && s.w1 === s.w0 + 1 && s.original, s);
const saved = Network.saveGame({ Location: SaveLocations.LOCAL_STORAGE, LocationCategories: SaveLocationCategories.NORMAL,
  Type: GameStateStorage.getGameConfigurationSaveType(), ContentType: SaveFileTypes.GAME_STATE, FileName: "CA_UPD051_AQ", Overwrite: true });
await settle(6000);
expect("the game saved (CA_UPD051_AQ)", saved !== false, { saved, turn: Game.turn });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks, worker: s.w1 };
