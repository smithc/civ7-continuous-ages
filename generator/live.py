"""Live tests: drive a running Civilization VII game from Python, without a human.

The game serves a Chrome DevTools Protocol endpoint for its UI view on port 9444 (AppOptions.txt
"UIDebugger", on by default; no option change, no effect on achievements). Runtime.evaluate runs JavaScript
in the UI context, the same context as the game's own screens and the automation tests. There is no channel
into the gameplay script context: state changes go through the operations the UI sends (the game's tuner
panels use the same calls).

The test build (build_mod.py --install --checks) has the automation test "CALive" (checks/ca-automation.js):
it sets up and hosts a game from a suite (autoplay/ContinuousAgesLive.json: civs, seeds, map, HumanPlayers=1)
and leaves slot 0 to the script. In the game, globalThis.caLive has the helpers: advance(n) (the AI plays
slot 0 for n turns), endTurn(), canTrain(unit), grantNode(node), createUnit(type, x, y), log(record),
finish(ok, message).

Commands (in generator/):
  python live.py start [--suite ContinuousAgesLive.json] [--set Player0Civ=CIVILIZATION_MUGHAL ...]
  python live.py wait [--timeout 600]            until the game runs and caLive is ready
  python live.py eval "Game.turn" "GameContext.localPlayerID"
  python live.py eval --file scenarios/x.js      the file is the body of an async function
  python live.py quit                            ends the test (QuitApp closes the game)
  python live.py scenario scenarios/x.js [--suite ...] [--set ...]   start, wait, run, quit, report
  python live.py all [--only meet]               every scenario in scenarios/scenarios.json, one game each
A scenario file returns {ok: true|false, ...}; its result and the [CA-CHECK][SCENARIO] records go to
build/scenarios/<time>/REPORT.md with a copy of the logs. Exit code: 0 pass, 1 fail, 2 could not run.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
HOST, PORT = "127.0.0.1", 9444
STEAM = r"C:\Program Files (x86)\Steam\steam.exe"
APP_ID = 1295660
LOGS = Path.home() / "AppData" / "Local" / "Firaxis Games" / "Sid Meier's Civilization VII" / "Logs"
STATE = REPO / "build" / "live" / "state.json"


# -- Chrome DevTools Protocol client (standard library) -------------------------------------------------
def targets(timeout: float = 3) -> list:
    with urllib.request.urlopen(f"http://{HOST}:{PORT}/json/list", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ws_path(target: dict) -> str:
    # Cohtml 2.2 puts the request path into webSocketDebuggerUrl; the frontend URL has the right one.
    ws = urllib.parse.parse_qs(urllib.parse.urlparse(target.get("devtoolsFrontendUrl", "")).query).get("ws", [None])[0]
    return "/" + ws.split("/", 1)[1] if ws else f"/devtools/page/{target['id']}"


class WebSocket:
    def __init__(self, path: str, timeout: float):
        self.sock = socket.create_connection((HOST, PORT), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("closed during handshake")
            head += chunk
        status, _, self.buf = head.partition(b"\r\n\r\n")
        if b" 101 " not in status.split(b"\r\n")[0]:
            raise ConnectionError("handshake failed: " + status.decode(errors="replace"))

    def _exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("socket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self, opcode: int, data: bytes) -> None:
        n, mask = len(data), os.urandom(4)
        hdr = bytearray([0x80 | opcode])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(bytes(hdr) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def send(self, text: str) -> None:
        self._frame(0x1, text.encode("utf-8"))

    def recv(self) -> str:
        message = b""
        while True:
            b1, b2 = self._exact(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            mask = self._exact(4) if b2 & 0x80 else None
            payload = self._exact(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            opcode = b1 & 0x0F
            if opcode == 0x9:
                self._frame(0xA, payload)
            elif opcode == 0x8:
                raise ConnectionError("the game closed the connection")
            elif opcode in (0x0, 0x1, 0x2):
                message += payload
                if b1 & 0x80:
                    return message.decode("utf-8", errors="replace")

    def close(self) -> None:
        try:
            self._frame(0x8, b"")
        finally:
            self.sock.close()


def evaluate(expression: str, timeout: float = 60, is_async: bool = False) -> dict:
    """Evaluates in the game's UI view. is_async: the expression is the body of an async function."""
    if is_async:
        expression = f"(async () => {{\n{expression}\n}})()"
    # The game's inspector server drops a connection now and then when calls come quickly: retry.
    for attempt in range(6):
        try:
            t = targets()
            if not t:
                raise ConnectionError("no inspector target")
            ws = WebSocket(ws_path(t[0]), timeout)
            break
        except (OSError, ConnectionError):
            if attempt == 5:
                raise
            time.sleep(1 + attempt)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expression, "returnByValue": True, "awaitPromise": True}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                break
    finally:
        ws.close()
    if "error" in msg:
        return {"ok": False, "error": msg["error"]}
    res = msg["result"]
    if "exceptionDetails" in res:
        ex = res["exceptionDetails"]
        return {"ok": False, "error": ex.get("exception", {}).get("description") or ex.get("text")}
    v = res["result"]
    return {"ok": True, "value": v.get("value", v.get("description"))}


# -- the game process ----------------------------------------------------------------------------------
def game_pids() -> list[int]:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Civ7_Win64_DX12_FinalRelease.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return [int(m.group(1)) for m in re.finditer(r'"Civ7_Win64_DX12_FinalRelease\.exe","(\d+)"', out)]


def write_suite(suite: str, sets: list[str]) -> Path:
    """The suite with parameter overrides (Key=Value) in its first test, as UTF-8 without a BOM."""
    text = (HERE / "autoplay" / suite).read_text(encoding="utf-8")
    for kv in sets:
        key, value = kv.split("=", 1)
        if re.search(rf"\b{re.escape(key)}=[^,}}]*", text):
            text = re.sub(rf"\b{re.escape(key)}=[^,}}]*", f"{key}={value}", text, count=1)
        else:
            text = re.sub(r"(Test=\w+)", rf"\1, {key}={value}", text, count=1)
    path = Path(tempfile.gettempdir()) / suite
    path.write_bytes(text.encode("utf-8"))
    return path


MANUAL_DEFAULTS = {"StartAge": "AGE_ANTIQUITY", "MapSeed": "4242", "GameSeed": "4242", "Player0Civ": "CIVILIZATION_EGYPT",
                   "Player1Civ": "CIVILIZATION_PERSIA", "Player2Civ": "CIVILIZATION_GREECE", "Player3Civ": "CIVILIZATION_HAN",
                   "Player4Civ": "CIVILIZATION_ROME", "Player5Civ": "CIVILIZATION_MAYA"}


def start(suite: str, sets: list[str], manual: bool = False) -> int:
    """Starts the game. With a suite (the default), the automation test CALive sets up and hosts the game. With
    manual, the game starts at its main menu without automation, and host_game() sets up a normal game."""
    if game_pids():
        print("Civilization VII is running. Close it first (or use the running game: wait / eval).")
        return 2
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"started": time.time(), "suite": None if manual else suite, "sets": sets, "manual": manual}),
                     encoding="utf-8")
    if manual:
        # LIVE_PLAIN_LAUNCH=1: without -bypassStartButton, exactly as a player starts the game.
        flags = [] if os.environ.get("LIVE_PLAIN_LAUNCH") == "1" else ["-bypassStartButton"]
        subprocess.Popen([STEAM, "-applaunch", str(APP_ID)] + flags)
        print(f"started: main menu (manual{', plain launch' if not flags else ''})")
        return 0
    path = write_suite(suite, sets)
    subprocess.Popen([STEAM, "-applaunch", str(APP_ID), "-autojson", str(path), "-bypassStartButton"])
    print(f"started: suite {path}")
    return 0


def manual() -> bool:
    return STATE.exists() and json.loads(STATE.read_text(encoding="utf-8")).get("manual", False)


def ensure_helpers() -> None:
    """The live helpers (checks/ca-live.js) in the game's page, marked ready. A normal game has no automation test to
    load them, and each load or world transition makes a new page."""
    evaluate((HERE / "checks" / "ca-live.js").read_text(encoding="utf-8") + "\n;globalThis.caLive.ready = true; true", timeout=30)


def host_game(sets: list[str], timeout: float = 300) -> dict:
    """At the main menu of a game started without automation: a new game with the given settings (Key=Value, as in
    a suite: StartAge, MapSeed, GameSeed, Player<i>Civ), hosted as the automation's PlayGame does
    (Configuration, then Network.hostGame once GameSetup has taken the changes). Slot 0 is the human."""
    values = dict(MANUAL_DEFAULTS, **dict(kv.split("=", 1) for kv in sets))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            t = targets()
            if t and t[0]["url"].endswith("root-shell.html") and evaluate(
                    "typeof Configuration !== 'undefined' && typeof Network !== 'undefined' && UI.isInShell()", timeout=10).get("value") is True:
                break
        except (OSError, ConnectionError, ValueError):
            pass
        time.sleep(3)
    else:
        return {"ok": False, "error": "the main menu did not come"}
    time.sleep(8)  # the main menu finishes loading its screens
    players = "".join(f"Configuration.editPlayer({k[6:-3]}).setCivilizationTypeName({json.dumps(v)});"
                      for k, v in values.items() if re.fullmatch(r"Player\d+Civ", k))
    setup = ("(() => { Configuration.editGame().reset(); const g = Configuration.editGame(), m = Configuration.editMap();"
             f" g.setStartAgeType({json.dumps(values['StartAge'])}); m.setMapSeed({int(values['MapSeed'])}); g.setGameSeed({int(values['GameSeed'])});"
             f" {players} return GameSetup.currentRevision; }})()")
    r = evaluate(setup, timeout=30)
    if not r.get("ok"):
        return r
    rev = r["value"]
    for _ in range(60):
        if evaluate("GameSetup.currentRevision", timeout=10).get("value") != rev:
            break
        time.sleep(1)
    return evaluate("(Network.hostGame(ServerType.SERVER_TYPE_NONE), { ok: true, revision: GameSetup.currentRevision })", timeout=30)


def wait(timeout: float, expr: str = "globalThis.caLive?.ready === true && typeof Game !== 'undefined' && Game.turn >= 1") -> bool:
    if manual() and expr.startswith("globalThis.caLive?.ready"):
        expr = "typeof Game !== 'undefined' && Game.turn >= 1"
    deadline, last = time.time() + timeout, None
    while time.time() < deadline:
        try:
            t = targets()
            url = t[0]["url"] if t else None
            if url and url.endswith("root-game.html") and evaluate(expr, timeout=10).get("value") is True:
                if manual():
                    time.sleep(5)  # the game's screens finish loading
                    ensure_helpers()
                if STATE.exists():  # the game this tool started: quit may close only these processes
                    state = json.loads(STATE.read_text(encoding="utf-8"))
                    state.setdefault("pids", game_pids())
                    STATE.write_text(json.dumps(state), encoding="utf-8")
                return True
            last = url
        except (OSError, ConnectionError, ValueError):
            last = "no endpoint yet"
        time.sleep(3)
    print(f"timed out; last state: {last}")
    return False


def quit_game(timeout: float = 120) -> None:
    try:
        evaluate("typeof globalThis.caLive?.finish === 'function' ? globalThis.caLive.finish(true, 'live.py quit') : engine.call('exitToDesktop')",
                 timeout=10)
    except (OSError, ConnectionError, ValueError):
        pass
    deadline = time.time() + timeout
    while time.time() < deadline and game_pids():
        time.sleep(3)
    if game_pids():
        # Only a game that this tool started (its process ids are in the state file); never a user's game.
        mine = set(json.loads(STATE.read_text(encoding="utf-8")).get("pids", [])) if STATE.exists() else set()
        for pid in set(game_pids()) & mine:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            print(f"the game did not quit by itself: closed process {pid}")
    if STATE.exists() and not game_pids():
        STATE.unlink()


def choose_civ(civ: str | None, timeout: float = 300) -> dict:
    """In the shell's civ selection screen of a world transition: slot 0's choice, as the screen makes it
    (age-transition-civ-select.js startGame: PlayerCivilization, then startGame). civ None keeps the civ."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            t = targets()
            if t and t[0]["url"].endswith("root-shell.html") and evaluate(
                    "typeof GameSetup !== 'undefined' && !!GameSetup.findPlayerParameter(GameContext.localPlayerID, 'PlayerCivilization')",
                    timeout=10).get("value") is True:
                break
            # The next age loaded without the screen: the game chose slot 0's civ itself.
            if t and t[0]["url"].endswith("root-game.html") and evaluate(
                    "typeof Game !== 'undefined' && Game.turn === 1", timeout=10).get("value") is True:
                civ_now = evaluate("GameInfo.Civilizations.lookup(Players.get(GameContext.localPlayerID).civilizationType)?.CivilizationType",
                                   timeout=10).get("value")
                return {"ok": False, "error": "the game made the transition itself: no civ selection screen", "civ": civ_now}
        except (OSError, ConnectionError, ValueError):
            pass
        time.sleep(2)
    else:
        return {"ok": False, "error": "the civ selection screen did not come"}
    time.sleep(5)  # the screen builds its cards
    pick = json.dumps(civ) if civ else "GameSetup.findPlayerParameter(GameContext.localPlayerID, 'PlayerCivilization').value.value"
    return evaluate("(() => { const id = GameContext.localPlayerID; const p = GameSetup.findPlayerParameter(id, 'PlayerCivilization');"
                    " const valid = (p.domain?.possibleValues ?? []).filter((v) => (v.invalidReason ?? 0) == 0).map((v) => v.value?.toString());"
                    f" const civ = {pick}; GameSetup.setPlayerParameterValue(id, 'PlayerCivilization', civ); engine.call('startGame');"
                    " return { civ, valid }; })()", timeout=30)


def run_phases(file: Path, timeout: float) -> tuple[dict, list]:
    """A scenario file can have phases, separated by lines that start with '//// PHASE'. A phase that returns
    {transition: {civ}} has called caLive.transition(): the civ is chosen in the shell, the new age loads, and
    the next phase runs with globalThis.caPrev = the earlier phases' results."""
    phases = re.split(r"(?m)^//// PHASE.*$", file.read_text(encoding="utf-8"))
    results = []
    for i, code in enumerate(phases):
        if i > 0:
            last = results[-1].get("value") if results[-1].get("ok") else None
            if not (isinstance(last, dict) and last.get("transition") is not None):
                return {"ok": False, "error": f"phase {i} did not end with a transition"}, results
            chosen = choose_civ((last["transition"] or {}).get("civ"))
            results.append({"ok": chosen.get("ok", False), "value": {"ok": chosen.get("ok", False), "choose": chosen.get("value"), "phase": f"{i}-shell"}})
            if not chosen.get("ok") or not wait(900):
                return {"ok": False, "error": f"the new age did not load after phase {i}", "choose": chosen}, results
            prev = [r.get("value") for r in results]
            evaluate(f"globalThis.caPrev = {json.dumps(prev)}; true", timeout=10)
        results.append(evaluate(code, timeout=timeout, is_async=True))
        if not results[-1].get("ok"):
            break
    final = results[-1]
    values = [r.get("value") for r in results if r.get("ok")]
    if final.get("ok") and isinstance(final.get("value"), dict):
        ok = all(isinstance(v, dict) and v.get("ok") is not False for v in values) and final["value"].get("ok") is True
        return {"ok": True, "value": {**final["value"], "ok": ok, "phases": values if len(phases) > 1 else None}}, results
    return final, results


def scenario(file: Path, suite: str, sets: list[str], timeout: float, is_manual: bool = False) -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = REPO / "build" / "scenarios" / stamp
    out.mkdir(parents=True, exist_ok=True)
    if start(suite, sets, is_manual) != 0:
        return 2
    t0 = time.time()
    result = None
    try:
        hosted = host_game(sets) if is_manual else {"ok": True}
        if not hosted.get("ok"):
            result = {"ok": False, "error": "could not host the game", "host": hosted}
        elif not wait(600):
            result = {"ok": False, "error": "the game was not ready in 10 minutes"}
        else:
            result, _ = run_phases(file, timeout)
    except (OSError, ConnectionError, ValueError) as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        quit_game()
    value = result.get("value") if result.get("ok") else None
    passed = bool(result.get("ok")) and isinstance(value, dict) and value.get("ok") is True
    shutil.copytree(LOGS, out / "logs", dirs_exist_ok=True)
    records = [l.split("[CA-CHECK][SCENARIO] ", 1)[1] for l in (out / "logs" / "UI.log").read_text(encoding="utf-8", errors="replace").splitlines()
               if "[CA-CHECK][SCENARIO] " in l] if (out / "logs" / "UI.log").exists() else []
    fails = [l for l in (out / "logs" / "UI.log").read_text(encoding="utf-8", errors="replace").splitlines()
             if "[CA-CHECK][FAIL]" in l or "[CA-CHECK][ERROR]" in l] if (out / "logs" / "UI.log").exists() else []
    passed = passed and not fails
    report = [f"# Scenario {file.name}: {'PASS' if passed else 'FAIL'}", "",
              f"- Suite: {suite} {' '.join(sets)}", f"- Time: {round((time.time() - t0) / 60, 1)} minutes", "",
              "## Result", "", "```json", json.dumps(result, indent=1)[:20000], "```", "",
              "## [CA-CHECK][SCENARIO] records", ""] + [f"- `{r[:900]}`" for r in records] + \
             ["", "## [CA-CHECK][FAIL] and [ERROR] lines", ""] + ([f"- {l[:900]}" for l in fails] or ["- none"])
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    shutil.copy(file, out / file.name)
    print(f"{'PASS' if passed else 'FAIL'}: {out / 'REPORT.md'}")
    return 0 if passed else 1


def install(options: list[str]) -> bool:
    """The test build that a scenario needs (build_mod.py --install --checks plus options, for example
    --age-points 8 for a scenario through world transitions)."""
    res = subprocess.run([sys.executable, str(HERE / "build_mod.py"), "--install", "--checks"] + options,
                         cwd=HERE, capture_output=True, text=True)
    ok = res.returncode == 0 and "Installed to" in res.stdout
    print(f"build {' '.join(options) or '(default)'}: {'installed' if ok else 'FAILED'}")
    return ok


def run_all(listing: Path, only: str | None) -> int:
    """Every scenario in scenarios/scenarios.json, one game each; a summary in build/scenarios/<time>-all.md.
    An entry's "build" options (default none) are installed first; the list is run in its order, so keep the
    entries of one build together. The default test build is installed again at the end."""
    entries = json.loads(listing.read_text(encoding="utf-8"))
    rows, failed = [], 0
    installed = None
    for e in entries:
        if only and only not in e["file"]:
            continue
        options = e.get("build", [])
        if options != installed:
            if not install(options):
                return 2
            installed = options
        before = set((REPO / "build" / "scenarios").glob("*")) if (REPO / "build" / "scenarios").exists() else set()
        code = scenario(listing.parent / e["file"], e.get("suite", "ContinuousAgesLive.json"), e.get("set", []), e.get("timeout", 1800),
                        e.get("manual", False))
        new = sorted(set((REPO / "build" / "scenarios").glob("*")) - before)
        failed += code != 0
        rows.append(f"| {e['file']} | {' '.join(e.get('set', [])) or '-'} | {'PASS' if code == 0 else 'FAIL' if code == 1 else 'NOT RUN'} | "
                    f"{new[-1].name if new else '-'} | {e.get('proves', '')} |")
    if installed not in (None, []):
        install([])
    out = REPO / "build" / "scenarios" / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-all.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join([f"# Scenario tests: {'PASS' if not failed else f'{failed} FAIL'}", "",
                              "| Scenario | Settings | Result | Run | Proves |", "| --- | --- | --- | --- | --- |"] + rows) + "\n",
                   encoding="utf-8")
    print(f"{'PASS' if not failed else f'{failed} FAIL'}: {out}")
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start"); p.add_argument("--suite", default="ContinuousAgesLive.json"); p.add_argument("--set", action="append", default=[])
    p.add_argument("--manual", action="store_true", help="a normal game without automation: start, then host it with the --set values")
    p = sub.add_parser("wait"); p.add_argument("--timeout", type=float, default=600); p.add_argument("--expr")
    p = sub.add_parser("eval"); p.add_argument("expr", nargs="*"); p.add_argument("--file", type=Path); p.add_argument("--timeout", type=float, default=600)
    p = sub.add_parser("quit"); p.add_argument("--timeout", type=float, default=120)
    p = sub.add_parser("scenario"); p.add_argument("file", type=Path); p.add_argument("--suite", default="ContinuousAgesLive.json")
    p.add_argument("--set", action="append", default=[]); p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--manual", action="store_true", help="a normal game without automation (the human's own screens)")
    p = sub.add_parser("all"); p.add_argument("--list", type=Path, default=HERE / "scenarios" / "scenarios.json")
    p.add_argument("--only", help="run only the scenarios whose file name contains this text")
    a = ap.parse_args()
    if a.cmd == "all":
        return run_all(a.list, a.only)
    if a.cmd == "start":
        code = start(a.suite, a.set, a.manual)
        if code == 0 and a.manual:
            hosted = host_game(a.set)
            print(f"hosted: {hosted}")
            return 0 if hosted.get("ok") else 1
        return code
    if a.cmd == "wait":
        ok = wait(a.timeout, a.expr) if a.expr else wait(a.timeout)
        print("ready" if ok else "not ready")
        return 0 if ok else 1
    if a.cmd == "eval":
        for e in a.expr:
            print(json.dumps(evaluate(e, a.timeout)), flush=True)
        if a.file:
            print(json.dumps(evaluate(a.file.read_text(encoding="utf-8"), a.timeout, is_async=True)), flush=True)
        return 0
    if a.cmd == "quit":
        quit_game(a.timeout)
        return 0
    return scenario(a.file, a.suite, a.set, a.timeout, a.manual)


if __name__ == "__main__":
    sys.exit(main())
