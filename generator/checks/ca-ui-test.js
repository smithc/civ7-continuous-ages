// Continuous Ages automation test "CAUITest": UI checks in a loaded game (suite autoplay/ContinuousAgesUITest.json,
// run by ui_test.py). It opens the civic tree, scrolls each age border into view, points at a later-age civic, and
// logs [CA-CHECK][UISHOT] {name} when a view is ready (ui_test.py takes a screenshot then) and [CA-CHECK][UITEST]
// records: the drawn pieces of each line at a dummy card (ui_test.py checks that the chains join) and the cards that
// the hover highlight marks.
import { Shared_OnAutomationEvent, PassTest, FailTest } from '../../base-standard/ui/automation/automation-test-support.js';
import { ContextManager } from '../../core/ui/context-manager/context-manager.js';
import { Icon } from '../../core/ui/utilities/utilities-image.js';

const SHOT_WAIT_MS = 4000;   // time for ui_test.py to take the screenshot after a UISHOT marker
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const log = (kind, record) => console.warn(`[CA-CHECK][${kind}] ${JSON.stringify(record)}`);
const hash = (type) => GameInfo.ProgressionTreeNodes.lookup(type)?.$hash;
const card = (type) => document.querySelector(`tree-card-v2[type="${type}"]`);

async function waitFor(test, ms, what) {
  for (let t = 0; t < ms; t += 500) {
    if (test()) return;
    await wait(500);
  }
  throw new Error(`timed out: ${what}`);
}

async function shot(name) {
  log("UISHOT", { name });
  await wait(SHOT_WAIT_MS);
}

const rect = (e) => {
  const r = e.getBoundingClientRect();
  return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
};

// Each line that starts or ends at a dummy card, with its pieces in screen pixels.
function logDummyLines(view) {
  let count = 0;
  for (const line of document.querySelectorAll("tree-line")) {
    const from = line.getAttribute("from"), to = line.getAttribute("to");
    const fromDummy = card(from)?.classList.contains("dummy") ?? false;
    const toDummy = card(to)?.classList.contains("dummy") ?? false;
    if (!fromDummy && !toDummy) continue;
    const pieces = [];
    for (const piece of line.querySelectorAll("div")) pieces.push([piece.className.replace(/absolute |tree-grid-line/g, "").trim(), ...rect(piece)]);
    log("UITEST", { check: "line", view, from, to, fromDummy, toDummy, from_box: rect(card(from)), to_box: rect(card(to)), pieces });
    count++;
  }
  return count;
}

// The civics on the path to the target, and which of them the hover highlight marked.
function logHover(view, type) {
  const path = Players.get(GameContext.localPlayerID)?.AI?.getProgressionTreePath(hash(type), 1) ?? [];
  const civics = path.map((q) => q.nodeType).filter((t) => card(t));
  const marked = civics.filter((t) => card(t).classList.contains("hoverqueued"));
  const name = (t) => GameInfo.ProgressionTreeNodes.lookup(t)?.ProgressionTreeNodeType?.replace("NODE_", "") ?? `${t}`;
  log("UITEST", { check: "hover", view, target: type, path: path.length, civics: civics.map(name), unmarked: civics.filter((t) => !marked.includes(t)).map(name) });
}

async function runChecks() {
  await wait(5000);   // the loaded game's UI settles
  // As the civic chooser's "open full tree" (culture-chooser.js openFullTree): the screen gets its trees by an event.
  const treeCSV = Players.get(GameContext.localPlayerID)?.Culture?.getAvailableTrees()?.join(",");
  if (!treeCSV) throw new Error("the local player has no civic trees");
  ContextManager.push("screen-culture-tree", { singleton: true, createMouseGuard: true,
    targetParent: document.querySelector(".fxs-trees") ?? undefined });
  window.dispatchEvent(new CustomEvent("view-culture-progression-tree", {
    detail: { treeCSV, targetNode: undefined, iconCallback: Icon.getCultureIconFromProgressionTreeNodeDefinition } }));
  await waitFor(() => card(hash("NODE_CIVIC_EX_MAIN_ECONOMICS")), 30000, "civic tree cards");
  await wait(3000);   // lines are drawn some frames after the cards
  const screen = document.querySelector("screen-culture-tree");
  for (const [view, type] of [["civics-aq-ex", "NODE_CIVIC_EX_MAIN_ECONOMICS"], ["civics-ex-mo", "NODE_CIVIC_MO_MAIN_MODERNIZATION"]]) {
    const element = card(hash(type));
    element.closest("fxs-scrollable-horizontal")?.component?.scrollIntoView(element);
    await wait(2000);
    log("UITEST", { check: "view", view, lines: logDummyLines(view) });
    await shot(view);
    screen.component.handleCardHover(String(hash(type)), "0");
    await wait(1000);
    logHover(view, type);
    await shot(`${view}-hover`);
    screen.component.handleCardDehover();
  }
}

class CAUITest {
  listener = (command, ...args) => this.onAutomationEvent(command, args);
  register() {
    engine.on("Automation-Test-CAUITest", this.listener);
  }
  onAutomationEvent(command, args) {
    Shared_OnAutomationEvent(args);
    Automation.log(`CAUITest: event ${command}`);
    if (command !== "Run") return;
    runChecks().then(() => PassTest(""), async (e) => {
      log("UITEST", { check: "error", error: `${e}` });
      await shot("error");   // the screen at the failure
      FailTest(`${e}`);
    });
  }
}

new CAUITest().register();
Automation.setScriptHasLoaded("ca-ui-test");
