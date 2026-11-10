// Scenario test of the known limit U-TOWN-PURCHASE (docs/known-limits.md; build: build_mod.py --install --checks, or
// --control for the base game; suite: ContinuousAgesLive.json, Antiquity world).
// A town that may buy buildings of a tag (EFFECT_ADJUST_TOWN_CAN_PURCHASE_TAGGED_CONSTRUCTIBLES; here Augustus's
// ability, tag CULTURE) can buy a building of that tag without the building's own tech or civic: the engine names the
// missing unlock but allows the purchase. The base game does this within one age; the mod loads every age's content,
// so a town can also buy later-age buildings. This scenario shows the behavior and fails when it changes.
//   control step: the capital (a city, normal purchase rules) is refused each locked building (NeededUnlock)
//   Augustus: the new town buys the Amphitheater (Engineering, not researched), and on the mod build the Pavilion,
//     the Kiln (Exploration techs) and the Opera House (Modern tech)
//   another leader (no tag source): the new town cannot buy them
const me = GameContext.localPlayerID;
const p = Players.get(me);
const checks = [];
const expect = (name, value, want, detail = {}) => {
  checks.push({ name, ok: value === want, value, want, detail });
  caLive.log({ scenario: "town_purchase", name, ok: value === want, value, want, detail });
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
if (p.Cities.getCityIds().length === 0) await caLive.advance(2);
const leader = GameInfo.Leaders.lookup(p.leaderType)?.LeaderType;
const augustus = leader === "LEADER_AUGUSTUS";
const modBuild = GameInfo.ProgressionTreeNodes.lookup("NODE_TECH_CA_EXPLORATION_BREAKTHROUGH") != null;
const capId = p.Cities.getCityIds()[0];
const capLoc = Cities.get(capId).location;
expect("Masonry granted (Monument unlocked)", await caLive.grantNodeAndWait("NODE_TECH_AQ_MASONRY"), true);
Visibility.revealAllPlots(me);
// A new settlement is a town: a Settler on free land 4 to 6 plots from the capital.
let tries = 0;
for (let r = 4; r <= 6 && p.Cities.getCityIds().length < 2; r++) {
  for (let dx = -r; dx <= r && p.Cities.getCityIds().length < 2; dx++) for (const dy of [-r, r]) {
    if (p.Cities.getCityIds().length >= 2 || tries > 12) break;
    const x = capLoc.x + dx, y = capLoc.y + dy;
    if (x < 0 || y < 0 || x >= GameplayMap.getGridWidth() || y >= GameplayMap.getGridHeight()) continue;
    if (GameplayMap.isWater(x, y) || GameplayMap.isImpassable(x, y) || GameplayMap.getOwner(x, y) !== -1) continue;
    tries++;
    const u = await caLive.createUnitAndWait("UNIT_SETTLER", x, y);
    if (!u || !Game.UnitOperations.canStart(u.id, "UNITOPERATION_FOUND_CITY", {}, false)?.Success) continue;
    Game.UnitOperations.sendRequest(u.id, "UNITOPERATION_FOUND_CITY", {});
    await caLive.waitFor(() => p.Cities.getCityIds().length >= 2, 15000);
  }
}
const townId = p.Cities.getCityIds().find((c) => Cities.get(c)?.isTown);
expect("a town was founded", townId != null, true, { tries });
if (townId == null) return { ok: false, failed: checks.filter((c) => !c.ok), checks };
for (let i = 0; i < 20; i++) p.Treasury.changeGoldBalance(500, -1);
await sleep(1500);
const has = (cityId, type) => (Cities.get(cityId).Constructibles?.getIds() ?? [])
  .some((k) => GameInfo.Constructibles.lookup(Constructibles.getByComponentID(k)?.type)?.ConstructibleType === type);
// Buy on the first plot where the engine allows it; returns whether the building exists afterwards.
async function buy(cityId, type, really) {
  const d = GameInfo.Constructibles.lookup(type);
  const plain = Game.CityCommands.canStart(cityId, CityCommandTypes.PURCHASE, { ConstructibleType: d.$index }, false);
  const out = { allowed: false, bought: false, unlock: plain?.NeededUnlock ?? null };
  for (const idx of Cities.get(cityId).getPurchasedPlots() ?? []) {
    const loc = GameplayMap.getLocationFromIndex(idx);
    const args = { ConstructibleType: d.$index, X: loc.x, Y: loc.y };
    if (!Game.CityCommands.canStart(cityId, CityCommandTypes.PURCHASE, args, false)?.Success) continue;
    out.allowed = true;
    if (really) { Game.CityCommands.sendRequest(cityId, CityCommandTypes.PURCHASE, args); await sleep(1500); out.bought = has(cityId, type); }
    break;
  }
  return out;
}
const locked = ["BUILDING_AMPHITHEATER"].concat(modBuild ? ["BUILDING_PAVILION", "BUILDING_KILN", "BUILDING_OPERA_HOUSE"] : []);
for (const t of locked) {
  const def = GameInfo.Constructibles.lookup(t);
  expect(`${t} exists in this build`, def != null, true);
  if (!def) continue;
  const cap = await buy(capId, t, false);
  expect(`control: the capital is refused ${t}`, cap.allowed, false, cap);
  const town = await buy(townId, t, true);
  expect(augustus ? `U-TOWN-PURCHASE: Augustus's town buys ${t} without its unlock` : `no tag source: the town cannot buy ${t}`,
    augustus ? town.bought : town.allowed, augustus, town);
}
const monument = await buy(townId, "BUILDING_MONUMENT", false);
caLive.log({ scenario: "town_purchase", info: "Monument (unlocked) in the town", leader, modBuild, ...monument });
return { ok: checks.every((c) => c.ok), leader, modBuild, failed: checks.filter((c) => !c.ok), checks };
