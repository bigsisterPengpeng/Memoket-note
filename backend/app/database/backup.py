"""Automatic backup of the notes library (Trilium has daily / weekly / monthly tiers).

On every backend start, check: if there is no backup today, copy one with sqlite's online backup
API to `backups/notes-YYYYMMDD.sqlite3` (a consistent snapshot, not a bare cp). Keep the latest 7
"daily" and the latest 3 "monthly" (the first one of each month). The knowledge base (KITE's xml,
tens of MB per user) is not handled here yet - that is the next step.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

from ..util.config import get_settings

KEEP_DAILY = 7
KEEP_MONTHLY = 3
_NAME = re.compile(r"^notes-(\d{8})\.sqlite3$")


def backup_dir() -> Path:
    d = Path(get_settings().kite_data_dir) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _existing(d: Path) -> list[tuple[str, Path]]:
    out = []
    for p in d.iterdir():
        m = _NAME.match(p.name)
        if m:
            out.append((m.group(1), p))
    return sorted(out)


def maybe_backup(db_path: Path, today: date | None = None) -> Path | None:
    """Make a backup if there is none today, then prune. Returns the new backup path; None if today already has one."""
    today = today or datetime.now().date()
    stamp = today.strftime("%Y%m%d")
    d = backup_dir()
    target = d / f"notes-{stamp}.sqlite3"
    if target.exists() or not db_path.exists():
        return None
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    prune(d)
    return target


def prune(d: Path) -> list[Path]:
    """Keep the latest KEEP_DAILY, plus the first one of each month (latest KEEP_MONTHLY months). Returns the deleted ones."""
    items = _existing(d)
    keep: set[Path] = {p for _s, p in items[-KEEP_DAILY:]}
    firsts: dict[str, Path] = {}
    for stamp, p in items:                       # sorted ascending by date; the first occurrence is the month's first
        firsts.setdefault(stamp[:6], p)
    for _month, p in sorted(firsts.items())[-KEEP_MONTHLY:]:
        keep.add(p)
    gone = []
    for _s, p in items:
        if p not in keep:
            p.unlink(missing_ok=True)
            gone.append(p)
    return gone


# ---------------------------------------------------------------- knowledge base (KITE codebook)

KEEP_KB_WEEKLY = 2
_KB_NAME = re.compile(r"^codebook-(\d{4}W\d{2})\.xml$")


def maybe_backup_kb(root: Path, today: date | None = None) -> list[Path]:
    """One backup per week of each user's `codebook.xml`: `backups/kb/<user>/codebook-YYYYWww.xml`,
    keeping the latest KEEP_KB_WEEKLY. Tens of MB each, once a week, capped at two - will not fill the disk.
    Copy only the xml itself (.lock / .bak-* are not data)."""
    today = today or datetime.now().date()
    iso = today.isocalendar()
    stamp = f"{iso[0]}W{iso[1]:02d}"
    made: list[Path] = []
    for user_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "backups"):
        src = user_dir / "codebook.xml"
        if not src.is_file():
            continue
        dst_dir = backup_dir() / "kb" / user_dir.name
        dst_dir.mkdir(parents=True, exist_ok=True)
        target = dst_dir / f"codebook-{stamp}.xml"
        if target.exists():
            continue
        shutil.copy2(src, target)
        made.append(target)
        olds = sorted(p for p in dst_dir.iterdir() if _KB_NAME.match(p.name))
        for p in olds[:-KEEP_KB_WEEKLY]:
            p.unlink(missing_ok=True)
    # Also clear backups whose user directory is gone: leftovers like cancel-test and shot-fresh-*

    # directory exists, so their backup stays.
    kb_root = backup_dir() / "kb"
    if kb_root.is_dir():
        alive = {p.name for p in root.iterdir() if p.is_dir()}
        for d in kb_root.iterdir():
            if d.is_dir() and d.name not in alive:
                shutil.rmtree(d, ignore_errors=True)
    return made
