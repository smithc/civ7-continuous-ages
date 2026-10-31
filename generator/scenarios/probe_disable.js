// Probe (build: python build_mod.py --install --checks --probe disable): which form of
// EFFECT_PLAYER_DISABLE_BUILD_UNIT stops training once its requirement (game turn >= 3) is met?
//   UNIT_SCOUT    CA_PROBE_DYNAMIC               (no permanent, no PermanentlyDisabled)
//   UNIT_WARRIOR  CA_PROBE_PERMANENT             (permanent)
//   UNIT_SETTLER  CA_PROBE_PERMANENT_RUNONCE_PD  (permanent, run-once, PermanentlyDisabled; the Pirate Republic form)
// Also records which calls exist for scripted tests (debug operations, unit library).
const units = ["UNIT_SCOUT", "UNIT_WARRIOR", "UNIT_SETTLER"];
const player = () => Players.get(GameContext.localPlayerID);
const tryCall = (f) => { try { return f(); } catch (e) { return `error ${e}`; } };
const rows = [];
function snapshot(label) {
  for (const u of units) {
    const hash = GameInfo.Units.lookup(u)?.$hash;
    const row = { label, turn: Game.turn, unit: u, ...caLive.canTrain(u),
      isBuildDisabled: tryCall(() => player().Units?.isBuildDisabled?.(hash)),
      isBuildPermanentlyDisabled: tryCall(() => player().Units?.isBuildPermanentlyDisabled?.(hash)) };
    rows.push(row);
    caLive.log({ probe: "disable", ...row });
  }
}
const env = { localPlayer: GameContext.localPlayerID, localObserver: tryCall(() => GameContext.localObserverID), turn: Game.turn,
  grantTreeNode: typeof PlayerOperationTypes?.GRANT_TREE_NODE, unitsLib: Object.keys(Units ?? {}).slice(0, 40) };
caLive.log({ probe: "disable", env });
await caLive.advance(1);            // the AI founds the capital
snapshot("turn 2 (requirement not met)");
await caLive.advance(2);
snapshot("turn 4 (requirement met)");
const at = (label, unit) => rows.find((r) => r.label.startsWith(label) && r.unit === unit);
const verdict = Object.fromEntries(units.map((u) => [u, { before: at("turn 2", u)?.ok, after: at("turn 4", u)?.ok }]));
return { ok: true, env, verdict, rows };
