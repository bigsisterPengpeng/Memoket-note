"""**How long** screen activity is kept (`app/journey/retention.py`, round 779 / P21).

Before this the feature **had no retention period**: `FRAME_KEEP_DAYS=3` only covered large frames,
segment descriptions and thumbnails were never deleted - the user's machine piled up, indefinitely, a
written record of "what he did on screen every day", and the informed-choice screen said not a word about it.

Pinned here are the properties **each of which could turn "kept 30 days" into a lie**:
  - an expired day is deleted together with **its memories in the knowledge base** (files only = the sentences are still there, still cited)
  - expired thumbnails must **also wipe `thumb` on the segments** (files only = a page of 404 images)
  - expiry of large frames must not run only "when that day is opened" (measured: 78MB of 09-16 stayed exactly that way)
  - **failing to delete must be loud**: `rmtree(ignore_errors=True)` leaves half a directory and replies "deleted"
  - today's data **must not be touched at all** - the shell is writing into it
"""

from __future__ import annotations

import json
import os
import stat
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.journey import retention as keep


# --- the criterion (pure functions) ---

def test_default_is_not_keep_forever():
    """**The default decides the actual privacy state of most people.** "Keep forever" is an option, not the default."""
    p = keep.Policy()
    assert p.segment_days == 30 and p.thumb_days == 7
    assert keep.FOREVER in keep.SEGMENT_CHOICES and keep.FOREVER in keep.THUMB_CHOICES
    assert p.segment_days != keep.FOREVER and p.thumb_days != keep.FOREVER
    # thumbnails (what the screen looked like) are kept shorter than segments (one-sentence
    # descriptions)
    assert p.thumb_days < p.segment_days


def test_expiry_criterion_never_touches_today_or_the_future():
    """The shell is writing into today's data; when the clock was set back, "days in the future" must not be deleted either."""
    today = date(2026, 9, 19)
    p = keep.Policy(segment_days=7, thumb_days=3)
    assert keep.due("2026-09-19", today, p) == (False, False)
    assert keep.due("2026-09-20", today, p) == (False, False)
    assert keep.due("2026-09-18", today, p) == (False, False)      # 1 day
    assert keep.due("2026-09-16", today, p) == (False, True)       # 3 days: only thumbnails deleted
    assert keep.due("2026-09-12", today, p) == (True, False)       # 7 days: the whole day deleted
    assert keep.due('\u4e0d\u662f\u65e5\u671f', today, p) == (False, False)
    # **Second gate**: even if the retention period is negative (a corrupted config file, a future
    # choice written wrong), today's data must not be deleted - beyond the gate in `read_policy`,
    # the criterion itself does not trust that number either.
    assert keep.due("2026-09-19", today, keep.Policy(segment_days=-1, thumb_days=-1)) \
        == (False, False)


def test_keep_forever_deletes_nothing():
    today = date(2026, 9, 19)
    p = keep.Policy(segment_days=keep.FOREVER, thumb_days=keep.FOREVER)
    assert keep.due("2020-01-01", today, p) == (False, False)


def test_bad_retention_falls_back_to_default_not_to_most_permissive(tmp_path):
    """`clamp` would clamp `-1` to 0 = "keep forever" - **interpreting bad data as the most permissive choice**,
    exactly the wrong direction. Hence "not recognized -> back to the default"."""
    (tmp_path / keep.POLICY_FILE).write_text('{"segment_days": -1, "thumb_days": 9999}')
    p = keep.read_policy(tmp_path)
    assert p.segment_days == 30 and p.thumb_days == 7
    (tmp_path / keep.POLICY_FILE).write_text('\u8fd9\u4e0d\u662f json')
    assert keep.read_policy(tmp_path) == keep.Policy()
    # no file at all is the default too
    assert keep.read_policy(tmp_path / '\u6ca1\u6709\u8fd9\u4e2a\u76ee\u5f55') == keep.Policy()


def test_stored_values_only_accept_listed_choices(tmp_path):
    out = keep.write_policy(tmp_path, keep.Policy(segment_days=14, thumb_days=99))
    assert out.segment_days == 14 and out.thumb_days == 7
    assert json.loads((tmp_path / keep.POLICY_FILE).read_text()) == \
        {"segment_days": 14, "thumb_days": 7}


# --- disk sweep ---

def _mkday(root: Path, day: str, *, thumbs=2, frames=1, described=True, report=True) -> Path:
    d = root / day
    (d / "thumbs").mkdir(parents=True)
    (d / "shots").mkdir()
    segs = []
    for i in range(thumbs):
        t = d / "thumbs" / f"{i:03d}.jpg"
        t.write_bytes(b"JPG")
        f = d / "shots" / f"{i:03d}.png"
        seg = {"start": f"{day}T0{i}:00:00Z", "end": f"{day}T0{i}:30:00Z", "app": "Code",
               "title": "", "n": 20, "thumb": str(t), "frames": []}
        if i < frames:
            f.write_bytes(b"PNG")
            seg["frames"] = [str(f)]
        if described:
            seg["desc"] = f'\u6539 capture.ts \u7684\u7b2c {i} \u5904'
            seg["session"] = f"screen-{day.replace('-', '')}-{i:03d}"
        segs.append(seg)
    (d / "segments.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    if report:
        (d / "report.json").write_text('{"report": "# \u4eca\u5929\\n", "report_segments": 2}')
    return d


def _io(root: Path):
    def load(day: str) -> list[dict]:
        try:
            return json.loads((root / day / "segments.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def save(day: str, segs: list[dict]) -> None:
        (root / day / "segments.json").write_text(json.dumps(segs, ensure_ascii=False),
                                                  encoding="utf-8")
    return load, save


def test_expired_day_is_deleted_with_its_knowledge_base_memories(tmp_path):
    """**Deleting files but not facts makes "these records are kept only 30 days" a lie** -
    those sentences are still in the knowledge base, still recalled, still written into the user's documents (section 1 item 5)."""
    old = _mkday(tmp_path, "2026-09-01")
    young = _mkday(tmp_path, "2026-09-18")
    forgotten: list[str] = []
    load, save = _io(tmp_path)

    rep = keep.sweep(tmp_path, keep.Policy(segment_days=7, thumb_days=30), date(2026, 9, 19),
                     load=load, save=save,
                     forget=lambda s: (forgotten.append(s), 2)[1])

    assert not old.exists() and young.exists()
    assert rep.days_removed == ["2026-09-01"]
    assert forgotten == ["screen-20260901-000", "screen-20260901-001"]
    assert rep.facts_removed == 4
    assert rep.failures == []


def test_expired_thumbnails_also_wipe_thumb_on_segments(tmp_path):
    """Deleting only the files without changing the segments leaves `has_thumb` true, and every row of the page
    hangs a 404 `<img>` - which looks broken rather than "expired"."""
    d = _mkday(tmp_path, "2026-09-10")
    load, save = _io(tmp_path)

    rep = keep.sweep(tmp_path, keep.Policy(segment_days=30, thumb_days=7), date(2026, 9, 19),
                     load=load, save=save)

    assert rep.thumbs_removed == 2 and rep.days_removed == []
    assert not (d / "thumbs").exists()
    segs = json.loads((d / "segments.json").read_text())
    assert [s["thumb"] for s in segs] == ["", ""]
    assert [s["desc"] for s in segs] == ['\u6539 capture.ts \u7684\u7b2c 0 \u5904', '\u6539 capture.ts \u7684\u7b2c 1 \u5904']
    assert (d / "report.json").is_file(), "expiring thumbnails must not take this day's daily report with them"


def test_thumbnail_pointing_outside_the_directory_is_not_deleted_but_reported(tmp_path):
    """Segment files are written by the shell. If one was really tampered with, this would be a "delete any file by path" hole."""
    d = _mkday(tmp_path, "2026-09-10", thumbs=1)
    outside = tmp_path / '\u522b\u4eba\u7684\u7167\u7247.jpg'
    outside.write_bytes(b"JPG")
    segs = json.loads((d / "segments.json").read_text())
    segs[0]["thumb"] = str(outside)
    (d / "segments.json").write_text(json.dumps(segs, ensure_ascii=False))
    load, save = _io(tmp_path)

    rep = keep.sweep(tmp_path, keep.Policy(segment_days=30, thumb_days=7), date(2026, 9, 19),
                     load=load, save=save)

    assert outside.exists()
    assert any("not in the directory of 2026-09-10" in f for f in rep.failures)


def test_large_frame_expiry_does_not_only_run_when_the_day_is_opened(tmp_path):
    """`_expire_frames` used to hang only off `GET /day` - **and nobody looks three days back**.
    Measured: the 78MB of large frames of 09-16 stayed exactly that way."""
    d = _mkday(tmp_path, "2026-09-14", thumbs=2, frames=2, described=False)
    load, save = _io(tmp_path)
    big = d / "shots" / "000.png"
    assert big.exists()

    def expire(day: str, segs: list[dict]) -> int:
        n = 0
        for s in segs:
            for f in s.get("frames") or []:
                Path(f).unlink(missing_ok=True)
            if s.get("frames"):
                s["frames"] = []
                s["skip"] = '\u622a\u56fe\u5df2\u8fc7\u671f'
                n += 1
        return n

    rep = keep.sweep(tmp_path, keep.Policy(segment_days=30, thumb_days=30), date(2026, 9, 19),
                     load=load, save=save, expire_frames=expire)

    assert rep.frames_removed == 2 and not big.exists()
    assert json.loads((d / "segments.json").read_text())[0]["skip"] == '\u622a\u56fe\u5df2\u8fc7\u671f'


def test_todays_data_is_never_touched(tmp_path):
    """The shell is writing into today's data."""
    today = date(2026, 9, 19)
    d = _mkday(tmp_path, today.isoformat())
    load, save = _io(tmp_path)
    before = (d / "segments.json").read_text()

    rep = keep.sweep(tmp_path, keep.Policy(segment_days=7, thumb_days=1), today,
                     load=load, save=save)

    assert rep.days_removed == [] and rep.thumbs_removed == 0
    assert (d / "segments.json").read_text() == before
    assert (d / "thumbs" / "000.jpg").exists()


def test_things_that_are_not_dates_are_not_touched(tmp_path):
    """`_tmp` (the original being captured), `on` (the switch), `deny.json` (the deny list) all live at the same level."""
    (tmp_path / "_tmp").mkdir()
    (tmp_path / "_tmp" / "now.png").write_bytes(b"PNG")
    (tmp_path / "on").write_text("1")
    (tmp_path / "deny.json").write_text('{"apps": ["\u6211\u4eec\u516c\u53f8\u90a3\u4e2a\u7cfb\u7edf"]}')
    _mkday(tmp_path, "2026-09-01")
    load, save = _io(tmp_path)

    keep.sweep(tmp_path, keep.Policy(segment_days=7, thumb_days=1), date(2026, 9, 19),
               load=load, save=save)

    assert (tmp_path / "_tmp" / "now.png").exists()
    assert (tmp_path / "on").read_text() == "1"
    assert json.loads((tmp_path / "deny.json").read_text())["apps"] == ['\u6211\u4eec\u516c\u53f8\u90a3\u4e2a\u7cfb\u7edf']


@pytest.mark.skipif(os.geteuid() == 0, reason="root can delete anything")
def test_failing_to_delete_is_loud_never_silent(tmp_path):
    """`shutil.rmtree(ignore_errors=True)` leaves half a directory behind while the caller gets
    "success" - the user pressed "delete". In this feature "I thought it was all deleted" is the one error that must not happen."""
    d = _mkday(tmp_path, "2026-09-01")
    (d / "thumbs").chmod(stat.S_IRUSR | stat.S_IXUSR)      # read-only directory: what is inside cannot be deleted
    load, save = _io(tmp_path)
    try:
        rep = keep.sweep(tmp_path, keep.Policy(segment_days=7, thumb_days=1), date(2026, 9, 19),
                         load=load, save=save)
        assert rep.failures, "cannot delete yet says nothing = silent failure"
        # **files** that cannot be deleted must be reported
        assert any(f.split(": ")[0].endswith(".jpg") for f in rep.failures)
        # **directories** that cannot be deleted must be reported too (reporting only files, nobody
        # says "the directory is still there")
        assert any(f.split(": ")[0].endswith("/thumbs") for f in rep.failures)
        assert rep.days_removed == [], "not fully deleted, so it must not report 'this day was deleted'"
        assert d.exists()
    finally:
        (d / "thumbs").chmod(stat.S_IRWXU)


def test_delete_everything_keeps_settings_not_records(tmp_path):
    """"Delete everything you recorded about me" is not "reset my settings to factory"."""
    _mkday(tmp_path, "2026-09-01")
    _mkday(tmp_path, "2026-09-18")
    (tmp_path / "on").write_text("1")
    (tmp_path / "deny.json").write_text('{"apps": []}')
    keep.write_policy(tmp_path, keep.Policy(segment_days=14, thumb_days=3))
    (tmp_path / "_tmp").mkdir()
    (tmp_path / "_tmp" / "now.png").write_bytes(b"PNG")
    load, _ = _io(tmp_path)
    gone: list[str] = []

    rep = keep.wipe_all(tmp_path, load=load, forget=lambda s: (gone.append(s), 1)[1])

    assert sorted(rep.days_removed) == ["2026-09-01", "2026-09-18"]
    assert len(gone) == 4 and rep.facts_removed == 4
    assert not (tmp_path / "2026-09-01").exists() and not (tmp_path / "2026-09-18").exists()
    assert not (tmp_path / "_tmp").exists()
    assert (tmp_path / "on").exists() and (tmp_path / "deny.json").exists()
    assert keep.read_policy(tmp_path).segment_days == 14


def test_counted_volume_is_the_numbers_shown_to_the_user(tmp_path):
    """"Segments kept 30 days" on its own is an abstract setting; "30 days . now 2 days, 4 segments, some KB"
    is what a user can decide on."""
    _mkday(tmp_path, "2026-09-18")
    _mkday(tmp_path, "2026-09-10", described=False, report=False)
    load, _ = _io(tmp_path)

    u = keep.usage(tmp_path, load)

    assert u.days == 2 and u.segments == 4 and u.described == 2
    assert u.thumbs == 4 and u.reports == 1
    assert u.oldest == "2026-09-10" and u.bytes > 0


# --- routes ---

def _router(tmp_path, monkeypatch):
    """Point the routes at a temporary directory and replace the knowledge base with a countable fake."""
    from app.routers import journey as J

    monkeypatch.setattr(J, "journey_root", lambda: tmp_path)
    monkeypatch.setattr(J, "_swept_at", 0.0)
    gone: list[str] = []
    monkeypatch.setattr(J, "UserMemory", lambda user: type(
        "M", (), {"remove_sessions": lambda self, s: (gone.append(s), 1)[1]})())
    return J, gone


def test_retention_field_also_shows_whats_on_disk_now(tmp_path, monkeypatch):
    """"Segments kept 30 days" on its own is an abstract setting. The decision the user has to make needs a second number."""
    J, _ = _router(tmp_path, monkeypatch)
    _mkday(tmp_path, "2026-09-18")

    out = J.get_retention(user="tester")

    assert out.segment_days == 30 and out.thumb_days == 7
    assert out.frame_days == J.FRAME_KEEP_DAYS == 3
    assert keep.FOREVER in out.segment_choices          # "keep forever" is one of the choices
    assert out.days == 1 and out.segments == 2 and out.thumbs == 2 and out.reports == 1
    assert out.bytes > 0 and out.oldest == "2026-09-18"


def test_shrinking_retention_takes_effect_immediately(tmp_path, monkeypatch):
    """If shrinking it did not take effect immediately, the user changes 30 days to 7 and those days are still on
    the page - he has no way of knowing whether the switch does anything at all."""
    J, gone = _router(tmp_path, monkeypatch)
    # dates follow today: the route computes days from `date.today()`; a hard-coded "2026-09-18"
    # would be swept away once 7 days pass
    old_day = (date.today() - timedelta(days=28)).isoformat()
    old = _mkday(tmp_path, old_day)
    _mkday(tmp_path, (date.today() - timedelta(days=2)).isoformat())

    out = J.put_retention(J.JourneyRetentionIn(segment_days=7, thumb_days=7), user="tester")

    assert not old.exists(), "not swept right after the change = nobody can tell whether the switch took effect"
    assert out.swept["days_removed"] == [old_day]
    assert out.swept["facts_removed"] == 2 and len(gone) == 2
    assert out.days == 1 and out.segment_days == 7
    assert json.loads((tmp_path / keep.POLICY_FILE).read_text())["segment_days"] == 7


def test_delete_everything_includes_knowledge_base_memories(tmp_path, monkeypatch):
    J, gone = _router(tmp_path, monkeypatch)
    _mkday(tmp_path, "2026-09-01")
    _mkday(tmp_path, "2026-09-18")

    out = J.delete_all(user="tester")

    assert sorted(out.swept["days_removed"]) == ["2026-09-01", "2026-09-18"]
    assert len(gone) == 4 and out.swept["facts_removed"] == 4
    assert out.days == 0 and out.segments == 0 and out.bytes == 0
    assert J.days(user="tester") == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root can delete anything")
def test_deleting_a_day_not_fully_must_report_500_not_say_deleted(tmp_path, monkeypatch):
    """It used to be `shutil.rmtree(ignore_errors=True)`: files that were in use stayed on disk,
    while the user got "this day was deleted"."""
    J, _ = _router(tmp_path, monkeypatch)
    d = _mkday(tmp_path, "2026-09-18")
    (d / "thumbs").chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(Exception) as e:
            J.delete_day(date="2026-09-18", user="tester")
        assert 'Could not fully delete' in str(e.value.detail) and "thumbs" in str(e.value.detail)
        assert d.exists()
    finally:
        (d / "thumbs").chmod(stat.S_IRWXU)


def test_turning_the_day_also_sweeps_expired_data(tmp_path, monkeypatch):
    """Cleanup hangs off **the read path**, no separate timer. Hanging it off `/day` is not enough: that endpoint
    only looks at the day the user has open, and nobody looks three days back (measured: 78MB of 09-16 stayed exactly that way)."""
    from app.routers import journey as J

    called: list[str] = []
    monkeypatch.setattr(J, "journey_root", lambda: tmp_path)
    monkeypatch.setattr(J, "_sweep_if_due", lambda user: called.append(user))

    J.days(user="tester")

    assert called == ["tester"]


def test_sweep_runs_every_ten_minutes_not_on_every_poll(tmp_path, monkeypatch, _no_journey_sweep):
    """This page polls every 30 seconds. An `rglob` over the whole root each time trades the user's disk
    for an immediacy nobody needs. (`_no_journey_sweep` hands back **the real one**.)"""
    J, _ = _router(tmp_path, monkeypatch)
    ran: list[int] = []
    monkeypatch.setattr(J, "_sweep", lambda user, policy=None: ran.append(1))

    _no_journey_sweep("tester")
    monkeypatch.setattr(J, "_swept_at", 1e9)      # just swept
    _no_journey_sweep("tester")

    assert len(ran) == 1
