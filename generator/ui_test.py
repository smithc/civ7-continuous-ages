"""UI test in the game: build and install the mod with the checks, start Civilization VII with the
suite autoplay/ContinuousAgesUITest.json (load a save, run the CAUITest automation test from
checks/ca-ui-test.js, quit), take a screenshot at each [CA-CHECK][UISHOT] marker in UI.log, and
write a report of the [CA-CHECK][UITEST] records.

    python ui_test.py [--save CA_AQ135] [--no-build] [--timeout 10]

Output: build/uitest/<stamp>/ with the screenshots (NN-<view>.png), UI.log, Automation.log and
REPORT.md. The game takes the screen while the test runs; the screenshots show the whole screen.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from iterate import HERE, REPO, LOGS, game_running, run
from tools.screenshot import screenshot

STEAM = r"C:\Program Files (x86)\Steam\steam.exe"
APP_ID = 1295660
SUITE = HERE / "autoplay" / "ContinuousAgesUITest.json"
OUT_ROOT = REPO / "build" / "uitest"
RECORD = re.compile(r"\[CA-CHECK\]\[(UISHOT|UITEST)\] (\{.*\})")


def records(text: str) -> list[tuple[str, dict]]:
    return [(m.group(1), json.loads(m.group(2))) for m in RECORD.finditer(text)]


def play(save: str, out: Path, timeout_min: float) -> tuple[bool, list[str]]:
    """Runs the suite; takes the screenshots. Returns (the game exited in time, screenshot names)."""
    suite_text = re.sub(r"SaveName=\w+", f"SaveName={save}", SUITE.read_text(encoding="utf-8"))
    suite = out / SUITE.name
    suite.write_text(suite_text, encoding="utf-8")   # UTF-8 without a BOM: the game ignores a suite with one
    start = time.time()
    subprocess.Popen([STEAM, "-applaunch", str(APP_ID), "-autojson", str(suite), "-bypassStartButton"])
    ui_log, offset, shots, seen = LOGS / "UI.log", 0, [], False
    while time.time() - start < timeout_min * 60:
        time.sleep(1)
        running = game_running()
        seen = seen or running
        if seen and not running:
            return True, shots
        # UI.log is written again at each game start: read only the new one, from where we stopped.
        if not ui_log.exists() or ui_log.stat().st_mtime < start:
            continue
        size = ui_log.stat().st_size
        if size < offset:
            offset = 0
        with ui_log.open("rb") as f:
            f.seek(offset)
            chunk = f.read(size - offset).decode("utf-8", "replace")
        cut = chunk.rfind("\n") + 1   # a line that is not complete yet waits for the next read
        offset += len(chunk[:cut].encode("utf-8"))
        for kind, rec in records(chunk[:cut]):
            if kind == "UISHOT":
                name = f"{len(shots) + 1:02d}-{rec['name']}.png"
                screenshot(out / name, max_width=3440)
                shots.append(name)
                print(f"  screenshot {name}")
    return False, shots


def joints(lines: list[dict]) -> list[dict]:
    """For each dummy card: the end of the line into it and the start of the line out of it
    (horizontal pieces only), and the gap between them in screen pixels. The boxes are screen boxes
    after the CSS rotation, so a piece is horizontal when it is wider than high (corners are square)."""
    flat = lambda p: p[3] > p[4]
    result = []
    for into in (l for l in lines if l["toDummy"]):
        out = next((l for l in lines if l["from"] == into["to"] and l["view"] == into["view"]), None)
        a = [p for p in into["pieces"] if flat(p)]
        b = [p for p in (out or {}).get("pieces", []) if flat(p)]
        if not a or not b:
            result.append({"view": into["view"], "dummy": into["to"], "ok": False, "why": "no horizontal piece"})
            continue
        end = max(a, key=lambda p: p[1] + p[3])
        begin = min(b, key=lambda p: p[1])
        dy = (begin[2] + begin[4] / 2) - (end[2] + end[4] / 2)
        dx = begin[1] - (end[1] + end[3])
        result.append({"view": into["view"], "dummy": into["to"], "dy": dy, "dx": dx, "ok": abs(dy) <= 3 and dx <= 4})
    return result


def report(out: Path, save: str, exited: bool, shots: list[str]) -> bool:
    text = (out / "UI.log").read_text(encoding="utf-8", errors="replace") if (out / "UI.log").exists() else ""
    tests = [r for k, r in records(text) if k == "UITEST"]
    lines = [r for r in tests if r.get("check") == "line"]
    hovers = [r for r in tests if r.get("check") == "hover"]
    errors = [r for r in tests if r.get("check") == "error"]
    js = joints(lines)
    auto = (out / "Automation.log").read_text(encoding="utf-8", errors="replace") if (out / "Automation.log").exists() else ""
    verdicts = re.findall(r"\[(PASS|FAIL)\].*", auto)
    ok = exited and bool(shots) and not errors and all(j["ok"] for j in js) and all(not h["unmarked"] for h in hovers)
    md = [f"# UI test {out.name}", "", f"- Save: {save}", f"- Game exited in time: {exited}",
          f"- Automation: {', '.join(verdicts) or 'no [PASS]/[FAIL] line'}", f"- Result: {'PASS' if ok else 'FAIL'}", "",
          "## Screenshots", ""] + [f"- {s}" for s in shots] + ["", "## Line joints at dummy cards", ""]
    md += [f"- {j['view']} {j['dummy']}: " + (f"dy {j['dy']}, dx {j['dx']}" if "dy" in j else j["why"])
           + ("" if j["ok"] else "  **FAIL**") for j in js] or ["- none"]
    md += ["", "## Hover highlight", ""]
    md += [f"- {h['view']} {h['target']}: path {h['path']} nodes, civics {len(h['civics'])}, unmarked {h['unmarked'] or 'none'}"
           + ("  **FAIL**" if h["unmarked"] else "") for h in hovers] or ["- none"]
    md += ["", "## Errors", ""] + ([f"- {e['error']}" for e in errors] or ["- none"])
    (out / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save", default="CA_AQ135", help="save in Saves/Single, without .Civ7Save")
    ap.add_argument("--no-build", action="store_true", help="use the installed mod as it is")
    ap.add_argument("--timeout", type=float, default=10, help="minutes")
    args = ap.parse_args()
    if game_running():
        raise SystemExit("The game is running: close it first.")
    if not args.no_build:
        r = run([sys.executable, str(HERE / "build_mod.py"), "--install", "--checks"])
        if r.returncode:
            raise SystemExit(r.stdout + r.stderr)
    out = OUT_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    print(f"UI test, save {args.save}: {out}")
    exited, shots = play(args.save, out, args.timeout)
    time.sleep(3)   # the logs are complete a moment after the game exits
    for name in ("UI.log", "Automation.log"):
        if (LOGS / name).exists():
            shutil.copyfile(LOGS / name, out / name)
    sys.exit(0 if report(out, args.save, exited, shots) else 1)


if __name__ == "__main__":
    main()
