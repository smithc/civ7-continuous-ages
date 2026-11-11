"""The release regression set: run it in parallel game workers, follow it, run again what failed, stop it.

  python regression.py --list [--workers N]      the items, their commands and typical minutes (one game each);
                                                 with --workers, the estimated time of the set
  python regression.py run [--workers N] [--only K1,K2,...] [--skip K,...] [--prev v0.4.0] [--fresh-saves] [--dry-run]
                                                 run the items on N workers at once (default 6); results in
                                                 build/regression/<stamp>.txt, each item's output in build/regression/<stamp>/;
                                                 an item whose game hung (HANG FAIL) runs once more
  python regression.py status [RESULTS]          the latest (or given) set: each item's result and report, the items
                                                 that run now with their worker's turn, the items not started
  python regression.py rerun [RESULTS] [--workers N] [--dry-run]
                                                 a new set with only the items that did not pass in RESULTS
  python regression.py stop [--yes]              stop the running set: it starts no next item, and the iterate.py,
                                                 live.py, runner and game of each running item are closed (dry run
                                                 without --yes)

Workers (gamepool.py): each item runs as "iterate.py --worker K" (or "live.py --worker K"): its own user folders,
Mods, Logs and Saves, and its own build. The real user folders and the installed mod do not change. A worker
starts the game from its executable; the Steam client must run. Before a set starts, it checks that each worker
gets its own Saves folder (a Windows setting outside the repo: "python gamepool.py check"; docs/development.md,
Parallel games). The longest items start first. "live" (live.py all) needs port 9444, so at most one live item
runs at a time. "saves" is the save compatibility test (docs/releasing.md): "saves:play" plays the previous
release (--prev, default: the newest v* tag that is not HEAD) from a git worktree in a worker, and keeps 5 of
its autosaves as CA_<TAG>_<world>_<turn>.Civ7Save in the real Saves folder; then "saves:<world>_<turn>" loads
each one with the current build for 20 turns. Saves kept by an earlier set are used again (--fresh-saves plays
the old version again).

Rules: never while the user plays (the set refuses to start while a game runs that no worker started). Run it
in the background (Claude Code: run_in_background) or in a terminal for a night run. Stop it only with
"regression.py stop --yes": stopping the Python process alone leaves its items and games running.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import gamepool
import oldversion

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REG = REPO / "build" / "regression"
STATE = REG / "current.json"
STOP_FILE = REG / "STOP"
# 6 workers with minimum graphics quality in the workers (gamepool.WORKER_GRAPHICS): in the GPU study of 2026-11-01,
# 6 games each played 1.64 s/turn against 1.87 for 4 games at High (base game, 100 Antiquity turns), so a set should
# take about 50 minutes instead of 86 (projected; the first set on 6 workers measures it). Later the same day: no
# frame cap, VSync off, no camera movement and a held priority gave 4.0 turns per second with 6 games. At High, 4 games used about
# 28 of the 32 GB of GPU memory; at minimum quality a game uses about 1.5 GB.
DEFAULT_WORKERS = 6

T = "--turns 700 --timeout 150 --expect-transitions 3"
# key, command (in generator/; the set adds --worker K), typical minutes of one game alone (measured on 31 October
# and 1 November 2026), why
ITEMS = [
    ("transition", f"iterate.py --suite ContinuousAgesTransition.json --no-fast-test --observe NONE {T}", 15,
     "three ages, normal cost: continuity through both transitions"),
    ("seed777", f"iterate.py --suite ContinuousAgesTransitionSeed777.json --fast-test 0.4 --observe NONE {T}", 11,
     "civs ahead of the world, DLC civs"),
    ("persist", f"iterate.py --suite ContinuousAgesTransitionPersist.json --no-fast-test --observe NONE {T}", 15,
     "civs keep their civ: Test of Time trees, legacy civs, governments"),
    ("timetested", f"iterate.py --suite ContinuousAgesTimeTested.json --fast-test 0.4 --observe NONE {T}", 15,
     "later-age civs from the start (rule 2i)"),
    ("default1001", f"iterate.py --suite ContinuousAgesDefault.json --no-fast-test --observe NONE {T} --set MapSeed=1001 --set GameSeed=1001", 13,
     "the default setup: random AI civs from any age"),
    ("default2002", f"iterate.py --suite ContinuousAgesDefault.json --fast-test 0.4 --observe NONE {T} --set MapSeed=2002 --set GameSeed=2002", 11,
     "the default setup, second seed"),
    ("default3003", f"iterate.py --suite ContinuousAgesDefault.json --fast-test 0.4 --observe NONE {T} --set MapSeed=3003 --set GameSeed=3003", 14,
     "the default setup, third seed"),
    ("catchup", f"iterate.py --suite ContinuousAgesTransitionCatchUp.json --no-fast-test --observe NONE {T}", 15,
     "Catch-up Research +100% through the Modern world"),
    ("human", f"iterate.py --suite ContinuousAgesTransitionHuman.json --no-fast-test --observe 0 {T}", 45,
     "one human slot (--observe 0: about 4 times slower per turn; it hung once at Modern turn 1)"),
    ("quick", f"iterate.py --suite ContinuousAgesTransitionQuick.json --no-fast-test --observe NONE {T}", 11, "game speed Quick"),
    ("epic", "iterate.py --suite ContinuousAgesTransitionEpic.json --no-fast-test --observe NONE --turns 1500 --timeout 240 --expect-transitions 3", 18,
     "game speed Epic"),
    ("marathon", "iterate.py --suite ContinuousAgesTransitionMarathon.json --no-fast-test --observe NONE --turns 1500 --timeout 240 --expect-transitions 3", 31,
     "game speed Marathon"),
    # live: 35 minutes for 20 scenarios in set 20261110-132232 (it started last and ended last); 25 scenarios since rule
    # 2n (2026-11-11: about 16 minutes more). The time decides the start order (longest first), so it must be current.
    ("live", "live.py all", 50, "all live scenarios (scenarios/scenarios.json), one game each, in one worker"),
    ("saves", "(save compatibility: play --prev in a worker, keep 5 autosaves, load each with this build)", 25,
     "saves of the previous release load and play 20 turns"),
]
SAVE_POINTS = ["00_0100", "00_0135", "01_0060", "01_0135", "02_0060"]  # AutoSave_<world 00/01/02>_<turn>
SAVE_PLAY_MINUTES, SAVE_LOAD_MINUTES = 15, 4
# The load suite loads the save named by its first test's SaveName (default CA_COMPAT); --set names the kept save.
SAVE_LOAD = "iterate.py --suite ContinuousAgesFromSaveCompat.json --no-fast-test --turns 20 --observe NONE --timeout 25 --set SaveName={save}"
PLAY_ARGS = ["-Turns", "700", "-TimeoutMinutes", "150", "-ObserveAs", "NONE"]  # the previous release's three-age game
RESULT = re.compile(r"^(PASS|FAIL|\d+ FAIL): (.+)$")


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def git(*args: str, repo: Path = REPO) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


def prev_tag() -> str | None:
    head = git("rev-parse", "HEAD")
    for tag in git("tag", "--list", "v*", "--sort=-v:refname").splitlines():
        if git("rev-list", "-n", "1", tag) != head:
            return tag
    return None


def tag_code(tag: str) -> str:
    return tag.upper().replace(".", "")  # v0.4.0 -> V040


def pid_alive(pid) -> bool:
    if not pid:
        return False
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return f'"{pid}"' in out


# -- Jobs ---------------------------------------------------------------------------------------------------
@dataclass
class Job:
    key: str
    script: str  # iterate.py, live.py, or regression.py (saves:play)
    args: list[str]
    minutes: int
    needs: str | None = None  # a job that must end first
    save: str | None = None  # saves:<w>: the kept save that the item loads
    live: bool = False
    worker: int | None = None
    proc: subprocess.Popen | None = None
    log: Path | None = None
    started: float = 0.0
    result: str | None = None
    path: str = ""
    retried: bool = False  # a second run after a hang
    extra: dict = field(default_factory=dict)

    def again(self) -> "Job":
        return Job(self.key, self.script, self.args, self.minutes, self.needs, self.save, self.live, retried=True)

    def command(self, worker: int) -> list[str]:
        if self.script == "live.py":
            return [self.script, "--worker", str(worker), *self.args]
        return [self.script, *self.args, "--worker", str(worker)]


def jobs_for(keys: list[str], prev: str | None, fresh: bool, dry: bool) -> tuple[list[Job], list[str]]:
    """The jobs of the items, and lines for items that cannot run at all."""
    items = {k: (c, m) for k, c, m, _ in ITEMS}
    jobs, notes = [], []
    for key in keys:
        cmd, minutes = items[key]
        if key == "live":
            jobs.append(Job(key, "live.py", cmd.split()[1:], minutes, live=True))
        elif key == "saves":
            if not prev:
                notes.append(f"-- {now()} [saves] COULD NOT RUN: no earlier v* tag")
                continue
            code = tag_code(prev)
            real = gamepool.saves(None)
            kept = {w: real / f"CA_{code}_{w}.Civ7Save" for w in SAVE_POINTS}
            needs = None
            if fresh or not all(p.exists() for p in kept.values()):
                jobs.append(Job("saves:play", "regression.py", ["_play", "--prev", prev], SAVE_PLAY_MINUTES))
                needs = "saves:play"
            else:
                notes.append(f"-- {now()} [saves:play] kept saves of {prev} found ({real}); not played again (--fresh-saves plays it)")
            for w, save in kept.items():
                jobs.append(Job(f"saves:{w}", "iterate.py", SAVE_LOAD.format(save=save.stem).split()[1:], SAVE_LOAD_MINUTES,
                                needs=needs, save=save.stem))
        else:
            jobs.append(Job(key, cmd.split()[0], cmd.split()[1:], minutes))
    return jobs, notes


def estimate(jobs: list[Job], workers: int) -> float:
    """Minutes of the set on N workers, from the typical minutes of one game alone (longest first; no slowdown
    from running together counted)."""
    free = [0.0] * workers
    done: dict[str, float] = {}
    live_free = 0.0
    for j in order(jobs):
        i = min(range(workers), key=lambda k: free[k])
        t = max(free[i], done.get(j.needs, 0.0) if j.needs else 0.0, live_free if j.live else 0.0)
        free[i] = t + j.minutes
        done[j.key] = free[i]
        if j.live:
            live_free = free[i]
    return max(free) if jobs else 0.0


def order(jobs: list[Job]) -> list[Job]:
    """Longest first; a job that waits for another goes after it."""
    out = sorted(jobs, key=lambda j: -j.minutes)
    for j in [j for j in out if j.needs]:
        out.remove(j)
        out.insert(max(i for i, x in enumerate(out) if x.key == j.needs) + 1 if any(x.key == j.needs for x in out) else len(out), j)
    return out


class Runner:
    def __init__(self, results: Path, workers: int, dry: bool):
        self.results, self.workers, self.dry = results, workers, dry
        self.logdir = results.with_suffix("")
        self.passed = self.failed = 0

    def write(self, line: str) -> None:
        print(line, flush=True)
        if not self.dry:
            with self.results.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def save_state(self, running: list[Job]) -> None:
        if not self.dry:
            STATE.write_text(json.dumps({"pid": os.getpid(), "results": str(self.results), "workers": self.workers,
                                         "jobs": {j.key: {"pid": j.proc.pid if j.proc else None, "worker": j.worker,
                                                          "started": j.started} for j in running}}), encoding="utf-8")

    def start(self, j: Job, worker: int) -> None:
        j.worker, j.started = worker, time.time()
        cmd = j.command(worker)
        self.write(f"== {now()} [{j.key}] w{worker} python {' '.join(cmd)}")
        if self.dry:
            return
        self.logdir.mkdir(parents=True, exist_ok=True)
        j.log = self.logdir / f"{j.key.replace(':', '-')}.log"
        with j.log.open("w", encoding="utf-8") as out:
            j.proc = subprocess.Popen([sys.executable, "-u", *cmd], cwd=HERE, stdout=out, stderr=subprocess.STDOUT,
                                      env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def hang(self, j: Job) -> bool:
        """The runner closed the item's game as a hang: 'HANG FAIL' in its REPORT.md, or the runner's 'HANG:' line in
        the item's output (saves:play)."""
        text = j.log.read_text(encoding="utf-8", errors="replace") if j.log and j.log.exists() else ""
        if re.search(r"^HANG:", text, re.M):
            return True
        report = Path(j.path) if j.path.endswith("REPORT.md") else None
        return bool(report and report.exists() and "HANG FAIL" in report.read_text(encoding="utf-8", errors="replace"))

    def finish(self, j: Job, code: int | None) -> None:
        tail = j.log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:] if j.log and j.log.exists() else []
        found = [m for m in (RESULT.match(l.strip()) for l in tail) if m]
        minutes = (time.time() - j.started) / 60
        if STOP_FILE.exists():
            j.result = "STOPPED"
            self.write(f"-- {now()} [{j.key}] STOPPED (exit {code})")
        elif found and code in (0, 1):
            verdict, path = found[-1].group(1), found[-1].group(2)
            j.result = "PASS" if verdict == "PASS" and code == 0 else "FAIL"
            j.path = path
            if j.result == "FAIL" and not j.retried and self.hang(j):
                # The rare base-game hang in the turn-start autosave (docs/known-limits.md): run the item once more.
                j.result = "RETRY"
                self.write(f"-- {now()} [{j.key}] RETRY after HANG FAIL: {path} ({minutes:.0f} min); the item runs once more")
                return
            self.write(f"-- {now()} [{j.key}] {j.result}: {path} ({minutes:.0f} min)"
                       + (" (second run after a hang)" if j.retried else ""))
        else:
            j.result = "COULD NOT RUN"
            last = next((l for l in reversed(tail) if l.strip()), "")
            self.write(f"-- {now()} [{j.key}] COULD NOT RUN (exit {code}): {last[:300]} (output: {j.log})")
        self.passed += j.result == "PASS"
        self.failed += j.result != "PASS"

    def run(self, jobs: list[Job], notes: list[str], keys: list[str]) -> int:
        STOP_FILE.unlink(missing_ok=True) if not self.dry else None
        head = git("rev-parse", "--short", "HEAD")
        dirty = " + uncommitted changes" if git("status", "--porcelain", "generator") else ""
        serial = sum(j.minutes for j in jobs)
        self.write(f"# Regression {self.results.stem}: git {head}{dirty}; items {','.join(keys)}; workers {self.workers}; "
                   f"started {now()} ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC); typical {serial} min one at a time, "
                   f"about {estimate(jobs, self.workers):.0f} min on {self.workers} workers")
        for line in notes:
            self.write(line)
            self.failed += "COULD NOT RUN" in line
        t0 = time.time()
        pending, running, ended = order(jobs), [], {}
        free = list(range(1, self.workers + 1))
        try:
            while pending or running:
                # Start what can start: a free worker; the job it waits for has ended; one live game at a time.
                for j in list(pending):
                    if STOP_FILE.exists() or not free:
                        break
                    if j.needs and j.needs not in ended:
                        continue
                    if j.live and any(r.live for r in running):
                        continue
                    pending.remove(j)
                    if j.needs and ended.get(j.needs) != "PASS":
                        self.write(f"-- {now()} [{j.key}] COULD NOT RUN: {j.needs} did not pass")
                        self.failed += 1
                        ended[j.key] = "COULD NOT RUN"
                        continue
                    if j.save and not self.dry and not (gamepool.saves(None) / f"{j.save}.Civ7Save").exists():
                        self.write(f"-- {now()} [{j.key}] COULD NOT RUN: no save {j.save}.Civ7Save")
                        self.failed += 1
                        ended[j.key] = "COULD NOT RUN"
                        continue
                    self.start(j, free.pop(0))
                    running.append(j)
                    if not self.dry:
                        time.sleep(15)  # the game starts read the same files: start them a little apart
                if STOP_FILE.exists() and not running:
                    break
                self.save_state(running)
                if self.dry:
                    for j in running:
                        ended[j.key] = "PASS"
                        free.append(j.worker)
                    running = []
                    free.sort()
                    continue
                time.sleep(5)
                for j in list(running):
                    code = j.proc.poll()
                    if code is None:
                        continue
                    self.finish(j, code)
                    running.remove(j)
                    free.append(j.worker)
                    free.sort()
                    if j.result == "RETRY":
                        pending.insert(0, j.again())  # first in line; items that wait for it keep waiting
                    else:
                        ended[j.key] = j.result
                if STOP_FILE.exists():
                    for j in pending:
                        self.write(f"-- {now()} [{j.key}] STOPPED (not started)")
                    pending = []
        finally:
            if not self.dry:
                STATE.unlink(missing_ok=True)
        word = "STOPPED" if STOP_FILE.exists() else "DONE"
        self.write(f"{word} {now()}: {self.passed} pass, {self.failed} not passed; {(time.time() - t0) / 60:.0f} min on "
                   f"{self.workers} workers (typical one at a time: {serial} min)")
        STOP_FILE.unlink(missing_ok=True) if not self.dry else None
        return 0 if self.failed == 0 and word == "DONE" else 1


# -- saves:play (runs as its own process in a worker: "regression.py _play --prev TAG --worker K") ----------
def play_previous(prev: str, worker: int) -> int:
    """Plays the previous release in worker K and keeps 5 of its autosaves. The previous release's own build_mod.py
    (from a git worktree) builds and installs the old mod into the worker (its MODS_DIR follows LOCALAPPDATA), and the
    CURRENT run_autoplay.ps1 plays the old release's suite (an old runner would start the game through Steam)."""
    os.environ.update(gamepool.env(worker))
    problem = gamepool.require_documents(worker)
    if problem:
        print(problem)
        return 2
    code = tag_code(prev)
    real = gamepool.saves(None)
    kept = {w: real / f"CA_{code}_{w}.Civ7Save" for w in SAVE_POINTS}
    wt = REPO.parent / f"{REPO.name}-{prev}"
    print(f"play {prev} in the worktree {wt} as worker {worker}; keep autosaves {', '.join(SAVE_POINTS)} as {code}")
    if wt.exists():
        print(f"COULD NOT RUN: {wt} exists (an earlier worktree; remove it with git worktree remove)")
        return 2
    r = subprocess.run(["git", "-C", str(REPO), "worktree", "add", str(wt), prev], capture_output=True, text=True)
    if r.returncode:
        print(f"COULD NOT RUN: git worktree add: {r.stderr.strip()[:300]}")
        return 2
    for line in oldversion.patch_worktree(wt):  # anchors of a newer game version (oldversion.py)
        print(f"patched {prev} for this game version: {line}", flush=True)
    done = threading.Event()
    own_auto = gamepool.saves(worker) / "auto"
    t0 = time.time()

    def copier() -> None:  # the game keeps only the last few autosaves: copy each wanted one when it appears
        while not done.is_set():
            for w, dst in kept.items():
                src = own_auto / f"AutoSave_{w}.Civ7Save"
                if src.exists() and not dst.exists() and src.stat().st_mtime > t0:
                    time.sleep(5)  # the game may still write it
                    shutil.copy2(src, dst)
                    print(f"kept {dst.name}", flush=True)
            done.wait(3)
    try:
        gamepool.prepare(worker)
        b = subprocess.run([sys.executable, "build_mod.py", "--install", "--checks"], cwd=wt / "generator",
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if "Installed to" not in b.stdout:
            print(f"COULD NOT RUN: the build of {prev} failed:\n{(b.stdout + b.stderr)[-1500:]}")
            return 2
        print(f"built and installed {prev}: {[l for l in b.stdout.splitlines() if l.startswith('Installed to')][-1]}", flush=True)
        for dst in kept.values():
            dst.unlink(missing_ok=True)
        th = threading.Thread(target=copier, daemon=True)
        th.start()
        res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "run_autoplay.ps1"), *PLAY_ARGS,
                              "-SuiteFile", str(wt / "generator" / "autoplay" / "ContinuousAgesTransition.json")],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(res.stdout + res.stderr, flush=True)
        done.set()
        th.join(timeout=30)
    finally:
        done.set()
        subprocess.run(["git", "-C", str(REPO), "worktree", "remove", "--force", str(wt)], capture_output=True)
    have = [p.name for p in kept.values() if p.exists()]
    if len(have) == len(kept):
        print(f"PASS: kept {', '.join(have)} in {real} (runner exit {res.returncode})")
        return 0
    print(f"FAIL: kept {len(have)} of {len(kept)} saves ({', '.join(have) or 'none'}); runner exit {res.returncode}")
    return 1


# -- Results ------------------------------------------------------------------------------------------------
def latest_results() -> Path | None:
    files = sorted(REG.glob("*.txt"))
    return files[-1] if files else None


def parse_results(path: Path) -> tuple[str, list[dict]]:
    """Items of a results file: this script's format ('== time [key] wK python ...' and '-- time [key] RESULT: path'),
    or the format of the serial set ('== time [key] python ...', then a 'RESULT: path' line)."""
    head, items, by_key, cur = "", [], {}, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# Regression"):
            head = line
        elif line.startswith("== "):
            m = re.match(r"== (\d\d:\d\d:\d\d) \[([^\]]+)\] (?:w(\d+) )?(.*)", line)
            if m:
                cur = {"time": m.group(1), "key": m.group(2), "worker": m.group(3), "cmd": m.group(4), "result": None, "path": None}
                items.append(cur)
                by_key[cur["key"]] = cur
        elif line.startswith("-- "):
            m = re.match(r"-- (\d\d:\d\d:\d\d) \[([^\]]+)\] (PASS|FAIL|\d+ FAIL|COULD NOT RUN|STOPPED)[^:]*:? ?(.*)", line)
            if m:
                it = by_key.get(m.group(2))
                if it is None:
                    it = {"time": m.group(1), "key": m.group(2), "worker": None, "cmd": "", "result": None, "path": None}
                    items.append(it)
                    by_key[it["key"]] = it
                it["result"], it["path"] = m.group(3), m.group(4).strip()
        elif cur is not None and cur["result"] is None and re.match(r"(PASS|FAIL|\d+ FAIL|COULD NOT RUN|STOPPED)\b", line):
            r = re.match(r"(PASS|FAIL|\d+ FAIL|COULD NOT RUN|STOPPED)[^:]*:? ?(.*)", line)
            cur["result"], cur["path"] = r.group(1), r.group(2).strip()
    last = {}  # an item that ran again after a hang ("RETRY after HANG FAIL"): only its last run counts
    for it in items:
        last[it["key"]] = it
    return head, list(last.values())


def status(path: Path | None) -> int:
    path = path or latest_results()
    if not path or not path.exists():
        print(f"No results file in {REG}.")
        return 1
    head, items = parse_results(path)
    minutes = {k: m for k, _, m, _ in ITEMS}
    print(head or f"Results: {path}")
    print(f"File: {path}")
    for it in items:
        res = it["result"] or "running"
        print(f"  {it['time']}  {res:<14} {it['key']:<16} {('w' + it['worker']) if it['worker'] else '  '}  {it['path'] or ''}")
    done = [it for it in items if it["result"]]
    text = path.read_text(encoding="utf-8", errors="replace")
    finished = bool(re.search(r"^(DONE|STOPPED) ", text, re.M))
    print(f"{len(done)} items with a result: {sum(it['result'] == 'PASS' for it in done)} pass, "
          f"{sum(it['result'] != 'PASS' for it in done)} not passed" + ("; the set has ended." if finished else "."))
    if finished:
        return 0
    planned = re.search(r"items ([\w,:]+);", head)
    if planned:
        seen = {it["key"].split(":")[0] for it in items}
        left = [k for k in planned.group(1).split(",") if k not in seen]
        if left:
            print(f"Not started: {', '.join(left)} (typical {sum(minutes.get(k, 15) for k in left)} min one at a time)")
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if state and not pid_alive(state.get("pid")):
        print(f"Warning: the set's process {state.get('pid')} has ended without DONE or STOPPED. Its items or games may "
              "still run: check them (regression.py stop shows what it would close).")
    for key, j in state.get("jobs", {}).items():
        w = j.get("worker")
        change = gamepool.last_log_change(w) if w else None
        print(f"  now: {key} on worker {w}, {((time.time() - j.get('started', time.time())) / 60):.0f} min; game "
              f"{gamepool.game_pids(w) or 'not running'}; turn {gamepool.last_turn(w) or '-'}; logs changed "
              f"{f'{change:.1f} min ago' if change is not None else '-'}"
              + ("  <- no change for 10 min: the runner closes the game as a hang" if change and change >= 10 else ""))
    return 0


def stop(yes: bool) -> int:
    if not STATE.exists():
        print(f"No regression set runs (no {STATE}). Nothing to stop.")
        return 0
    state = json.loads(STATE.read_text(encoding="utf-8"))
    jobs = state.get("jobs", {})
    print(f"Set {Path(state['results']).name} (process {state.get('pid')}): {len(jobs)} items run.")
    for key, j in jobs.items():
        games = gamepool.game_pids(j["worker"]) if j.get("worker") else []
        print(f"  {'close' if yes else 'would close'} [{key}]: process {j.get('pid')} and its child processes; "
              f"worker {j.get('worker')} game {games or 'none'}")
    if not yes:
        print("Dry run. Add --yes to stop the set.")
        return 0
    STOP_FILE.write_text(f"stop requested {datetime.now():%H:%M:%S}", encoding="utf-8")
    for key, j in jobs.items():
        if pid_alive(j.get("pid")):
            subprocess.run(["taskkill", "/PID", str(j["pid"]), "/T", "/F"], capture_output=True)
        if j.get("worker"):
            gamepool.stop(j["worker"])
    deadline = time.time() + 60
    while time.time() < deadline and pid_alive(state.get("pid")):
        time.sleep(2)
    if pid_alive(state.get("pid")):
        print("The set's process still runs; it ends after its next check.")
    else:
        STOP_FILE.unlink(missing_ok=True)
        print("Stopped.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run", "status", "rerun", "stop", "_play"])
    ap.add_argument("results", nargs="?", type=Path, help="status/rerun: a results file (default: the newest)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"games at once (default {DEFAULT_WORKERS})")
    ap.add_argument("--worker", type=int, help=argparse.SUPPRESS)  # _play
    ap.add_argument("--only", help="comma-separated item keys")
    ap.add_argument("--skip", help="comma-separated item keys to leave out")
    ap.add_argument("--prev", help="the previous release tag for the save test (default: the newest v* tag not at HEAD)")
    ap.add_argument("--fresh-saves", action="store_true", help="play the previous release again for new saves")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    keys_all = [k for k, _, _, _ in ITEMS]
    if a.cmd == "_play":
        return play_previous(a.prev, a.worker)
    if a.list or not a.cmd:
        for k, c, m, why in ITEMS:
            print(f"{k:<12} {m:>3} min  {why}\n{'':18}{'' if c.startswith('(') else 'python '}{c}")
        jobs, _ = jobs_for(keys_all, prev_tag(), False, True)
        print(f"\nAll: about {sum(m for _, _, m, _ in ITEMS)} min one at a time; about {estimate(jobs, a.workers):.0f} min "
              f"on {a.workers} workers (typical times; games that run together are a little slower). Results: {REG}\\<stamp>.txt")
        return 0
    if a.cmd == "status":
        return status(a.results)
    if a.cmd == "stop":
        return stop(a.yes)
    if a.cmd == "rerun":
        src = a.results or latest_results()
        if not src or not src.exists():
            print("No results file to rerun.")
            return 2
        head, items = parse_results(src)
        keys = []
        for it in items:
            base = "saves" if it["key"].startswith("saves") else it["key"]
            if it["result"] != "PASS" and base in keys_all and base not in keys:
                keys.append(base)
        planned = re.search(r"items ([\w,:]+);", head)  # a stopped set: the items it did not reach
        seen = {("saves" if it["key"].startswith("saves") else it["key"]) for it in items}
        keys += [k for k in (planned.group(1).split(",") if planned else []) if k not in seen and k not in keys]
        if not keys:
            print(f"Every item in {src.name} passed. Nothing to run again.")
            return 0
    else:
        keys = a.only.split(",") if a.only else keys_all
        keys = [k for k in keys if not a.skip or k not in a.skip.split(",")]
    bad = [k for k in keys if k not in keys_all]
    if bad:
        ap.error(f"unknown item(s) {bad}; see --list")
    if a.workers < 1:
        ap.error("--workers: 1 or more")
    if not a.dry_run:
        if STATE.exists() and pid_alive(json.loads(STATE.read_text(encoding="utf-8")).get("pid")):
            print(f"A regression set runs already ({STATE}). Use status or stop.")
            return 2
        problems = []
        if gamepool.other_games():
            problems.append(f"a game runs that no worker started (process {gamepool.other_games()}): if the user plays, do "
                            "not start a test; close a serial test game first")
        if gamepool.worker_games():
            problems.append(f"worker games from an earlier set still run ({gamepool.worker_games()}): "
                            "python gamepool.py stop <worker>")
        if not gamepool.steam_running():
            problems.append("the Steam client does not run (the game needs it)")
        docs = gamepool.documents_state(1)
        if not docs["ok"] and (a.workers > 1 or os.environ.get("CIV7_ALLOW_SHARED_SAVES") != "1"):
            problems.append(f"{docs['reason']}. {gamepool.SETUP_HINT}")
        if problems:
            print("NOT STARTED:\n" + "\n".join(f"- {p}" for p in problems))
            return 2
        REG.mkdir(parents=True, exist_ok=True)
    results = REG / f"{datetime.now():%Y%m%d-%H%M%S}.txt"
    prev = a.prev or (prev_tag() if "saves" in keys else None)
    jobs, notes = jobs_for(keys, prev, a.fresh_saves, a.dry_run)
    return Runner(results, a.workers, a.dry_run).run(jobs, notes, keys)


if __name__ == "__main__":
    sys.exit(main())
