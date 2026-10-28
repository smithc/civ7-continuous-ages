"""Screenshot of the primary screen as PNG, with only the Python standard library (Windows GDI through
ctypes, PNG through zlib). ui_test.py takes one at each [CA-CHECK][UISHOT] marker.

    python tools/screenshot.py out.png [--max-width 1920]
"""
import argparse
import ctypes
import struct
import zlib
from ctypes import wintypes
from pathlib import Path

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
SRCCOPY, CAPTUREBLT, DIB_RGB_COLORS = 0x00CC0020, 0x40000000, 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def grab() -> tuple[int, int, bytes]:
    """(width, height, BGRA rows top to bottom) of the primary screen in physical pixels."""
    user32.SetProcessDPIAware()   # else a scaled display (125%, 150%) gives a part of the screen
    w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, w, h)
    gdi32.SelectObject(memory, bitmap)
    gdi32.BitBlt(memory, 0, 0, w, h, screen, 0, 0, SRCCOPY | CAPTUREBLT)
    info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)   # -h: top-down rows
    pixels = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(memory, bitmap, 0, h, pixels, ctypes.byref(info), DIB_RGB_COLORS)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(None, screen)
    return w, h, pixels.raw


def png(w: int, h: int, bgra: bytes, max_width: int) -> bytes:
    """RGB PNG, scaled down (nearest pixel) to max_width when the screen is wider."""
    step = max(1, -(-w // max_width))
    out_w, out_h = len(range(0, w, step)), len(range(0, h, step))
    rows = []
    for y in range(0, h, step):
        row = bgra[y * w * 4:(y + 1) * w * 4]
        b, g, r = row[0::4 * step], row[1::4 * step], row[2::4 * step]
        rgb = bytearray(out_w * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = r, g, b
        rows.append(b"\x00" + bytes(rgb))
    chunk = lambda kind, data: (struct.pack(">I", len(data)) + kind + data
                                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", out_w, out_h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))


def screenshot(out: Path, max_width: int = 1920) -> tuple[int, int]:
    """Writes the screenshot to out; returns the screen size."""
    w, h, pixels = grab()
    out.write_bytes(png(w, h, pixels, max_width))
    return w, h


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--max-width", type=int, default=1920)
    a = ap.parse_args()
    print(a.out, "%dx%d" % screenshot(a.out, a.max_width))
