"""**How long** screen activity is kept (docs/daily-journey-plan.md section 1, section 8.3 item 3).

**Why this file exists** (round 779 / P21): before it, the feature **had no retention period**.
`FRAME_KEEP_DAYS=3` only covered the large frame sent to the model; **segment descriptions and thumbnails
were never deleted** - in real data the 38 thumbnails of 09-16 were still there three days later, and so
were the 78MB of large frames of 09-16 (because expiry only ran "when that day was opened", and nobody
looks three days back). That means this machine was piling up, indefinitely, a written record of "what this
person did on screen every day", while of the four points on the informed-choice screen **not one told the
user how long it is kept** - plan section 8.3 says five points, and the missing one was exactly this.
**Without the feature, that sentence could not be written**; cleanup first, then the promise.

The chosen defaults and why (real data volumes in docs/daily-journey-plan.md section 1):

  - **Thumbnails 7 days.** They are the evidence for "is this description made up", and that checking
    happens on the day or within a few days - no product path reads thumbnails from two weeks ago.
    Real data: 99-170 per day, 1.2-2.0MB per day; 7 days ~ 700-1200 images ~ 10-14MB.
  - **Segment descriptions 30 days.** Longer than thumbnails, because they are the raw material of the
    "review" path, and much smaller (30-60KB per day, 30 days ~ 1.2MB). **Why exactly 30**: the feature
    itself offers a "last 30 days" review button; a retention period shorter than the longest review
    window the product itself offers would turn that button into a lie.
  - **Large frames still 3 days** (`FRAME_KEEP_DAYS`, unchanged): they are deleted as soon as the
    description is done; 3 days is the window for "the vision endpoint keeps failing to connect".

"Keep forever" is **an option, not the default**: the default decides the actual privacy state of most people.

**Failing to delete must be loud.** Every delete in this layer collects failures into `failures`, which the
UI states verbatim (the "quietly fails to delete" of `shutil.rmtree(ignore_errors=True)` is exactly what
makes users think everything was deleted - the same class of incident as a day growing back after `DELETE /day`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Callable, Iterable

from ..util import i18n

#: "keep forever". 0 rather than None: it must go into json as is, and work directly with
#: `if not days`.
FOREVER = 0

DEFAULT_SEGMENT_DAYS = 30
DEFAULT_THUMB_DAYS = 7

#: the choices in settings. **"Keep forever" is in the list, but is not a default.**
SEGMENT_CHOICES = (7, 14, 30, 90, 180, FOREVER)
THUMB_CHOICES = (1, 3, 7, 14, 30, FOREVER)

POLICY_FILE = "retention.json"


@dataclass(frozen=True)
class Policy:
    """How long to keep. Days = "delete anything older than this many days"; `FOREVER` (0) = keep forever."""

    segment_days: int = DEFAULT_SEGMENT_DAYS
    thumb_days: int = DEFAULT_THUMB_DAYS

    def as_dict(self) -> dict:
        return {"segment_days": self.segment_days, "thumb_days": self.thumb_days}


def _pick(value, choices: Iterable[int], fallback: int) -> int:
    """Only the choices in the list are accepted. **Any odd number falls back to the default**, no clamping -
    `segment_days: -1` clamped to 0 would become "keep forever", interpreting bad data as the most permissive
    choice, exactly the wrong direction."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return n if n in tuple(choices) else fallback


def read_policy(root: Path) -> Policy:
    """Read `<journey root>/retention.json`. Missing / broken both fall back to the default -
    **the default is the conservative choice**; when it cannot be read, better to delete a bit early."""
    try:
        j = json.loads((root / POLICY_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Policy()
    if not isinstance(j, dict):
        return Policy()
    return Policy(
        segment_days=_pick(j.get("segment_days"), SEGMENT_CHOICES, DEFAULT_SEGMENT_DAYS),
        thumb_days=_pick(j.get("thumb_days"), THUMB_CHOICES, DEFAULT_THUMB_DAYS),
    )


def write_policy(root: Path, policy: Policy) -> Policy:
    clean = Policy(
        segment_days=_pick(policy.segment_days, SEGMENT_CHOICES, DEFAULT_SEGMENT_DAYS),
        thumb_days=_pick(policy.thumb_days, THUMB_CHOICES, DEFAULT_THUMB_DAYS),
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / POLICY_FILE).write_text(json.dumps(clean.as_dict(), ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    return clean


def age_days(day: str, today: _date) -> int | None:
    """How many days this day is from today. Returns None for an invalid date (such directories are never touched)."""
    try:
        return (today - _date.fromisoformat(day)).days
    except ValueError:
        return None


def due(day: str, today: _date, policy: Policy) -> tuple[bool, bool]:
    """`(whole day due for deletion, thumbnails due for deletion)`.

    **A pure function; the criterion lives here** - the disk-scanning layer only executes it.
    `age >= days`: `segment_days=7` means "records of the day seven days ago are no longer kept",
    so 09-19 is deleted on 09-26, not 09-25.

    Today and "days in the future" (the clock was set back) are never touched: the shell is writing into today's.
    """
    age = age_days(day, today)
    if age is None or age <= 0:
        return False, False
    seg = bool(policy.segment_days) and age >= policy.segment_days
    thumb = bool(policy.thumb_days) and age >= policy.thumb_days
    # when the whole day is to be deleted there is no need to mention thumbnails separately - they
    # go together
    return seg, (thumb and not seg)


@dataclass
class SweepReport:
    """What one cleanup did. **Failures must reach the UI verbatim.**"""

    days_removed: list[str] = field(default_factory=list)
    thumbs_removed: int = 0
    frames_removed: int = 0
    facts_removed: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def did_something(self) -> bool:
        return bool(self.days_removed or self.thumbs_removed or self.frames_removed)

    def as_dict(self) -> dict:
        return {"days_removed": self.days_removed, "thumbs_removed": self.thumbs_removed,
                "frames_removed": self.frames_removed, "facts_removed": self.facts_removed,
                "failures": self.failures}


def rm_file(p: Path, fails: list[str]) -> bool:
    """Delete one file. **If it cannot be deleted, record a line** (what, why); never swallow it."""
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        fails.append(i18n.msg("{path}: {error}", path=p, error=exc.strerror or exc))
        return False


def rm_tree(d: Path, fails: list[str]) -> bool:
    """Delete a whole directory, **bottom up, one by one**, recording a line for each thing that cannot be deleted.

    Not `shutil.rmtree(ignore_errors=True)`: that quietly leaves half a directory behind when it cannot delete,
    while the caller gets "success". The user pressed "delete"; failing to delete must be said.
    """
    if not d.exists():
        return True
    ok = True
    for p in sorted(d.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        if p.is_dir():
            try:
                p.rmdir()
            except OSError as exc:
                fails.append(i18n.msg("{path}: {error}", path=p, error=exc.strerror or exc))
                ok = False
        elif not rm_file(p, fails):
            ok = ok and not p.exists()
    try:
        d.rmdir()
    except OSError as exc:
        fails.append(i18n.msg("{path}: {error}", path=d, error=exc.strerror or exc))
        ok = False
    return ok


def day_dirs(root: Path) -> list[str]:
    """All directory names under the journey root that "look like a day". `_tmp` / `on` / `deny.json` do not count."""
    try:
        return sorted(d.name for d in root.iterdir()
                      if d.is_dir() and age_days(d.name, _date.today()) is not None)
    except OSError:
        return []


def drop_thumbs(day_dir: Path, segs: list[dict], fails: list[str]) -> int:
    """Delete this day's thumbnails and wipe `thumb` from the segments.

    **Both must be done together**: deleting only the files without changing the segments would hang a 404
    `<img>` on every row of the page (`has_thumb` still true), which looks broken rather than "expired".
    """
    n = 0
    root = day_dir.resolve()
    for seg in segs:
        t = seg.get("thumb")
        if t:
            # **Only delete things inside this day's directory.** Segment files are written by the
            # shell; if one was really tampered with, this would be a "delete any file by path"
            # hole; anything outside the directory is not deleted, but it is reported.
            try:
                p = Path(t).resolve()
                p.relative_to(root)
            except (OSError, ValueError):
                fails.append(i18n.msg("{file}: not in the directory of {day}, not deleted", file=t, day=day_dir.name))
                seg["thumb"] = ""
                continue
            if rm_file(p, fails):
                n += 1
            seg["thumb"] = ""
    # also clear what the segment table does not record (orphan thumbnails left by merging segments)
    sub = day_dir / "thumbs"
    if sub.is_dir():
        for f in sorted(sub.iterdir()):
            if rm_file(f, fails):
                n += 1
        try:
            sub.rmdir()
        except OSError:
            pass          # if something is still there keep it for the next round; rm_file already recorded the real failure
    return n


def sweep(root: Path, policy: Policy, today: _date, *,
          load: Callable[[str], list[dict]],
          save: Callable[[str, list[dict]], None],
          forget: Callable[[str], int] | None = None,
          expire_frames: Callable[[str, list[dict]], int] | None = None) -> SweepReport:
    """Clean up by retention period. **The daily chore hangs off the read path**; no separate timer.

    `forget` means "also delete the memory this segment was extracted into in the knowledge base". **Expiry must
    delete it too**, otherwise "these records are kept only 30 days" is false - the sentences are still in the
    knowledge base, still recalled, still cited. Same promise as `DELETE /day` deleting the facts along with it (section 1 item 5).
    """
    rep = SweepReport()
    for day in day_dirs(root):
        drop_day, drop_thumb = due(day, today, policy)
        d = root / day
        if drop_day:
            segs = load(day)
            if forget:
                for s in segs:
                    if s.get("session"):
                        rep.facts_removed += forget(s["session"])
            if rm_tree(d, rep.failures):
                rep.days_removed.append(day)
            continue
        segs = load(day)
        if not segs:
            continue
        changed = 0
        if expire_frames:
            # Expiry of the large frames (`FRAME_KEEP_DAYS`) used to run only when **that day was
            # opened**, so days nobody looked at kept their full-screen captures (measured: 78MB
            # still there three days after 09-16).
            changed += expire_frames(day, segs)
            rep.frames_removed += changed
        if drop_thumb:
            n = drop_thumbs(d, segs, rep.failures)
            rep.thumbs_removed += n
            changed += n
        if changed:
            save(day, segs)
    return rep


def wipe_all(root: Path, *, load: Callable[[str], list[dict]],
             forget: Callable[[str], int] | None = None) -> SweepReport:
    """**Delete everything**: segments, descriptions, thumbnails, large frames and daily reports of all days, together
    with the memories they were extracted into in the knowledge base.

    Only three things that **are not records** remain: the switch (`on`), the user's own deny list
    (`deny.json`), and the retention period (`retention.json`) - "delete everything you recorded about me"
    is not "reset my settings to factory".
    """
    rep = SweepReport()
    for day in day_dirs(root):
        segs = load(day)
        if forget:
            for s in segs:
                if s.get("session"):
                    rep.facts_removed += forget(s["session"])
        if rm_tree(root / day, rep.failures):
            rep.days_removed.append(day)
    rm_tree(root / "_tmp", rep.failures)
    return rep


@dataclass
class Usage:
    """How much is on disk right now. **Before "delete" it must be possible to say exactly what will be deleted.**"""

    days: int = 0
    segments: int = 0
    described: int = 0
    thumbs: int = 0
    reports: int = 0
    bytes: int = 0
    oldest: str = ""

    def as_dict(self) -> dict:
        return {"days": self.days, "segments": self.segments, "described": self.described,
                "thumbs": self.thumbs, "reports": self.reports, "bytes": self.bytes,
                "oldest": self.oldest}


def usage(root: Path, load: Callable[[str], list[dict]]) -> Usage:
    u = Usage()
    days = day_dirs(root)
    u.days = len(days)
    u.oldest = days[0] if days else ""
    for day in days:
        d = root / day
        segs = [s for s in load(day) if not s.get("deleted")]
        u.segments += len(segs)
        u.described += sum(1 for s in segs if (s.get("desc") or "").strip())
        u.thumbs += sum(1 for s in segs if s.get("thumb"))
        if (d / "report.json").is_file():
            u.reports += 1
        try:
            u.bytes += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        except OSError:
            pass
    return u
