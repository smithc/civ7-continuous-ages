import { TreeGrid } from '/base-standard/ui/tree-grid/tree-grid.js';
import { Layout } from '/core/ui/utilities/utilities-layout.js';
import '/base-standard/ui/tree-grid/tree-line.js';

// Continuous Ages: tree columns from the prereqs inside the tree only.
// The first civics of an age need that age's Breakthrough tech, a prereq in the tech tree. The engine
// counts it in each node's treeDepth, and the tree screen (tree-grid.js) uses treeDepth as the column,
// so the first Modern civics stood 3 columns after the last Exploration civics, with stray lines in the
// 2 empty columns. This sets each node with a parent in the tree to its deepest parent + 1. When no
// prereq is outside the tree, the result is the engine's own treeDepth.
const fixedTrees = new Set();

function inTreeDepths(tree, nodes) {
  if (!Array.isArray(nodes)) return nodes;
  const parents = new Map();
  for (const node of nodes) {
    for (const child of node.connectedNodeTypes ?? []) {
      if (!parents.has(child)) parents.set(child, []);
      parents.get(child).push(node.nodeType);
    }
  }
  // An in-tree parent always has a lower engine depth than its child, so this order puts parents first.
  const depth = new Map();
  let moved = 0;
  for (const node of [...nodes].sort((a, b) => a.treeDepth - b.treeDepth)) {
    const known = (parents.get(node.nodeType) ?? []).filter((p) => depth.has(p));
    const d = known.length ? Math.max(...known.map((p) => depth.get(p))) + 1 : node.treeDepth;
    depth.set(node.nodeType, d);
    if (d !== node.treeDepth) {
      node.treeDepth = d;
      moved++;
    }
  }
  if (moved && !fixedTrees.has(tree)) {
    fixedTrees.add(tree);
    console.warn(`[CA-CHECK][UI] tree layout: ${moved} nodes of tree ${tree} moved to their in-tree depth`);
  }
  return nodes;
}

function patchTreeStructure() {
  const trees = Game?.ProgressionTrees;
  if (!trees || trees.caInTreeDepths) return;
  try {
    const original = trees.getTreeStructure.bind(trees);
    trees.getTreeStructure = (tree) => {
      const nodes = original(tree);
      try {
        return inTreeDepths(tree, nodes);
      } catch (e) {
        console.warn(`[CA-CHECK][ERROR] tree layout, tree ${tree}: ${e}`);
        return nodes;
      }
    };
    trees.caInTreeDepths = true;
    console.warn(`[CA-CHECK][UI] tree layout patch ${Game.ProgressionTrees.caInTreeDepths ? "active" : "not kept by the engine"}`);
  } catch (e) {
    console.warn(`[CA-CHECK][ERROR] tree layout patch: ${e}`);
  }
}

// A line over more than one column goes through dummy nodes (layout-normalize.js). tree-grid.js
// generateLayoutData then must replace the line's target in the source card's list with the first
// dummy, but it looks for the source itself (indexOf(from) is -1) and splice(-1, 1) removes the last
// connection. A card with two such lines (each Antiquity leaf before the last column has a line to
// Economics and to Piety) then loses one chain's start and keeps a straight line to the other target:
// stray lines that start or end in empty columns. This sets each source card's list again from the
// layout graph, where the chains are correct. The dummy cards' own lists are correct already.
const fixedLines = new Set();

function relinkDummyChains(grid) {
  const g = grid._treeData?.graphLayout;
  if (!g) return;
  let fixed = 0;
  for (const card of grid._treeData.cards) {
    if (card.isDummy) continue;
    const next = g.successors(card.nodeType.toString()) ?? [];
    if (!next.some((v) => g.node(v)?.dummy == "edge")) continue;
    const want = next.map((v) => grid.getCard(v)?.nodeType ?? v);
    const have = card.connectedNodeTypes.map(String);
    if (want.length == have.length && want.every((t) => have.includes(String(t)))) continue;
    card.connectedNodeTypes = want;
    fixed++;
  }
  const tree = grid._sourceProgressionTree;
  if (fixed && !fixedLines.has(tree)) {
    fixedLines.add(tree);
    console.warn(`[CA-CHECK][UI] tree layout: lines of ${fixed} nodes of tree ${tree} linked to their dummy chains`);
  }
}

const generateLayoutData = TreeGrid.prototype.generateLayoutData;
TreeGrid.prototype.generateLayoutData = function (...args) {
  const result = generateLayoutData.apply(this, args);
  try {
    relinkDummyChains(this);
  } catch (e) {
    console.warn(`[CA-CHECK][ERROR] tree layout lines: ${e}`);
  }
  return result;
};

// tree-line.js draws a line from a dummy to a card as one straight piece when their heights differ by
// little, and puts it at toTop - verticalLength: right for a dummy above the card, but for a dummy
// below the card the piece lands that far above the card's middle instead of at the dummy's height,
// and the chain breaks (Organized Military to Piety, UI.log [CA-CHECK][TREELAYOUT], 2026-10-27).
// This moves that piece to the dummy's height, as the game's code does for a dummy above the card.
// The dummy's height is its middle as getHorizontalCalculations takes it: half the height of its
// .tree-card-bg (0 for a dummy, so its top), else half its own height.
function middle(element) {
  const bg = element.querySelector(".tree-card-bg");
  return element.offsetTop + (bg ? bg.offsetHeight : element.offsetHeight) / 2;
}

function patchTreeLine() {
  const TreeLine = Controls.getDefinition("tree-line")?.createInstance;
  if (!TreeLine?.prototype?.createHorizontalLine) {
    console.warn("[CA-CHECK][ERROR] tree layout: no tree-line component to patch");
    return;
  }
  const createHorizontalLine = TreeLine.prototype.createHorizontalLine;
  TreeLine.prototype.createHorizontalLine = function (...args) {
    const result = createHorizontalLine.apply(this, args);
    try {
      if (this.isFromNodeDummy && !this.isToNodeDummy && this.Root.children.length == 1) {
        const [fromElement, toElement] = this.getConnectingNodes() ?? [];
        if (fromElement && toElement) {
          const dummyTop = middle(fromElement);
          const toTop = middle(toElement);
          if (dummyTop > toTop) {
            this.Root.children[0].style.topPX = dummyTop - toTop - Layout.pixelsToScreenPixels(this.OFFSET_TO_CENTER);
          }
        }
      }
    } catch (e) {
      console.warn(`[CA-CHECK][ERROR] tree layout line ${this.from} to ${this.to}: ${e}`);
    }
    return result;
  };
}

// The hover highlight marks the path to the hovered node (AI.getProgressionTreePath). The path to a
// later-age civic also has the techs to that age's Breakthrough, and tree-grid.js setHoverItem stops
// at the first node that is not in the tree ("Can't get hovered card", NODE_TECH_AQ_IRON_WORKING in
// UI.log, 2026-10-27), so the civics after it were not marked. This skips such nodes. The list it
// returns has only nodes of the tree; the screen marks the cards of that list.
const setHoverItem = TreeGrid.prototype.setHoverItem;
TreeGrid.prototype.setHoverItem = function (nodeIndex) {
  const path = Players.get(GameContext.localPlayerID)?.AI?.getProgressionTreePath(nodeIndex, 1);
  if (!path) return setHoverItem.call(this, nodeIndex);   // the game's code logs this case
  const highlightNodes = [];
  for (const qualifiedNode of path) {
    const card = this.getCard(qualifiedNode.nodeType.toString());
    if (!card) continue;
    highlightNodes.push(qualifiedNode.nodeType);
    card.isHoverQueued = true;
  }
  return highlightNodes;
};

patchTreeLine();
engine.whenReady.then(patchTreeStructure);
