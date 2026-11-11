// Census test of rule 2n (build: build_mod.py --install --checks --age-points 8 --fast-test 0.01; suite:
// ContinuousAgesLive.json): every modifier unlock row below its node's highest depth, in all three worlds. The build
// writes the rows into globalThis.caMasterySplit (ca-checks.js). Slot 0 gets every node of a kept row by the debug grant
// (about 30 nodes are too many to research; mastery_unlocks.js is the test with normal research), then the game goes
// through both transitions. In each world, Players.get(id).Modifiers.getModifiers() lists the ACTIVE modifiers of slot 0
// (a call of the game's debug panels; it names each modifier id once). For each row of a node that slot 0 has:
//   a node at the row's depth: the row's own modifier is active ("low" for an additive effect, the original for a
//   switch effect), and the hidden copy "high" is not;
//   a node above the row's depth: "high" is active, and for an additive effect "low" is not (no double).
// Values, in the world of the grants, for the additive effects that the UI can read (specialist cap of the capital,
// tradition slots): one node each gives its amount at the row's depth and no more at the mastery. Each record also has
// the settlement cap, the specialist cap and the tradition slots, to compare runs with and without the rule.
//   --set CAMaster=1 (default)  every node to its highest depth: after a transition the "high" copies carry the effects.
//   --set CAMaster=0            every node to the row's depth only (the AI plays slot 0 near the age's end and can master
//                               some nodes; the check reads each node's depth when it runs).
// Negative control (--disable-rule mastery): the rows name the original modifiers and have no copies. With CAMaster=1
// the check fails after the first transition for each row whose modifier id no other row of slot 0 gives (a shared id,
// for example the settlement cap, stays listed while one row gives it; the values in the records show the loss). With
// CAMaster=0 it passes: a node granted by debug keeps its depth-1 modifiers across a transition, as a researched one does.
const me = GameContext.localPlayerID;
const MASTER = Number(Automation.getParameter("CurrentTest", "CAMaster", 1)) !== 0;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "mastery_census", phase: 1, name, ok, detail }); };
const settle = (ms = 2000) => new Promise((r) => setTimeout(r, ms));
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const short = (s) => String(s).replace(/^NODE_/, "");
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const all = globalThis.caMasterySplit ?? {};
const kept = (e) => e.kind === "additive" || e.kind === "switch";
const rows = (all[world] ?? []).filter(kept);
const ruleOn = rows.some((e) => e.high);
const capital = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const readers = {
  EFFECT_CITY_ADJUST_WORKER_CAP: () => capital()?.Workers?.getCityWorkerCap(),
  EFFECT_PLAYER_GRANT_TRADITION_SLOTS: () => Players.get(me).Culture?.getNumCultureSlots(CultureSlotTypes.TRADITION_CULTURE_SLOT),
};
// For the records (compare runs with and without the rule). The settlement cap is not this rule's: the engine carries it.
const values = () => ({ settlementCap: Players.get(me).Stats?.settlementCap, workerCap: capital()?.Workers?.getCityWorkerCap(),
  traditionSlots: Players.get(me).Culture?.getNumCultureSlots(CultureSlotTypes.TRADITION_CULTURE_SLOT) });
// The census of this world: the rows of the nodes that slot 0 has at the row's depth or above.
const census = () => {
  const active = new Set(Players.get(me).Modifiers.getModifiers().map((m) => GameEffects.getModifierDefinitionFromTypeId(m.modifierType)?.ID));
  const out = { rows: rows.length, covered: 0, atRowDepth: 0, above: 0, bad: [], uncovered: [] };
  for (const e of rows) {
    const has = depth(e.node);
    if (has < e.depth) { out.uncovered.push(`${short(e.node)} ${e.modifier}`); continue; }
    out.covered++;
    const at = has === e.depth;
    if (at) out.atRowDepth++; else out.above++;
    const want = !ruleOn ? e.modifier : at ? (e.low ?? e.modifier) : e.high;
    const not = !ruleOn ? null : at ? e.high : e.low;
    if (!active.has(want) || (not && active.has(not))) out.bad.push({ node: short(e.node), modifier: e.modifier, kind: e.kind, has, want: active.has(want), not: not ? active.has(not) : null });
  }
  return out;
};
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
const grantTo = async (node, target) => {
  for (let i = 0; i < 3 && depth(node) < target; i++) {
    const before = depth(node);
    if (!caLive.grantNode(node).sent) break;
    for (let k = 0; k < 10 && depth(node) === before; k++) await settle(300);
  }
  return depth(node) >= target;
};
// The Breakthroughs first (a civ with a later age's nodes has them).
const gates = Array.from(GameInfo.ProgressionTreeNodes).map((n) => n.ProgressionTreeNodeType).filter((n) => /^NODE_(TECH|CIVIC)_CA_\w+_BREAKTHROUGH$/.test(n)).sort();
const notGranted = [];
for (const g of gates) if (!(await grantTo(g, 1))) notGranted.push(short(g));
await settle();
// Values: one node for each additive effect with a reader, on a joined tree, that slot 0 does not have yet.
const mainTrees = new Set(["TREE_TECHS_AQ", "TREE_CIVICS_AQ_MAIN"]);
const steps = [];
for (const effect of Object.keys(readers)) {
  const e = rows.find((r) => r.effect === effect && r.kind === "additive" && r.alone && Number(r.amount) > 0 && depth(r.node) === 0
    && mainTrees.has(GameInfo.ProgressionTreeNodes.lookup(r.node)?.ProgressionTree));
  if (!e) { steps.push({ effect, row: null }); continue; }
  const v0 = readers[effect]();
  const g1 = await grantTo(e.node, e.depth); await settle(1500);
  const v1 = readers[effect]();
  const g2 = MASTER ? await grantTo(e.node, e.top) : true;  // CAMaster=0 masters no node: only the row's depth is read
  if (MASTER) await settle(1500);
  const v2 = readers[effect]();
  steps.push({ effect, node: short(e.node), modifier: e.modifier, amount: Number(e.amount), v0, v1, v2, granted: g1 && g2, ok: g1 && g2 && v1 === v0 + Number(e.amount) && v2 === v1 });
}
expect("values: for each additive effect that the UI can read, a node gives its amount at the row's depth and no more at the mastery (same world)",
  steps.length === 2 && steps.every((s) => s.ok === true), { steps });
// Then every node of a kept row of any world.
const targets = new Map();
for (const list of Object.values(all)) for (const e of list) if (kept(e)) targets.set(e.node, Math.max(targets.get(e.node) ?? 0, MASTER ? e.top : e.depth));
for (const [node, target] of [...targets].sort()) if (!(await grantTo(node, target))) notGranted.push(`${short(node)} (${depth(node)} of ${target}; ${GameInfo.ProgressionTreeNodes.lookup(node)?.ProgressionTree})`);
await settle();
const mainMissing = [...targets].filter(([node, target]) => depth(node) < target && mainTrees.has(GameInfo.ProgressionTreeNodes.lookup(node)?.ProgressionTree)).map(([n]) => short(n));
expect("setup: the build's list has kept rows for the three worlds, and every node of the joined trees was granted",
  Object.keys(all).length === 3 && rows.length >= 15 && gates.length >= 4 && mainMissing.length === 0,
  { worlds: Object.fromEntries(Object.entries(all).map(([w, l]) => [w, l.filter(kept).length])), ruleOn, master: MASTER, nodes: targets.size, gates: gates.length, mainMissing, notGranted });
const c1 = census();
expect("control: in the world of the grants, each row's modifier is active for slot 0 (and no double of an additive effect)", c1.covered >= 12 && c1.bad.length === 0,
  { ...c1, uncovered: c1.uncovered.length, badCount: c1.bad.length, values: values(),
    bad: c1.bad.slice(0, 6).map((b) => `${b.node} ${b.modifier}${b.want ? "" : " (not active)"}${b.not ? " (double)" : ""}`) });
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
// Slot 0 ends its own turns to the age's end. With these grants, AI play of slot 0 crashed the game in the Exploration
// world, with and without rule 2n (runs 20261111-125357-w1 and 20261111-125845-w1). CAAuto=1 lets the AI play, to study it.
const AUTO = Number(Automation.getParameter("CurrentTest", "CAAuto", 0)) !== 0;
for (let i = 0; AUTO && i < 30 && left() > 3; i++) await caLive.advance(1);
for (let i = 0; i < 40 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { if (AUTO && left() >= 2) await caLive.advance(1); } }
expect("the age is at its end", left() <= 0, { turn: Game.turn, left: left(), values: values() });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((c) => c.ok), checks, master: MASTER, ruleOn, transition: { auto: true } };

//// PHASE 2: the Exploration world
const me = GameContext.localPlayerID;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "mastery_census", phase: 2, name, ok, detail }); };
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const short = (s) => String(s).replace(/^NODE_/, "");
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const rows = ((globalThis.caMasterySplit ?? {})[world] ?? []).filter((e) => e.kind === "additive" || e.kind === "switch");
const ruleOn = rows.some((e) => e.high);
const capital = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const values = () => ({ settlementCap: Players.get(me).Stats?.settlementCap, workerCap: capital()?.Workers?.getCityWorkerCap(),
  traditionSlots: Players.get(me).Culture?.getNumCultureSlots(CultureSlotTypes.TRADITION_CULTURE_SLOT) });
const census = () => {
  const active = new Set(Players.get(me).Modifiers.getModifiers().map((m) => GameEffects.getModifierDefinitionFromTypeId(m.modifierType)?.ID));
  const out = { rows: rows.length, covered: 0, atRowDepth: 0, above: 0, bad: [], uncovered: [] };
  for (const e of rows) {
    const has = depth(e.node);
    if (has < e.depth) { out.uncovered.push(`${short(e.node)} ${e.modifier}`); continue; }
    out.covered++;
    const at = has === e.depth;
    if (at) out.atRowDepth++; else out.above++;
    const want = !ruleOn ? e.modifier : at ? (e.low ?? e.modifier) : e.high;
    const not = !ruleOn ? null : at ? e.high : e.low;
    if (!active.has(want) || (not && active.has(not))) out.bad.push({ node: short(e.node), modifier: e.modifier, kind: e.kind, has, want: active.has(want), not: not ? active.has(not) : null });
  }
  return out;
};
const prev = (globalThis.caPrev ?? [])[0] ?? {};
const c2 = census();
const mix = prev.master ? c2.above >= 12 : c2.atRowDepth >= 12;
expect("the world is Exploration and slot 0 is human, with the depths of this run", world === "AGE_EXPLORATION" && Players.get(me).isHuman && mix,
  { world, turn: Game.turn, master: prev.master, ruleOn, covered: c2.covered, atRowDepth: c2.atRowDepth, above: c2.above });
expect("test: after the transition, each row's modifier is active for slot 0 (the copy of the node's depth; no double of an additive effect)", c2.covered >= 12 && c2.bad.length === 0,
  { ...c2, uncovered: c2.uncovered.length, badCount: c2.bad.length, values: values(),
    bad: c2.bad.slice(0, 6).map((b) => `${b.node} ${b.modifier}${b.want ? "" : " (not active)"}${b.not ? " (double)" : ""}`) });
if (Number(Automation.getParameter("CurrentTest", "CAAuto", 0)) !== 0) {  // the research in progress, for the crash study
  let last = "";
  setInterval(() => { try { const t = JSON.stringify([Players.get(me).Techs?.getResearching?.(), Players.get(me).Culture?.getResearching?.()]);
    if (t !== last) { last = t; caLive.log({ scenario: "mastery_census", researching: t }); } } catch (e) { /* the page is closing */ } }, 250);
}
const m = Game.AgeProgressManager;
const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
// Slot 0 ends its own turns to the age's end. With these grants, AI play of slot 0 crashed the game in the Exploration
// world, with and without rule 2n (runs 20261111-125357-w1 and 20261111-125845-w1). CAAuto=1 lets the AI play, to study it.
const AUTO = Number(Automation.getParameter("CurrentTest", "CAAuto", 0)) !== 0;
for (let i = 0; AUTO && i < 30 && left() > 3; i++) await caLive.advance(1);
for (let i = 0; i < 40 && left() > 0; i++) { try { await caLive.endTurn(60000); } catch (e) { if (AUTO && left() >= 2) await caLive.advance(1); } }
expect("the age is at its end", left() <= 0, { turn: Game.turn, left: left(), values: values() });
setInterval(() => { if (Players.get(me)?.isTurnActive) GameContext.sendTurnComplete(); }, 3000);  // ends with the page
return { ok: checks.every((c) => c.ok), checks, master: prev.master, transition: { auto: true } };

//// PHASE 3: the Modern world
const me = GameContext.localPlayerID;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "mastery_census", phase: 3, name, ok, detail }); };
const depth = (n) => Game.ProgressionTrees.getNode(me, GameInfo.ProgressionTreeNodes.lookup(n)?.$hash)?.depthUnlocked ?? 0;
const short = (s) => String(s).replace(/^NODE_/, "");
const world = GameInfo.Ages.lookup(Game.age)?.AgeType;
const rows = ((globalThis.caMasterySplit ?? {})[world] ?? []).filter((e) => e.kind === "additive" || e.kind === "switch");
const ruleOn = rows.some((e) => e.high);
const capital = () => Players.get(me).Cities.getCityIds().map((id) => Cities.get(id)).find((c) => c?.isCapital);
const values = () => ({ settlementCap: Players.get(me).Stats?.settlementCap, workerCap: capital()?.Workers?.getCityWorkerCap(),
  traditionSlots: Players.get(me).Culture?.getNumCultureSlots(CultureSlotTypes.TRADITION_CULTURE_SLOT) });
const census = () => {
  const active = new Set(Players.get(me).Modifiers.getModifiers().map((m) => GameEffects.getModifierDefinitionFromTypeId(m.modifierType)?.ID));
  const out = { rows: rows.length, covered: 0, atRowDepth: 0, above: 0, bad: [], uncovered: [] };
  for (const e of rows) {
    const has = depth(e.node);
    if (has < e.depth) { out.uncovered.push(`${short(e.node)} ${e.modifier}`); continue; }
    out.covered++;
    const at = has === e.depth;
    if (at) out.atRowDepth++; else out.above++;
    const want = !ruleOn ? e.modifier : at ? (e.low ?? e.modifier) : e.high;
    const not = !ruleOn ? null : at ? e.high : e.low;
    if (!active.has(want) || (not && active.has(not))) out.bad.push({ node: short(e.node), modifier: e.modifier, kind: e.kind, has, want: active.has(want), not: not ? active.has(not) : null });
  }
  return out;
};
const c3 = census();
expect("the world is Modern and slot 0 is human", world === "AGE_MODERN" && Players.get(me).isHuman, { world, turn: Game.turn, ruleOn, covered: c3.covered, atRowDepth: c3.atRowDepth, above: c3.above });
expect("test: after the second transition, each row's modifier is active for slot 0 (the copy of the node's depth; no double of an additive effect)", c3.covered >= 12 && c3.bad.length === 0,
  { ...c3, uncovered: c3.uncovered.length, badCount: c3.bad.length, values: values(),
    bad: c3.bad.slice(0, 6).map((b) => `${b.node} ${b.modifier}${b.want ? "" : " (not active)"}${b.not ? " (double)" : ""}`) });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
