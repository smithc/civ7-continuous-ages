"""Summarize a Civilization VII crash dump without symbols.

Prints the exception, the game-code return addresses found on the crashing
thread's stack, and for each the strings that its function references (which
often names the subsystem, for example RESOURCECLASS_TREASURE).

Usage: python crashstack.py <dump.dmp | submission.pkg> [<game exe>]
A submission.pkg (packagedDumps) holds a JSON catalog with the exception and the call stack;
its frames are named the same way.
Needs: minidump, pefile, capstone (generator/requirements-tools.txt).
"""
import json
import mmap
import re
import struct
import sys

import capstone
import pefile
from minidump.minidumpfile import MinidumpFile

DEFAULT_EXE = (r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VII"
               r"\Base\Binaries\Win64\Civ7_Win64_DX12_FinalRelease.exe")
KNOWN_CODES = {0xC0000005: "ACCESS_VIOLATION", 0xC0000374: "HEAP_CORRUPTION", 0xC0000409: "STACK_BUFFER_OVERRUN",
               0x80000003: "BREAKPOINT", 0xC00000FD: "STACK_OVERFLOW"}


class Image:
    """The game executable on disk, for disassembly and string lookups."""

    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.file = open(path, "rb")  # keep open: the map needs the handle
        self.m = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        self.secs = [(self.base + s.VirtualAddress, s.SizeOfRawData, s.PointerToRawData) for s in self.pe.sections]
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def off(self, va):
        for sva, size, raw in self.secs:
            if sva <= va < sva + size:
                return raw + va - sva
        return None

    def cstr(self, va):
        o = self.off(va)
        if o is None:
            return None
        b = self.m[o:o + 120]
        mt = re.match(rb"[ -~]{4,118}", b)
        return mt.group().decode() if mt and b[len(mt.group()):len(mt.group()) + 1] == b"\0" else None

    def func_start(self, va):
        o = self.off(va)
        i = o
        while i > o - 0x4000:
            if self.m[i - 2:i] == b"\xcc\xcc" and self.m[i] != 0xCC:
                return va - (o - i)
            i -= 1
        return va - 0x200

    def strings_near(self, va, limit=10):
        start = self.func_start(va)
        o = self.off(start)
        found = []
        for ins in self.md.disasm(self.m[o:o + 0x1800], start):
            if ins.address > va + 0x800:
                break
            mt = re.search(r"rip ([+-]) (0x[0-9a-f]+)", ins.op_str)
            if mt:
                t = ins.address + ins.size + int(mt.group(2), 16) * (1 if mt.group(1) == "+" else -1)
                s = self.cstr(t)
                if s and "BuildAgent" not in s:
                    found.append(s)
        return start, list(dict.fromkeys(found))[:limit]


def package(path, exe=DEFAULT_EXE):
    """Crash package from packagedDumps: exception text and named call-stack frames."""
    b = open(path, "rb").read()
    i = b.find(b'{"Catalog"')
    obj, _ = json.JSONDecoder().raw_decode(b[i:].decode("utf-8", "replace"))
    print(" ".join(obj["Exception"]["Message"].split()), "| time", obj.get("Time"))
    mods = [(m["baseAddr"], m["baseAddr"] + m["size"], m["file"].rsplit("\\", 1)[-1]) for m in obj["ModuleInfo"]]
    img = Image(exe)
    all_strings = []
    print("Call stack (game frames named by the strings their function references):")
    for a in obj["Callstack"]:
        name, base = next(((n, b0) for b0, e, n in mods if b0 <= a < e), ("?", 0))
        if name.lower().startswith("civ7"):
            start, strs = img.strings_near(a - base + img.base, 6)
            all_strings += strs
            print(f"  {name}+{a - base:#x} (function ~{start:#x}): {strs}")
        else:
            print(f"  {name}+{a - base:#x}")
    if any(s_.startswith("CAkAudioMgr") for s_ in all_strings):
        print("EXIT CRASH (audio thread): the crashing thread is the Wwise audio manager")


def main(dump, exe=DEFAULT_EXE):
    if dump.lower().endswith(".pkg"):
        return package(dump, exe)
    mf = MinidumpFile.parse(dump)
    rd = mf.get_reader()
    exc = mf.exception.exception_records[0]
    er = exc.ExceptionRecord
    code = er.ExceptionCode_raw
    mods = [(m.baseaddress, m.endaddress, m.name.replace("\\", "/").rsplit("/", 1)[-1]) for m in mf.modules.modules]

    def modof(a):
        for b, e, n in mods:
            if b <= a < e:
                return n, a - b
        return None, None

    n, o = modof(er.ExceptionAddress)
    print(f"Exception {code:#x} ({KNOWN_CODES.get(code, 'unknown')}) at {n}+{o:#x}, "
          f"parameters {[hex(x) for x in er.ExceptionInformation[:er.NumberParameters]]}")
    th = [t for t in mf.threads.threads if t.ThreadId == exc.ThreadId][0]
    data = rd.read(th.Stack.StartOfMemoryRange, th.Stack.MemoryLocation.DataSize)
    img = Image(exe)
    seen = set()
    print("Game functions on the crashing stack (nearest first) and the strings they reference:")
    for off in range(0, len(data) - 8, 8):
        v = struct.unpack_from("<Q", data, off)[0]
        name, rel = modof(v)
        if not name or not name.lower().startswith("civ7") or rel < 0x1000:
            continue
        start, strs = img.strings_near(v)
        if start in seen:
            continue
        seen.add(start)
        print(f"  {v:#x} (function ~{start:#x}): {strs}")
        if len(seen) >= 25:
            break


if __name__ == "__main__":
    main(*sys.argv[1:])
