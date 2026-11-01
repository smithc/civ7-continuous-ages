// Scenario test: the human's world transition (a normal game, live.py --manual; a build with short ages:
// --age-points 8). Slot 0 founds its capital and only ends its turns (no autoplay at any time). At the age end it
// starts the transition as the legends screen's button does; the shell's civ selection screen must come, and the
// civ chosen there (by live.py, as the screen does) must be slot 0's civ in the new age.
// Run it with the mod's test build and with the control build (--control: the base game) to compare.
const me = GameContext.localPlayerID;
const player = () => Players.get(me);
const civOf = () => GameInfo.Civilizations.lookup(player().civilizationType)?.CivilizationType;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "human_transition", name, ok, detail }); };
if (player().Cities.getCityIds().length === 0) {
  const founder = player().Units.getUnitIds().map((id) => Units.get(id)).find((u) => GameInfo.Units.lookup(u.type)?.FoundCity);
  if (founder) Game.UnitOperations.sendRequest(founder.id, "UNITOPERATION_FOUND_CITY", {});
  await caLive.sleep(3000);
}
expect("slot 0 founded its capital", player().Cities.getCityIds().length > 0);
for (let i = 0; i < 40 && !caLive.ageEnded; i++) await caLive.endTurn();
expect("the age ended (no autoplay used)", caLive.ageEnded, { turn: Game.turn, human: player().isHuman });
await caLive.sleep(5000);
const screens = [...document.querySelectorAll("*")].map((e) => e.tagName.toLowerCase()).filter((t) => /^screen-|legend|age-|end-/.test(t));
const p = GameSetup.findPlayerParameter(me, "AgeTransitionPlayerCivilization");
const options = (p?.domain?.possibleValues ?? []).filter((v) => (v.invalidReason ?? 0) == 0).map((v) => v.value?.toString()).filter((v) => v && v !== "RANDOM");
const next = GameInfo.Ages.lookup(Game.age)?.AgeType === "AGE_ANTIQUITY" ? "AGE_EXPLORATION" : "AGE_MODERN";
const ofNext = new Set(GameInfo.LegacyCivilizations.filter((r) => r.Age === next).map((r) => r.CivilizationType));
const pick = options.find((c) => c !== civOf() && ofNext.has(c)) ?? options.find((c) => c !== civOf());
expect("the game offers civs of the next age", !!pick, { options: options.slice(0, 12) });
caLive.transition();
return { ok: checks.every((c) => c.ok), transition: { civ: pick }, from: civOf(), screens: [...new Set(screens)].slice(0, 15),
         setting: p?.value?.value?.toString(), checks };

//// PHASE 2: the next world age
const me = GameContext.localPlayerID;
const prev = globalThis.caPrev[0];
const civ = GameInfo.Civilizations.lookup(Players.get(me).civilizationType)?.CivilizationType;
const checks = [{ name: `slot 0 has the civ chosen on the screen (${prev.transition.civ})`, ok: civ === prev.transition.civ, detail: { civ } },
                { name: "slot 0 is still human", ok: Players.get(me).isHuman, detail: {} }];
for (const c of checks) caLive.log({ scenario: "human_transition", ...c });
return { ok: checks.every((c) => c.ok), civ, checks };
