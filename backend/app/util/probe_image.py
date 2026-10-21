"""**The image** used by "Test" in the "vision" field of the settings page (P23 #4).

P19 wired "Test" into every field, but the vision field went through the same probe as the writing model -
only `GET /models` (or one text-only completion). **That "connected" proves nothing about vision**: a
text-only model passes as is, and the user only finds out it cannot read images after saving, when they
click "image to table".

So this image is not decoration: it **has a three-digit number written on it**, the probe asks the model
to read the number, and only reading it right passes. (Asking "what colour is this" does not work - a text-only
model guessing "white" gets lucky; a three-digit number is guessed with probability 1/900.)

The image is drawn here on the spot, not stored in the repo, and never captures the user's screen:
  - a screenshot would send whatever is on the user's desktop, and this field is exactly the entry point of
    the "where do screenshots go" promise - using a real screenshot as a probe means breaking the privacy
    promise once in order to verify it;
  - a png in the repo needs someone to remember it pairs with this code (`desktop/build/icon.png` is the icon,
    not the probe image). Drawn with pure stdlib (zlib + struct); the glyphs are right below, changing the number is one line.
"""

from __future__ import annotations

import struct
import zlib


# guessing it blindly goes from 1/900 to 1/90. In this 5x7 dot matrix the "3" was once read as "2"

# three-digit 1/900 guess rate, and the current real endpoint already reads it right.
PROBE_NUMBER = "728"

# 5x7 dot matrix, digits only. Five characters per row, `#` is ink.
_FONT: dict[str, tuple[str, ...]] = {
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
}

_SCALE = 10          # how large one dot-matrix pixel is drawn
_PAD = 10            # margin all around (dot-matrix pixels)
_GAP = 1             # letter spacing (dot-matrix pixels)


def _bitmap(text: str) -> list[list[int]]:
    glyphs = [_FONT[ch] for ch in text if ch in _FONT]
    if not glyphs:
        raise ValueError(f"no glyph for: {text!r}")
    w = sum(len(g[0]) for g in glyphs) + _GAP * (len(glyphs) - 1) + _PAD * 2
    h = len(glyphs[0]) + _PAD * 2
    grid = [[0] * w for _ in range(h)]
    x = _PAD
    for g in glyphs:
        for r, row in enumerate(g):
            for c, ch in enumerate(row):
                if ch == "#":
                    grid[_PAD + r][x + c] = 1
        x += len(g[0]) + _GAP
    return grid


def _png(grid: list[list[int]], scale: int = _SCALE) -> bytes:
    """8-bit grayscale PNG. Ink = 0 (black), background = 255 (white) - maximum contrast, still readable when scaled down."""
    h, w = len(grid) * scale, len(grid[0]) * scale
    raw = bytearray()
    for row in grid:
        line = bytes(0 if px else 255 for px in row for _ in range(scale))
        for _ in range(scale):
            raw += b"\x00" + line          # one filter byte in front of each row (0 = None)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def probe_png(text: str = PROBE_NUMBER) -> bytes:
    """A black-and-white PNG with `text` written on it (`PROBE_NUMBER` by default)."""
    return _png(_bitmap(text))
