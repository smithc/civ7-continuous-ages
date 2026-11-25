// Continuous Ages: shows the local civ's own age (set by its Breakthrough techs) next to the world age.
// Each civ has its own age in this mod; the game's own UI shows only the world age.
import { Options, OptionType, CategoryType } from '/core/ui/options/model-options.js';
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

// The banner's position: an option in Options > Interface (a player report of 2026-11-19: the banner covered the
// banner of another mod). The choice is kept in the UI's local storage, which the game keeps across sessions.
const BANNER_KEY = "continuous-ages.banner-position";
const BANNER_POSITIONS = [
  { key: "top-center", label: "LOC_CA_BANNER_TOP_CENTER", css: { top: "0.4rem", left: "50%", transform: "translateX(-50%)" } },
  { key: "top-center-lower", label: "LOC_CA_BANNER_TOP_CENTER_LOWER", css: { top: "4.5rem", left: "50%", transform: "translateX(-50%)" } },
  { key: "top-left", label: "LOC_CA_BANNER_TOP_LEFT", css: { top: "4.5rem", left: "0.6rem" } },
  { key: "top-right", label: "LOC_CA_BANNER_TOP_RIGHT", css: { top: "4.5rem", right: "0.6rem" } },
  { key: "bottom-left", label: "LOC_CA_BANNER_BOTTOM_LEFT", css: { bottom: "0.4rem", left: "0.6rem" } },
  { key: "bottom-center", label: "LOC_CA_BANNER_BOTTOM_CENTER", css: { bottom: "0.4rem", left: "50%", transform: "translateX(-50%)" } },
  { key: "bottom-right", label: "LOC_CA_BANNER_BOTTOM_RIGHT", css: { bottom: "0.4rem", right: "0.6rem" } },
  { key: "hidden", label: "LOC_CA_BANNER_HIDDEN", css: null },
];
function bannerPosition() {
  let key = null;
  try { key = localStorage.getItem(BANNER_KEY); } catch (e) { /* no storage: the default */ }
  return BANNER_POSITIONS.find((p) => p.key === key) ?? BANNER_POSITIONS[0];
}
function setBannerPosition(key) {
  try { localStorage.setItem(BANNER_KEY, key); } catch (e) { console.warn(`[CA-CHECK][ERROR] banner position not stored: ${e}`); }
  console.warn(`[CA-CHECK][UI] age banner position: ${key}`);
  update();
}
function placeBanner() {
  const pos = bannerPosition();
  if (!banner) return pos;
  for (const side of ["top", "bottom", "left", "right", "transform"]) banner.style[side] = "";
  if (pos.css) for (const [k, v] of Object.entries(pos.css)) banner.style[k] = v;
  return pos;
}
globalThis.caBanner = { positions: BANNER_POSITIONS.map((p) => p.key), get: () => bannerPosition().key, set: setBannerPosition,
  element: () => banner };
try {
  Options.addInitCallback(() => {
    Options.addOption({
      category: CategoryType.Interface,
      group: "continuous_ages",
      type: OptionType.Dropdown,
      id: "option-ca-banner-position",
      label: "LOC_CA_OPTION_BANNER_POSITION",
      description: "LOC_CA_OPTION_BANNER_POSITION_DESCRIPTION",
      dropdownItems: BANNER_POSITIONS.map((p) => ({ label: p.label })),
      initListener: (info) => {
        info.currentValue = info.originalValue = BANNER_POSITIONS.indexOf(bannerPosition());
        info.selectedItemIndex = info.currentValue;
      },
      // The banner moves at once (a preview). Cancel calls restoreListener, which puts back the value the screen opened
      // with; Options.restore() calls initListener after it.
      updateListener: (info, value) => {
        info.currentValue = value;
        setBannerPosition(BANNER_POSITIONS[value]?.key ?? BANNER_POSITIONS[0].key);
      },
      restoreListener: (info) => {
        setBannerPosition(BANNER_POSITIONS[info.originalValue]?.key ?? BANNER_POSITIONS[0].key);
      },
    });
  });
} catch (e) {
  console.warn(`[CA-CHECK][ERROR] banner position option not added: ${e}`);
}

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
      banner.style.cssText = "position:absolute; z-index:10;" +
        "padding:0.15rem 0.8rem; font-size:0.9rem; color:#f0e6c8; background-color:rgba(20,16,10,0.75);" +
        "border:1px solid rgba(200,170,110,0.6); border-radius:0.3rem; pointer-events:none;";
      document.body.appendChild(banner);
    }
    const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
    const own = civAgeType(id);
    banner.textContent = `${Locale.compose("LOC_CA_YOUR_AGE")}: ${ageName(own)} · ${Locale.compose("LOC_CA_WORLD_AGE")}: ${ageName(world)}`;
    const pos = placeBanner();
    banner.style.display = pos.css ? "block" : "none";
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
