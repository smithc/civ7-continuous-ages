// Probe (build: python build_mod.py --install --checks --probe disable_gate; suite: --set Player0Civ=CIVILIZATION_MING):
// does EFFECT_PLAYER_DISABLE_BUILD_UNIT take effect when its requirement is a node the player completes
// during the game (rule 2i's requirement: the Exploration Breakthrough tech)?
//   UNIT_SCOUT    CA_PROBE_GATE_DYNAMIC               (no permanent, no PermanentlyDisabled)
//   UNIT_WARRIOR  CA_PROBE_GATE_DYNAMIC_PD            (no permanent, PermanentlyDisabled: rule 2i's form in 20261031-121009)
//   UNIT_SETTLER  CA_PROBE_GATE_PERMANENT_RUNONCE_PD  (permanent, run-once, PermanentlyDisabled)
//   UNIT_MERCHANT CA_REPLACE_UNIT_MANDARIN            (rule 2i itself, on Ming's trait)
const GATE = "NODE_TECH_CA_EXPLORATION_BREAKTHROUGH";
const units = ["UNIT_SCOUT", "UNIT_WARRIOR", "UNIT_SETTLER", "UNIT_MERCHANT"];
const tryCall = (f) => { try { return f(); } catch (e) { return `error ${e}`; } };
const state = (label) => {
  const p = Players.get(GameContext.localPlayerID);
  const out = { label, turn: Game.turn, gate: caLive.hasNode(GATE) };
  for (const u of units) {
    const hash = GameInfo.Units.lookup(u)?.$hash;
    out[u] = { disabled: tryCall(() => p.Units.isBuildDisabled(hash)), permanently: tryCall(() => p.Units.isBuildPermanentlyDisabled(hash)) };
  }
  caLive.log({ probe: "disable_gate", ...out });
  return out;
};
if (Players.get(GameContext.localPlayerID).Cities.getCityIds().length === 0) await caLive.advance(2);
const rows = [state("before the gate")];
rows.push({ grant: caLive.grantNode(GATE) });
await new Promise((r) => setTimeout(r, 2000));
rows.push(state("gate granted, same turn"));
await caLive.endTurn();
rows.push(state("gate granted, next turn"));
const last = rows[rows.length - 1];
return { ok: last.gate === true, rows };
