// Scenario test of the age banner's position option (a player report of 2026-11-19: the banner covers the banner of
// another mod). Build: build_mod.py --install --checks; suite: ContinuousAgesLive.json.
//   the option is in the game's Options model (Interface, group Continuous Ages), with one item per position
//   each position puts the banner on its side of the screen; "hidden" hides it; the default is the top center
//   the choice is kept in the UI's local storage (read back through a new read of the stored key)
//   the Options screen's own update call moves the banner (the path the dropdown uses)
// CABannerStep=set (default): the checks above; the run ends with "bottom right" stored.
// CABannerStep=check (the next entry, a new game process): the stored "bottom right" is applied at the start, then
// the default is stored again.
const me = GameContext.localPlayerID;
const checks = [];
const expect = (name, ok, detail = {}) => { checks.push({ name, ok, detail }); caLive.log({ scenario: "banner_position", phase: 1, name, ok, detail }); };
const settle = (ms = 1000) => new Promise((r) => setTimeout(r, ms));
if (Players.get(me).Cities.getCityIds().length === 0) await caLive.advance(2);
await settle(3500);  // the banner updates every 3 s
const B = globalThis.caBanner;
expect("setup: the banner script is loaded", !!B && !!B.element(), { keys: B?.positions });
if (!B) return { ok: false, checks };
const step = (() => { try { return Automation.getParameter("CurrentTest", "CABannerStep") ?? "set"; } catch (e) { return "set"; } })();
if (step === "check") {
  const r = B.element().getBoundingClientRect();
  const b = { left: Math.round(r.left), top: Math.round(r.top), shown: B.element().style.display !== "none", w: window.innerWidth, h: window.innerHeight };
  expect("a new game process: the stored position (bottom right) is applied at the start", B.get() === "bottom-right" && b.shown
    && b.left > window.innerWidth / 2 && b.top > window.innerHeight / 2, b);
  B.set("top-center");
  return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks };
}
B.set("top-center");
const el = B.element();
const box = () => { const r = el.getBoundingClientRect(); return { left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top),
  bottom: Math.round(r.bottom), shown: el.style.display !== "none", w: window.innerWidth, h: window.innerHeight }; };
const results = {};
for (const key of B.positions) { B.set(key); await settle(300); results[key] = box(); }
const W = window.innerWidth, H = window.innerHeight;
const centered = (b) => Math.abs((b.left + b.right) / 2 - W / 2) < W * 0.05;
expect("top center: shown, centered, at the top", results["top-center"].shown && centered(results["top-center"]) && results["top-center"].top < H * 0.1, results["top-center"]);
expect("top center, lower: centered, below the top center", centered(results["top-center-lower"]) && results["top-center-lower"].top > results["top-center"].top, results["top-center-lower"]);
expect("top left: on the left half, at the top", results["top-left"].right < W / 2 && results["top-left"].top < H / 2, results["top-left"]);
expect("top right: on the right half, at the top", results["top-right"].left > W / 2 && results["top-right"].top < H / 2, results["top-right"]);
expect("bottom left: on the left half, at the bottom", results["bottom-left"].right < W / 2 && results["bottom-left"].top > H / 2, results["bottom-left"]);
expect("bottom center: centered, at the bottom", centered(results["bottom-center"]) && results["bottom-center"].top > H / 2, results["bottom-center"]);
expect("bottom right: on the right half, at the bottom", results["bottom-right"].left > W / 2 && results["bottom-right"].top > H / 2, results["bottom-right"]);
expect("hidden: not shown", !results["hidden"].shown, results["hidden"]);
// The Options model: the entry and its update call (what the dropdown calls).
let model = null;
try { model = (await import("/core/ui/options/model-options.js")).Options; } catch (e) { model = null; }
if (model && !model.data.has("option-ca-banner-position")) { try { model.init(); } catch (e) { /* already initialized */ } }
const opt = model?.data?.get("option-ca-banner-position");
expect("the option is in the Options model (Interface, Continuous Ages)", !!opt && opt.category === "interface" && opt.group === "continuous_ages"
  && opt.dropdownItems?.length === B.positions.length, { found: !!opt, category: opt?.category, group: opt?.group, items: opt?.dropdownItems?.length });
if (opt) {
  opt.updateListener(opt, B.positions.indexOf("bottom-right"));
  await settle(300);
  const b = box();
  expect("the option's update call moves the banner (bottom right)", B.get() === "bottom-right" && b.left > W / 2 && b.top > H / 2, b);
  opt.initListener(opt);
  expect("the option's init call reads the stored position", opt.selectedItemIndex === B.positions.indexOf("bottom-right"), { index: opt.selectedItemIndex });
}
let stored = null;
try { stored = localStorage.getItem("continuous-ages.banner-position"); } catch (e) { stored = `error: ${e}`; }
expect("the choice is in the UI's local storage", stored === "bottom-right", { stored });
return { ok: checks.every((c) => c.ok), failed: checks.filter((c) => !c.ok), checks, results };
