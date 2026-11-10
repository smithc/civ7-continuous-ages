"""Build an earlier release on a newer game version (regression.py saves:play, tools/savecompat.py).

An earlier release's generator copies the game's transition script and applies TRANSITION_EDITS, each of which must
find its anchor. A game patch that changes an anchor stops that old build ("Transition script changed (game
patch?)"), so the save tests could not build the previous release (game 1.5.1, 2026-11-10: v0.5.0). patch_worktree()
applies the anchor changes that the current generator made for the same game patch to the old worktree, and only when
the installed game needs them. The old release's rules stay as they were: only anchors change.
"""
from __future__ import annotations

import os
from pathlib import Path

GAME_DIR = Path(os.environ.get("CIV7_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VII")
TRANSITION_SCRIPT = GAME_DIR / "Base" / "modules" / "base-standard" / "scripts" / "age-transition-post-load.js"

# (file in the worktree, old text, new text, text that the installed game's transition script must contain, why)
GAME_PATCHES = [
    ("generator/build_test1.py", "getNumDefenders() {", "getNumDefenders(iPlayer) {", "function getNumDefenders(iPlayer) {",
     "game 1.5.1: getNumDefenders takes the player (TRANSITION_EDITS anchor of the shadow helpers)"),
]


def patch_worktree(wt: Path) -> list[str]:
    """Applies GAME_PATCHES to an old release's worktree. Returns a line for each patch applied."""
    script = TRANSITION_SCRIPT.read_text(encoding="utf-8") if TRANSITION_SCRIPT.exists() else ""
    applied = []
    for rel, old, new, game_has, why in GAME_PATCHES:
        f = wt / rel
        if game_has not in script or not f.exists():
            continue
        data = f.read_bytes()
        if old.encode() in data:
            f.write_bytes(data.replace(old.encode(), new.encode()))
            applied.append(f"{rel}: {why}")
    return applied
