// Continuous Ages: shows the local civ's own age (set by its Breakthrough techs) next to the world age.
// Each civ has its own age in this mod; the game's own UI shows only the world age.
const GATES = [
  ["NODE_TECH_CA_MODERN_BREAKTHROUGH", "AGE_MODERN"],
  ["NODE_TECH_CA_EXPLORATION_BREAKTHROUGH", "AGE_EXPLORATION"],
];

function ageName(ageType) {
  const age = GameInfo.Ages.lookup(ageType);
  return age ? Locale.compose(age.Name) : ageType;
}

function civAgeType(playerId) {
  for (const [node, age] of GATES) {
    const info = GameInfo.ProgressionTreeNodes.lookup(node);
    if (info && Game.ProgressionTrees.getNodeState(playerId, info.$hash) >= ProgressionTreeNodeState.NODE_STATE_FULLY_UNLOCKED) {
      return age;
    }
  }
  return "AGE_ANTIQUITY";
}

// The civ choice at a world transition is the game's: the AI follows the game option
// AgeTransitionCivSelectionMode (set at game creation; Mirroring by default, Persistence keeps every AI
// civ), and the human chooses on the transition screen (keeping the civ is a valid choice). Tests showed
// that the AI ignores the per-player value AgeTransitionPlayerCivilization; that with every other civ
// locked it still switches, to a locked civ or a civ of another age; and that GameSetup refuses a mode
// change during a game. This logs, at the age end, each civ's age against the next age's gate and the
// choices the game offers it, for the report (a civ behind the gate that takes a new civ: the half swap).
const AGE_RANK = { AGE_ANTIQUITY: 0, AGE_EXPLORATION: 1, AGE_MODERN: 2 };
const NEXT_AGE = { AGE_ANTIQUITY: "AGE_EXPLORATION", AGE_EXPLORATION: "AGE_MODERN" };
function caTransitionCivs(source) {
  const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
  const next = NEXT_AGE[world];
  if (!next) return;
  const mode = GameSetup.findGameParameter("AgeTransitionCivSelectionMode")?.value?.value?.toString() ?? null;
  console.warn(`[CA-CHECK][CIVMODE] ${JSON.stringify({ source, world, mode })}`);
  for (const player of Players.getAlive()) {
    if (!player.isMajor) continue;
    try {
      const own = civAgeType(player.id);
      const civ = GameInfo.Civilizations.lookup(player.civilizationType)?.CivilizationType;
      // The choices the game offers (invalidReason 0: unlocked for this civ; the civ itself is valid too).
      const values = GameSetup.findPlayerParameter(player.id, "AgeTransitionPlayerCivilization")?.domain?.possibleValues ?? [];
      const valid = values.filter((v) => (v.invalidReason ?? 0) == 0).map((v) => v.value?.toString())
        .filter((v) => v && v !== "RANDOM").map((v) => v.replace("CIVILIZATION_", ""));
      console.warn(`[CA-CHECK][CIVCHOICE] ${JSON.stringify({ source, world, next, id: player.id, human: player.isHuman,
        civ, own, behind: AGE_RANK[own] < AGE_RANK[next], valid })}`);
    } catch (e) {
      console.warn(`[CA-CHECK][ERROR] civ choice, player ${player.id}: ${e}`);
    }
  }
}
globalThis.caTransitionCivs = caTransitionCivs;

let banner = null;
let lastText = null;
function update() {
  try {
    const id = GameContext.localPlayerID;
    if (id == null || id < 0 || !Players.get(id)?.isMajor) {
      if (banner) banner.style.display = "none";
      if (lastText !== "hidden") console.warn(`[CA-CHECK][UI] civ age banner hidden (local player ${id})`);
      lastText = "hidden";
      return;
    }
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "ca-civ-age";
      banner.style.cssText = "position:absolute; top:0.4rem; left:50%; transform:translateX(-50%); z-index:10;" +
        "padding:0.15rem 0.8rem; font-size:0.9rem; color:#f0e6c8; background-color:rgba(20,16,10,0.75);" +
        "border:1px solid rgba(200,170,110,0.6); border-radius:0.3rem; pointer-events:none;";
      document.body.appendChild(banner);
    }
    const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
    const own = civAgeType(id);
    banner.textContent = `${Locale.compose("LOC_CA_YOUR_AGE")}: ${ageName(own)} · ${Locale.compose("LOC_CA_WORLD_AGE")}: ${ageName(world)}`;
    banner.style.display = "block";
    if (banner.textContent !== lastText) console.warn(`[CA-CHECK][UI] civ age banner, player ${id}: ${banner.textContent}`);
    lastText = banner.textContent;
  } catch (e) {
    console.warn(`[CA-CHECK][ERROR] civ age banner: ${e}`);
  }
}

engine.whenReady.then(() => {
  engine.on("TurnBegin", update);
  engine.on("LocalPlayerChanged", update);
  engine.on("GameAgeEnded", () => caTransitionCivs("age-ended"));
  setInterval(update, 3000);
  update();
});
