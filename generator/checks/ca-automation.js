// Continuous Ages automation test "CAPlayAges": Firaxis PlayGame, but when the age ends it
// starts the age transition and keeps playing, instead of ending the test.
// Loaded by the autoplay suite (autoplay/ContinuousAgesTransition.json) from the mod folder.
import { AutomationBasePlayGame } from '../../base-standard/ui/automation/automation-base-play-game.js';
import { Shared_OnAutomationEvent } from '../../base-standard/ui/automation/automation-test-support.js';

// Civic trees the player has (a tree a player does not have shows its nodes as not unlocked),
// and the traditions and policies unlocked (the effect of civics, kept across ages in the base game).
// Snowball measures: settlement cap, population, buildings, science and culture per turn.
// Constructible types in the civ's settlements, logged in chunks (UI.log cuts long lines).
function logConstructibles(kind, player, extra) {
  const types = [];
  for (const id of player.Cities?.getCityIds() ?? []) {
    for (const cid of Cities.get(id)?.Constructibles?.getIds() ?? []) {
      const c = Constructibles.getByComponentID(cid);
      const t = c ? GameInfo.Constructibles.lookup(c.type)?.ConstructibleType : null;
      if (t) types.push(t.replace(/^(BUILDING|IMPROVEMENT|WONDER)_/, ""));
    }
  }
  types.sort();
  for (let i = 0; i < types.length; i += 30) {
    console.warn(`[CA-CHECK][${kind}] ${JSON.stringify({ ...extra, id: player.id, part: i / 30, types: types.slice(i, i + 30) })}`);
  }
}
function logChunks(kind, extra, key, list) {
  for (let i = 0; i === 0 || i < list.length; i += 30) {
    console.warn(`[CA-CHECK][${kind}] ${JSON.stringify({ ...extra, part: i / 30, [key]: list.slice(i, i + 30) })}`);
  }
}
function unitTypes(player) {
  return (player.Units?.getUnitIds() ?? []).map((uid) => (GameInfo.Units.lookup(Units.get(uid)?.type)?.UnitType ?? "?")
    .replace(/^UNIT_/, "")).sort();
}
function growthState(player) {
  const st = player.Stats;
  let buildings = 0;
  for (const id of player.Cities?.getCityIds() ?? []) buildings += (Cities.get(id)?.Constructibles?.getIds() ?? []).length;
  // Unit experience (U5): promotions and levels summed over the civ's units.
  let promotions = 0, levels = 0;
  for (const uid of player.Units?.getUnitIds() ?? []) {
    const xp = Units.get(uid)?.Experience;
    promotions += Number(xp?.getNumPromotions ?? 0);
    levels += Number(xp?.getLevel ?? 0);
  }
  return {
    promotions, levels,
    cap: st?.settlementCap ?? -1, pop: st?.totalPopulation ?? -1, buildings,
    sci: Math.round(st?.getNetYield(YieldTypes.YIELD_SCIENCE) ?? -1),
    cul: Math.round(st?.getNetYield(YieldTypes.YIELD_CULTURE) ?? -1),
  };
}
// Policy names (POLICIES record): the policy count fell by one at the Antiquity transition.
function policyNames(player) {
  return (player.Culture?.getUnlockedTraditions(CultureSlotTypes.POLICY_CULTURE_SLOT) ?? [])
    .map((t) => (GameInfo.Traditions.lookup(t)?.TraditionType ?? `${t}`).replace("TRADITION_", "")).sort();
}
function cultureState(player) {
  const c = player.Culture;
  const name = (t) => (GameInfo.ProgressionTrees.lookup(t)?.ProgressionTreeType ?? `${t}`).replace("TREE_CIVICS_", "");
  return {
    trees: (c?.getAvailableTrees() ?? []).map(name),
    traditions: (c?.getUnlockedTraditions(CultureSlotTypes.TRADITION_CULTURE_SLOT) ?? []).length,
    policies: (c?.getUnlockedTraditions(CultureSlotTypes.POLICY_CULTURE_SLOT) ?? []).length,
  };
}
// A node counts as done at depth 1 (the same rule as nodeDone in ca-checks.js; this module has its own copy).
function nodeDone(playerId, hash) {
  const S = ProgressionTreeNodeState;
  const s = Game.ProgressionTrees.getNodeState(playerId, hash);
  if (s >= S.NODE_STATE_FULLY_UNLOCKED || s === S.NODE_STATE_UNLOCKED) return true;
  return s === S.NODE_STATE_IN_PROGRESS && (Game.ProgressionTrees.getNode(playerId, hash)?.depthUnlocked ?? 0) >= 1;
}
function hasNode(playerId, type) {
  const hash = GameInfo.ProgressionTreeNodes.lookup(type)?.$hash;
  return hash !== undefined && nodeDone(playerId, hash);
}

// Camera auto-pan options (user options, in memory; the options screen saves them, this does not).
// Off by default in the test, to see if the camera pans add wait time; CAAutoPan=1 keeps them on.
const PAN_OPTIONS = ["NotificationCameraPan", "PlayerCombatCameraPan"];
let savedPanOptions = null;
function setPanOptions() {
  try {
    const keep = Automation.getParameter("CurrentTest", "CAAutoPan", 0);
    savedPanOptions ??= Object.fromEntries(PAN_OPTIONS.map((o) => [o, UI.getOption("user", "Interface", o)]));
    if (!keep) for (const o of PAN_OPTIONS) UI.setOption("user", "Interface", o, 0);
    const now = Object.fromEntries(PAN_OPTIONS.map((o) => [o, UI.getOption("user", "Interface", o)]));
    const transition = Configuration.getGame()?.getValue("AgeTransitionSettingName");
    console.warn(`[CA-CHECK][OPTIONS] ${JSON.stringify({ autoPan: keep ? "on" : "off", before: savedPanOptions, now, transition })}`);
  } catch (e) {
    console.warn(`[CA-CHECK][ERROR] pan options: ${e}`);
  }
}
function restorePanOptions() {
  try {
    for (const [o, v] of Object.entries(savedPanOptions ?? {})) UI.setOption("user", "Interface", o, v);
  } catch (e) {
    console.warn(`[CA-CHECK][ERROR] pan options restore: ${e}`);
  }
}

class AutomationTestCAPlayAges extends AutomationBasePlayGame {
  listener = (command, ...args) => {
    this.onAutomationEvent(command, args);
  };
  register() {
    engine.on("Automation-Test-CAPlayAges", this.listener);
  }
  onAutomationEvent(command, ...args) {
    Automation.log(`CAPlayAges: event ${command}`);
    Shared_OnAutomationEvent(args);
    if (command === "Run") {
      if (args !== null && args.length > 0 && args[0] == "Restart") {
        this.restart();
      } else {
        this.run();
      }
    } else if (command == "PostGameInitialization") {
      this.postGameInitialization(args);
    } else if (command == "GameStarted") {
      setPanOptions();
      this.gameStarted();
    } else if (command == "Stop") {
      restorePanOptions();
      this.stop();
    }
  }
  // Test parameter CATransitionSetting: the game's age transition setting (default: the game's,
  // AGE_TRANSITION_SETTING_KEEP_MORE). Set after PlayGame configures the game, before it hosts.
  run(serverType) {
    setPanOptions(); // also here: a resumed game (Resume=1 after LoadGame) sends no GameStarted to this test
    super.run(serverType);
    const setting = Automation.getParameter("CurrentTest", "CATransitionSetting");
    if (setting) {
      GameSetup.setGameParameterValue("AgeTransitionSetting", setting);
      Automation.log(`CAPlayAges: AgeTransitionSetting ${setting}`);
    }
    // Test parameter CACatchUp: the mod's Catch-up Research option (default: CA_CATCHUP_OFF).
    const catchUp = Automation.getParameter("CurrentTest", "CACatchUp");
    if (catchUp) {
      GameSetup.setGameParameterValue("CaCatchUp", catchUp);
      Automation.log(`CAPlayAges: CaCatchUp ${catchUp}`);
    }
    // Test parameter CACivMode: the AI civ choice mode at transitions (default: the game's, Mirroring).
    const civMode = Automation.getParameter("CurrentTest", "CACivMode");
    if (civMode) {
      GameSetup.setGameParameterValue("AgeTransitionCivSelectionMode", civMode);
      Automation.log(`CAPlayAges: AgeTransitionCivSelectionMode ${civMode}`);
    }
  }
  // PlayGame passes the test here. Continue into the next age instead.
  onGameAgeEndedListener() {
    const age = GameInfo.Ages.lookup(Game.age)?.AgeType;
    Automation.log(`CAPlayAges: age ended (${age}, turn ${Game.turn}); starting the transition`);
    console.warn(`[CA-CHECK][TRANSITION] {"turn":${Game.turn},"from":"${age}"}`);
    // State of every civ at the age end, to compare with the first turn of the next age.
    // A failed record must not stop the transition or the test end.
    for (const player of Players.getAlive()) {
      if (!player.isMajor) continue;
      try { this.logAgeEnd(age, player); }
      catch (e) { console.warn(`[CA-CHECK][ERROR] age end, player ${player.id}: ${e}`); }
    }
    // The last age has no next age: end the test as PlayGame does.
    if (age === "AGE_MODERN") {
      super.onGameAgeEndedListener();
      return;
    }
    // The mod's civ choice (ui/ca-civ-age.js) before the transition starts.
    if (globalThis.caTransitionCivs) globalThis.caTransitionCivs("automation");
    else console.warn("[CA-CHECK][ERROR] caTransitionCivs is not loaded");
    engine.call("transitionToNextAge");
  }
  logAgeEnd(age, player) {
    let techs = 0, civics = 0;
    const civicNodes = [];
    for (const node of GameInfo.ProgressionTreeNodes) {
      if (!nodeDone(player.id, node.$hash)) continue; // depth 1 counts
      const system = GameInfo.ProgressionTrees.lookup(node.ProgressionTree)?.SystemType;
      if (system === "SYSTEM_TECH") techs++;
      else if (system === "SYSTEM_CULTURE") { civics++; civicNodes.push(node.ProgressionTreeNodeType.replace("NODE_CIVIC_", "")); }
    }
    let cities = 0, towns = 0;
    for (const id of player.Cities?.getCityIds() ?? []) {
      if (Cities.get(id)?.isTown) towns++; else cities++;
    }
    const has = (t) => hasNode(player.id, t);
    const civAge = has("NODE_TECH_CA_MODERN_BREAKTHROUGH") ? "MO" : has("NODE_TECH_CA_EXPLORATION_BREAKTHROUGH") ? "EX" : "AQ";
    const civicAge = has("NODE_CIVIC_CA_MODERN_BREAKTHROUGH") ? "MO" : has("NODE_CIVIC_CA_EXPLORATION_BREAKTHROUGH") ? "EX" : "AQ";
    console.warn(`[CA-CHECK][AGEEND] ${JSON.stringify({
      age, turn: Game.turn, id: player.id, civAge, civicAge, gold: Math.round(player.Treasury?.goldBalance ?? -1), cities, towns,
      units: (player.Units?.getUnitIds() ?? []).length, techs, civics, ...cultureState(player), ...growthState(player) })}`);
    logChunks("CIVICS", { when: "end", age, id: player.id }, "nodes", civicNodes);
    logChunks("UNITS", { when: "end", age, id: player.id }, "types", unitTypes(player));
    logChunks("POLICIES", { when: "end", age, id: player.id }, "types", policyNames(player));
    logConstructibles("CONS", player, { when: "end", age });
  }
}

const handler = new AutomationTestCAPlayAges();
handler.register();
Automation.setScriptHasLoaded("ca-automation");
