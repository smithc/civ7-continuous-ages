"""Game workers: several Civilization VII games at once on one PC, each in its own user folders.

A worker is the folder build/workers/w<N>/. Its profile/ folder is a small copy of a Windows user profile. A game
of worker N runs with USERPROFILE, LOCALAPPDATA, APPDATA and TEMP in that folder, so its Logs, Mods, option files,
crash dumps and Saves are its own. A worker draws at minimum graphics quality (WORKER_GRAPHICS: faster turns).
The GPU shader caches are shared with the real user (SHARED_CACHES). The game
finds its folders with SHGetKnownFolderPath, and that call expands %USERPROFILE% from the process environment
(measured 2026-11-01: 4 games at once, each with the same Player_Stats.csv as a game alone). This module knows the
game, not the mod.

The game starts from its executable, not through Steam. The environment variable SteamAppId keeps
SteamAPI_RestartAppIfNecessary (steam_api64.dll) from handing the launch to Steam, as when Steam starts the game.
The Steam client must run and own the game. One Steam client serves every worker.

Saves: the game keeps its saves in Documents\\My Games\\Sid Meier's Civilization VII\\Saves. Windows reads the
Documents folder from HKCU\\...\\Explorer\\User Shell Folders, value "Personal" (and its GUID twin). The Windows
default is %USERPROFILE%\\Documents, which follows a worker. OneDrive's folder backup writes a full path there
(C:\\Users\\<you>\\OneDrive\\Documents), which no environment variable can move: every worker then shares one
Saves folder, and the autosaves of parallel games (AutoSave_<age>_<turn>) overwrite each other. "setup-documents"
writes the same folder as %USERPROFILE%\\OneDrive\\Documents: normal programs still get the same folder, and each
worker gets its own. This is a change to the user's Windows settings, outside the repo: "check" shows the state,
and every worker run checks it before it starts a game (see docs/development.md, "Parallel games").

  python gamepool.py check [--worker N]       is this PC ready for workers (Steam, game, Documents)?
  python gamepool.py setup-documents [--yes]   dry run, or write Documents as %USERPROFILE%\\... (backup first)
  python gamepool.py restore-documents [--yes] write the full path again (the form OneDrive wrote)
  python gamepool.py prepare N [N ...] [--live]  make or refresh worker folders
  python gamepool.py status                    each worker: game process, turn, last log change
  python gamepool.py env N                     PowerShell lines that make this terminal worker N
  python gamepool.py stop N [N ...]            close the game of a worker (only a game that a worker started)
  python gamepool.py reset N [N ...]           delete worker folders (cache junctions first; the caches stay)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
APP_ID = "1295660"
GAME_DIR = Path(os.environ.get("CIV7_GAME_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VII")
BIN = GAME_DIR / "Base" / "Binaries" / "Win64"
EXE_NAME = "Civ7_Win64_DX12_FinalRelease.exe"
GAME_SUBDIR = Path("Firaxis Games") / "Sid Meier's Civilization VII"  # in LocalAppData
SAVES_SUBDIR = Path("My Games") / "Sid Meier's Civilization VII" / "Saves" / "Single"  # in Documents
WORKERS = Path(os.environ.get("CIV7_WORKERS_DIR") or REPO / "build" / "workers")
# The real user, also inside a worker (a worker's environment keeps the real values in CIV7_REAL_*).
REAL_PROFILE = Path(os.environ.get("CIV7_REAL_USERPROFILE") or os.environ.get("USERPROFILE") or Path.home())
REAL_LOCALAPPDATA = Path(os.environ.get("CIV7_REAL_LOCALAPPDATA") or os.environ.get("LOCALAPPDATA")
                         or REAL_PROFILE / "AppData" / "Local")
# Not copied into a new worker: run output, crash dumps, and mods (each run installs its own build).
TEMPLATE_SKIP = {"Logs", "dumps", "packagedDumps", "Mods", "Mods-disabled", "PackageTemp", "PendingPackages"}
# GPU shader caches in LocalAppData. A worker links them (directory junctions) to the real user's folders, so a new
# worker does not compile every shader again (a first start took ~40 s longer with an empty cache; NVIDIA\DXCache
# was 18 GB). Every program on the PC already uses these caches at the same time: the driver and Windows control
# the access. Delete a worker only with "gamepool.py reset": it removes the junctions first (some delete tools
# follow a junction and empty its target).
SHARED_CACHES = ("D3DSCache", "NVIDIA", "AMD")
# Worker graphics: minimum quality. A test game does its turn work once per app tick (frame), so cheaper frames
# make faster turns (GPU study of 2026-11-01, base game, 4 games at once, 100 turns: 1.86 s/turn at High, 1.53 at
# minimum quality; byte-identical CSV logs; GPU memory 4.1 -> 1.5 GB per game). A frame cap does the opposite (60 Hz:
# 16% slower, 30 Hz: 76% slower), so TickIntervalInHZ stays as it is. Only worker files change; the user's game
# keeps its own settings.
WORKER_GRAPHICS = (
    ("Profile", "Minimum"), ("TextureDetail", 0), ("AssetQuality", 0), ("SSAOQuality", 0), ("ShadowQuality", 0),
    ("WaterQuality", 0), ("WaterSunSpecularEnabled", 0), ("VFXQuality", 0), ("TerrainGeometryQuality", 0),
    ("EnableBloom", 0), ("EnableHeightFog", 0), ("EnableLightPointShadowMaps", 0), ("EnableLightPoints", 0),
    ("EnableRefraction", 0), ("EnableSSR", 0), ("EnableSSShadows", 0), ("OverrideRenderScale", 1), ("RenderScale", 0.5))
# Saves without the minimap picture: the game draws it on the GPU for every save, and the rare base-game hang happens
# inside the turn-start autosave (docs/known-limits.md). Not proven to help; it does not change the game state.
WORKER_USER_OPTIONS = (("AddMinimapSnapshotToSaves", 0),)
UI_PORT = 9444  # AppOptions UIDebugger: the first game that starts gets the port; the others run without it
SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
DOCUMENTS_VALUES = ("Personal", "{F42EE2D3-909F-4907-8871-4C22FC0BF756}")
FOLDERID_DOCUMENTS = "FDD39AD0-238F-46AF-ADB4-6C85480369C7"
SETUP_HINT = ("Parallel games need their own Saves folders. Run 'python gamepool.py check' and "
              "'python gamepool.py setup-documents' in generator/ (docs/development.md, Parallel games).")


# -- Folders and environment ----------------------------------------------------------------------------
def worker() -> int | None:
    """The worker of this process (CIV7_WORKER), or None for the real user folders."""
    v = os.environ.get("CIV7_WORKER")
    return int(v) if v and v.isdigit() and int(v) > 0 else None


def worker_dir(n: int) -> Path:
    return WORKERS / f"w{n}"


def profile(n: int | None = None) -> Path:
    return worker_dir(n) / "profile" if n else REAL_PROFILE


def local_appdata(n: int | None = None) -> Path:
    return profile(n) / "AppData" / "Local" if n else REAL_LOCALAPPDATA


def user_data(n: int | None = None) -> Path:
    """The game's user folder (Logs, Mods, option files) of worker n, or of the real user."""
    return local_appdata(n) / GAME_SUBDIR


def logs(n: int | None = None) -> Path:
    return user_data(n) / "Logs"


def pid_file(n: int) -> Path:
    return worker_dir(n) / "game.pid"


def env(n: int, base: dict | None = None) -> dict:
    """The environment of worker n: its own profile folders, the real ones in CIV7_REAL_*, and SteamAppId."""
    e = dict(os.environ if base is None else base)
    p = profile(n)
    e.update({"USERPROFILE": str(p), "LOCALAPPDATA": str(p / "AppData" / "Local"),
              "APPDATA": str(p / "AppData" / "Roaming"), "TEMP": str(p / "Temp"), "TMP": str(p / "Temp"),
              "CIV7_WORKER": str(n), "CIV7_WORKER_DIR": str(worker_dir(n)),
              "CIV7_REAL_USERPROFILE": str(REAL_PROFILE), "CIV7_REAL_LOCALAPPDATA": str(REAL_LOCALAPPDATA),
              "CIV7_GAME_DIR": str(GAME_DIR), "SteamAppId": APP_ID, "SteamGameId": APP_ID})
    return e


def activate_from_argv(argv: list[str] | None = None) -> int | None:
    """'--worker N' in the command line: this process and its child processes use worker N's folders. Call it
    before path constants that use Path.home() or LOCALAPPDATA. Returns the worker (also one set by CIV7_WORKER)."""
    argv = sys.argv if argv is None else argv
    value = None
    for i, a in enumerate(argv):
        if a == "--worker" and i + 1 < len(argv):
            value = argv[i + 1]
        elif a.startswith("--worker="):
            value = a.split("=", 1)[1]
    if value is None:
        return worker()
    if not value.isdigit() or int(value) < 1:
        raise SystemExit(f"--worker {value}: use a number from 1")
    n = int(value)
    for d in (profile(n) / "AppData" / "Local", profile(n) / "AppData" / "Roaming", profile(n) / "Temp"):
        d.mkdir(parents=True, exist_ok=True)
    os.environ.update(env(n))
    return n


# -- Documents (Saves) ------------------------------------------------------------------------------------
_KNOWN_FOLDER = r'''
import ctypes, sys, uuid
guid = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID(sys.argv[1]).bytes_le)
path = ctypes.c_wchar_p()
hr = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0x4000, None, ctypes.byref(path))  # KF_FLAG_DONT_VERIFY
print(path.value if hr == 0 else "ERROR 0x%08x" % (hr & 0xffffffff))
ctypes.windll.ole32.CoTaskMemFree(path)
'''


def documents(n: int | None = None) -> Path:
    """The Documents folder that a game of worker n (or of the real user) gets, from the same Windows call the
    game makes, in a child process with that environment."""
    e = env(n) if n else {**os.environ, "USERPROFILE": str(REAL_PROFILE), "LOCALAPPDATA": str(REAL_LOCALAPPDATA)}
    out = subprocess.run([sys.executable, "-I", "-c", _KNOWN_FOLDER, FOLDERID_DOCUMENTS], env=e,
                         capture_output=True, text=True).stdout.strip()
    if not out or out.startswith("ERROR"):
        raise RuntimeError(f"SHGetKnownFolderPath(Documents) failed: {out or 'no output'}")
    return Path(out)


def saves(n: int | None = None) -> Path:
    return documents(n) / SAVES_SUBDIR


def documents_values() -> dict:
    """The raw (unexpanded) Documents values in the registry: {name: (value, type)}."""
    import winreg
    out = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS) as k:
        for name in DOCUMENTS_VALUES:
            try:
                out[name] = winreg.QueryValueEx(k, name)
            except FileNotFoundError:
                out[name] = (None, None)
    return out


def documents_state(n: int = 1) -> dict:
    """Does worker n get its own Documents? ok: yes; else a reason. Also the raw registry values."""
    real, mine = documents(None), documents(n)
    ok = profile(n).resolve() in [mine.resolve(), *mine.resolve().parents]
    reason = "" if ok else (
        f"worker {n} gets the same Documents as the real user ({mine}): every worker would share one Saves folder, "
        "and the autosaves of parallel games would overwrite each other")
    return {"ok": ok, "real": real, "worker": mine, "reason": reason, "values": documents_values()}


def require_documents(n: int) -> str | None:
    """None when worker n has its own Saves folder; else the message for a run that must not start.
    CIV7_ALLOW_SHARED_SAVES=1 allows a shared Saves folder (one worker at a time only)."""
    st = documents_state(n)
    if st["ok"] or os.environ.get("CIV7_ALLOW_SHARED_SAVES") == "1":
        return None
    return f"NOT READY: {st['reason']}. {SETUP_HINT}"


def setup_documents(yes: bool) -> int:
    import winreg
    values = documents_values()
    real_before = documents(None)
    plan = {}
    for name, (value, kind) in values.items():
        if value is None:
            continue
        if "%USERPROFILE%" in value.upper():
            print(f"{name}: {value} (already follows USERPROFILE)")
            continue
        prefix = str(REAL_PROFILE)
        if not value.lower().startswith(prefix.lower() + "\\"):
            print(f"{name}: {value} is not in the user profile ({prefix}). It cannot follow USERPROFILE: parallel games "
                  "would share one Saves folder. Move Documents into the profile, or run one worker at a time "
                  "(CIV7_ALLOW_SHARED_SAVES=1).")
            return 1
        plan[name] = (value, kind, "%USERPROFILE%" + value[len(prefix):])
    if not plan:
        print("Nothing to change.")
        return 0
    for name, (old, kind, new) in plan.items():
        print(f"{name}: {old}  ->  {new}  (REG_EXPAND_SZ)")
    if not yes:
        print("Dry run. Add --yes to write. Normal programs keep the folder " + str(real_before) + ".")
        return 0
    backup = WORKERS / "documents-registry-backup.json"
    WORKERS.mkdir(parents=True, exist_ok=True)
    if not backup.exists():  # the first backup is the original state: never replace it
        backup.write_text(json.dumps({"saved": datetime.now().isoformat(timespec="seconds"), "key": "HKCU\\" + SHELL_FOLDERS,
                                      "values": {k: list(v) for k, v in values.items()}}, indent=1), encoding="utf-8")
        print(f"Backup: {backup}")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS, 0, winreg.KEY_SET_VALUE) as k:
        for name, (_, _, new) in plan.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_EXPAND_SZ, new)
    after = documents(None)
    if after != real_before:  # must never happen: put the old values back at once
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS, 0, winreg.KEY_SET_VALUE) as k:
            for name, (old, kind, _) in plan.items():
                winreg.SetValueEx(k, name, 0, kind, old)
        print(f"ERROR: normal programs would get {after} instead of {real_before}. The old values are back.")
        return 1
    print(f"Written. Normal programs get {after}; worker 1 gets {documents(1)}.")
    return 0


def restore_documents(yes: bool) -> int:
    """Writes the full path again (the form that OneDrive wrote): the folder that normal programs get now."""
    import winreg
    plan = {}
    for name, (value, kind) in documents_values().items():
        if value and "%USERPROFILE%" in value.upper():
            plan[name] = (value, re.sub("%USERPROFILE%", str(REAL_PROFILE).replace("\\", "\\\\"), value, flags=re.I))
    if not plan:
        print("Nothing to restore: no Documents value uses %USERPROFILE%.")
        return 0
    for name, (old, new) in plan.items():
        print(f"{name}: {old}  ->  {new}")
    if not yes:
        print("Dry run. Add --yes to write.")
        return 0
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS, 0, winreg.KEY_SET_VALUE) as k:
        for name, (_, new) in plan.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_EXPAND_SZ, new)
    print("Written.")
    return 0


# -- Worker folders ---------------------------------------------------------------------------------------
def set_option(path: Path, key: str, value) -> None:
    """Sets an option in one of the game's option files (AppOptions.txt, UserOptions.txt): the file lists every
    option, commented out at its default (';Key value'); this writes 'Key value' in its place."""
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    pattern = re.compile(rf"^[ \t]*;?[ \t]*{re.escape(key)}[ \t]+.*$", re.M)
    if not pattern.search(text):
        raise ValueError(f"{path.name} has no option {key}")
    new = pattern.sub(f"{key} {value}", text, count=1)
    if new != text:
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write(new)


def prepare(n: int, live: bool = False, copy_saves: tuple[str, ...] = ()) -> dict:
    """Makes or refreshes worker n. A new worker gets a copy of the real user's game folder (options, the Mods
    database, legal and account caches; not Logs, dumps or mods). Each call sets UIDebugger (1 only for a live
    game: port 9444 must belong to the game that live.py drives), windowed mode, minimum graphics quality
    (WORKER_GRAPHICS) and saves without a minimap picture (WORKER_USER_OPTIONS), and copies the real saves that
    match copy_saves (for example the test saves CA_*.Civ7Save) into the worker's own Saves folder."""
    src = user_data(None)
    dst = user_data(n)
    for d in (profile(n) / "AppData" / "Local", profile(n) / "AppData" / "Roaming", profile(n) / "Temp"):
        d.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        if not (src / "AppOptions.txt").exists():
            raise RuntimeError(f"No game user folder at {src}: start the game once normally first.")
        shutil.copytree(src, dst, ignore=lambda d, names: [x for x in names if Path(d) == src and x in TEMPLATE_SKIP])
    (dst / "Mods").mkdir(exist_ok=True)
    link_caches(n)
    set_option(dst / "AppOptions.txt", "UIDebugger", 1 if live else 0)
    set_option(dst / "AppOptions.txt", "FullScreen", 0)
    for key, value in WORKER_GRAPHICS:
        set_option(dst / "GraphicsOptions.txt", key, value)
    for key, value in WORKER_USER_OPTIONS:
        set_option(dst / "UserOptions.txt", key, value)
    own = saves(n)
    real = saves(None)
    copied = []
    if own != real:
        (own / "auto").mkdir(parents=True, exist_ok=True)
        for pattern in copy_saves:
            for f in real.glob(pattern):
                t = own / f.name
                if not t.exists() or t.stat().st_mtime < f.stat().st_mtime or t.stat().st_size != f.stat().st_size:
                    shutil.copy2(f, t)
                    copied.append(f.name)
    return {"worker": n, "user_data": dst, "saves": own, "shared_saves": own == real, "copied": copied, "live": live}


def link_caches(n: int) -> list[str]:
    """Links the worker's GPU shader caches to the real user's (SHARED_CACHES). A worker's own cache from before
    is replaced: it holds only compiled shaders."""
    linked = []
    for name in SHARED_CACHES:
        real, link = REAL_LOCALAPPDATA / name, local_appdata(n) / name
        if not real.is_dir() or os.path.isjunction(link):
            continue
        if link.exists():
            shutil.rmtree(link)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"mklink /J {link} {real}: {(r.stdout + r.stderr).strip()}")
        linked.append(name)
    return linked


def reset(n: int) -> None:
    """Deletes worker n's folder: first the cache junctions (os.rmdir removes a junction, not its target)."""
    if game_pids(n):
        raise RuntimeError(f"worker {n}'s game runs: stop it first")
    for name in SHARED_CACHES:
        link = local_appdata(n) / name
        if os.path.isjunction(link):
            os.rmdir(link)
    if worker_dir(n).exists():
        shutil.rmtree(worker_dir(n))


# -- Processes --------------------------------------------------------------------------------------------
def _tasklist(image: str) -> list[tuple[str, int]]:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return [(m.group(1), int(m.group(2))) for m in re.finditer(r'"([^"]+)","(\d+)"', out)]


def game_pids(n: int | None = None) -> list[int]:
    """Running game processes: all of them, or only the one that worker n started (its pid file)."""
    pids = [pid for name, pid in _tasklist("Civ7_Win64_*") if name.lower().startswith("civ7_win64_")]
    if n is None:
        return pids
    pid = read_pid(n)
    return [pid] if pid in pids else []


def read_pid(n: int) -> int | None:
    try:
        return int(json.loads(pid_file(n).read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def worker_games() -> dict[int, int]:
    """{worker: game process} for each worker whose game runs."""
    pids = set(game_pids())
    out = {}
    for d in sorted(WORKERS.glob("w*")):
        if d.name[1:].isdigit():
            pid = read_pid(int(d.name[1:]))
            if pid in pids:
                out[int(d.name[1:])] = pid
    return out


def other_games() -> list[int]:
    """Game processes that no worker started: the user's own game, or a serial (Steam) test game."""
    mine = set(worker_games().values())
    return [p for p in game_pids() if p not in mine]


def steam_running() -> bool:
    return any(name.lower() == "steam.exe" for name, _ in _tasklist("steam.exe"))


def launch(n: int, args: list[str]) -> subprocess.Popen:
    """Starts the game for worker n (the executable, with the worker's environment) and writes its pid file."""
    proc = subprocess.Popen([str(BIN / EXE_NAME), *args], cwd=str(BIN), env=env(n))
    pid_file(n).write_text(json.dumps({"pid": proc.pid, "started": time.time()}), encoding="utf-8")
    return proc


def close_reporters(parent_pid: int) -> list[int]:
    """Closes the crash reporter that one game started (FiraxisCrashReporter.exe stays after the game exits, also
    without a crash; the crash is already saved in the dumps folder). Other games' reporters stay."""
    ps = (f"Get-CimInstance Win32_Process -Filter \"Name='FiraxisCrashReporter.exe' and ParentProcessId={int(parent_pid)}\" | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.isdigit()]


def port_owner(port: int = UI_PORT) -> int | None:
    """The process that listens on a local TCP port, or None."""
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
            return int(parts[4])
    return None


def stop(n: int) -> bool:
    """Closes worker n's game (only the process in its pid file, and only if it still runs)."""
    for pid in game_pids(n):
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        close_reporters(pid)
        return True
    return False


# -- Status -------------------------------------------------------------------------------------------------
def last_turn(n: int | None) -> str | None:
    f = logs(n) / "Player_Stats.csv"
    if not f.exists():
        return None
    with f.open("rb") as h:
        h.seek(max(0, f.stat().st_size - 4000))
        lines = h.read().decode("utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        first = line.split(",", 1)[0].strip()
        if first.isdigit():
            return first
    return None


def last_log_change(n: int | None) -> float | None:
    """Minutes since UI.log or RandCalls.csv changed (the runner's hang check watches the same two files)."""
    times = [p.stat().st_mtime for p in (logs(n) / "UI.log", logs(n) / "RandCalls.csv") if p.exists()]
    return (time.time() - max(times)) / 60 if times else None


def status_lines() -> list[str]:
    games = worker_games()
    lines = []
    for d in sorted(WORKERS.glob("w*"), key=lambda p: int(p.name[1:]) if p.name[1:].isdigit() else 0):
        if not d.name[1:].isdigit():
            continue
        n = int(d.name[1:])
        change = last_log_change(n)
        state = f"game {games[n]}" if n in games else "no game"
        lines.append(f"worker {n}: {state}; turn {last_turn(n) or '-'} (Player_Stats.csv; it restarts in each age); "
                     f"logs changed {f'{change:.1f} min ago' if change is not None else '-'}")
    others = other_games()
    if others:
        lines.append(f"other game processes (not a worker's): {others}")
    return lines or ["No workers yet (build/workers is empty)."]


def check(n: int) -> int:
    ok = True
    exe = BIN / EXE_NAME
    print(f"Game executable: {exe} ({'found' if exe.exists() else 'NOT FOUND (set CIV7_GAME_DIR)'})")
    ok &= exe.exists()
    st = steam_running()
    print(f"Steam client: {'runs' if st else 'NOT RUNNING (start Steam and log in; the game needs it)'}")
    ok &= st
    s = documents_state(n)
    for name, (value, kind) in s["values"].items():
        print(f"Registry {name}: {value}")
    print(f"Documents, normal programs: {s['real']}")
    print(f"Documents, worker {n}: {s['worker']}")
    if s["ok"]:
        print("Saves: each worker has its own Saves folder. Parallel games are possible.")
    else:
        print(f"Saves: NOT READY: {s['reason']}.")
        print("Fix: python gamepool.py setup-documents (dry run), then with --yes. See docs/development.md, Parallel games.")
        ok = False
    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("--worker", type=int, default=1)
    p = sub.add_parser("setup-documents"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("restore-documents"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("prepare"); p.add_argument("workers", type=int, nargs="+"); p.add_argument("--live", action="store_true")
    p.add_argument("--copy-saves", action="append", default=[], help="file pattern in the real Saves\\Single, for example CA_*.Civ7Save")
    sub.add_parser("status")
    p = sub.add_parser("env"); p.add_argument("worker", type=int)
    p = sub.add_parser("stop"); p.add_argument("workers", type=int, nargs="+")
    p = sub.add_parser("reset"); p.add_argument("workers", type=int, nargs="+")
    a = ap.parse_args()
    if a.cmd == "reset":
        for n in a.workers:
            reset(n)
            print(f"worker {n}: deleted {worker_dir(n)} (the shared caches stay)")
        return 0
    if a.cmd == "check":
        return check(a.worker)
    if a.cmd == "setup-documents":
        return setup_documents(a.yes)
    if a.cmd == "restore-documents":
        return restore_documents(a.yes)
    if a.cmd == "prepare":
        for n in a.workers:
            info = prepare(n, a.live, tuple(a.copy_saves))
            print(f"worker {n}: {info['user_data']}; saves {info['saves']}{' (SHARED)' if info['shared_saves'] else ''}; "
                  f"copied {len(info['copied'])} saves; UIDebugger {1 if a.live else 0}")
        return 0
    if a.cmd == "status":
        print("\n".join(status_lines()))
        return 0
    if a.cmd == "env":
        for k, v in env(a.worker, {}).items():
            print(f"$env:{k} = '{v}'")
        return 0
    if a.cmd == "stop":
        for n in a.workers:
            print(f"worker {n}: {'closed its game' if stop(n) else 'no game of this worker runs'}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
