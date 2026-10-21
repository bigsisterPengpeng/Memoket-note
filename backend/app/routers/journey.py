"""Opt-in screen-activity capture, retention, status and report endpoints."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date as _date
from datetime import datetime as _dt
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


from ..util import llm
from ..harness import prompts
from ..database import store
from ..database.kite.kite_memory import UserMemory
from ..editor.vision import VisionError, ask_image
from ..journey import day_stats, group_runs, render_time_block
from ..journey import retention as keep
from ..journey.stats import _at, render_churn
from ..journey.prompt import REPORT_SYSTEM, SPAN_SYSTEM, report_user, span_user
from ..harness.checks.journey import check_report
from .deps import current_user
from .schemas import (JourneyDayOut, JourneyDenyIn, JourneyDenyOut, JourneyReportOut,
                      JourneyRunOut, JourneySegment, JourneySpanOut)

router = APIRouter(prefix="/api/journey", tags=["journey"])

# Keep instructions in the system message and a final-answer marker for reasoning models.
DESCRIBE_SYSTEM = """Describe the visible screen activity in one concise English sentence. Start with a verb, without
a generic subject such as 'the user'. Include visible concrete names: a file, function,
document, page, person, error or figure. Focus on the main activity in the center, not
neighboring tabs, sidebars or status counters. Describe a visible conclusion, decision, error or
task when that is the main activity. Avoid generic statements such as 'using a code editor'. If
the content cannot be read, return 'Unable to read'. Keep it around 40 words or fewer. Put the
final sentence on a separate line beginning 'Answer:'."""
ANSWER = """Answer:"""


_SUBJECT = re.compile('^(\u8fd9\u4e2a\u4eba|\u90a3\u4e2a\u4eba|\u8fd9\u4f4d|\u7528\u6237|\u67d0\u4eba|\u4eba|\u4ed6|\u5979|TA|Ta)\\s*(\u6b63\u5728|\u5728|\u5219\u5728|\u5f53\u524d\u5728)?\\s*')
_SENT_END = "。！？"


def tighten(desc: str) -> str:
    d = (desc or "").strip()
    cut = _SUBJECT.sub("", d)
    if len(cut) >= 8:
        d = cut
    for i, ch in enumerate(d):
        if ch in _SENT_END and i + 1 < len(d):
            return d[: i + 1]
    return d


VAGUE = ('\u770b\u4e0d\u6e05', '\u65e0\u6cd5\u8fa8\u8ba4', '\u770b\u4e0d\u51fa', '\u4e0d\u6e05\u695a')
MIN_DESC = 12


BUILTIN_DENY_APPS = ("1Password", "1Password 7", "Keychain Access", '\u94a5\u5319\u4e32\u8bbf\u95ee',
                     "Bitwarden", "LastPass", "Dashlane", "Enpass")
BUILTIN_DENY_WORDS = ('\u5bc6\u7801', "password", '\u9690\u79c1\u6d4f\u89c8', "private browsing", '\u65e0\u75d5',
                      "incognito", '\u94f6\u884c', "online banking", '\u8f6c\u8d26', '\u8d26\u5355')


def journey_root() -> Path:
    return Path(os.environ.get("MEMOKET_JOURNEY_DIR")
                or (Path.home() / "Library" / "Application Support"
                    / "memoket-note-desktop" / "journey"))


def _day_dir(day: str) -> Path:
    if not _ok_day(day):
        raise HTTPException(400, 'Use a YYYY-MM-DD date, for example 2026-09-14')
    return journey_root() / day


def _ok_day(day: str) -> bool:
    try:
        _date.fromisoformat(day)
        return True
    except ValueError:
        return False


def _hhmm_local(iso: str) -> str:
    t = _at(iso)
    return t.astimezone().strftime("%H:%M") if t else iso[11:16]


def _load(day: str) -> list[dict]:
    f = _day_dir(day) / "segments.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


FRAME_KEEP_DAYS = 3


def _drop_frame(seg: dict) -> None:
    for f in seg.get("frames") or []:
        try:
            Path(f).unlink()
        except OSError:
            pass
    seg["frames"] = []


def _expire_frames(day: str, segs: list[dict]) -> int:
    try:
        stale = (_date.today() - _date.fromisoformat(day)).days >= FRAME_KEEP_DAYS
    except ValueError:
        return 0
    if not stale:
        return 0
    n = 0
    for seg in segs:
        if seg.get("deleted"):
            continue
        if seg.get("frames") and not seg.get("desc"):
            _drop_frame(seg)
            seg["skip"] = 'Screenshot expired'
            n += 1
        elif seg.get("frames"):
            _drop_frame(seg)
            n += 1
    return n


def _load_report(day: str) -> dict:
    try:
        return json.loads((_day_dir(day) / "report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


_MINE = ("desc", "skip", "session", "deleted", "frames", "thumb")


def _merge_back(disk: list[dict], ours: list[dict]) -> list[dict]:
    if not disk:
        return ours
    mine = {s["start"]: s for s in ours if s.get("start")}
    out: list[dict] = []
    for seg in disk:
        m = mine.get(seg.get("start", ""))
        if m is None:
            out.append(seg)
        elif m.get("deleted"):
            out.append(m)
        else:
            out.append({**seg, **{k: m[k] for k in _MINE if k in m}})
    return out


def _save(day: str, segs: list[dict]) -> None:
    d = _day_dir(day)
    merged = _merge_back(_load(day), segs)


    if not merged and not (d / "segments.json").exists():
        return
    d.mkdir(parents=True, exist_ok=True)
    (d / "segments.json").write_text(json.dumps(merged, ensure_ascii=False, indent=1),
                                     encoding="utf-8")


def pick_answer(raw: str) -> str:
    text = (raw or "").strip()
    for marker in (ANSWER, '\u7b54\u6848\uff1a'):
        if marker in text:
            return text.rsplit(marker, 1)[1].strip().split("\n")[0].strip()
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    cjk = [ln for ln in lines if any('\u4e00' <= c <= '\u9fff' for c in ln)]
    return (cjk[-1] if cjk else (lines[-1] if lines else text))[:300]


def worth_keeping(desc: str) -> bool:
    d = (desc or "").strip()
    return len(d) >= MIN_DESC and not any(v in d for v in VAGUE) and "unable to read" not in d.casefold()


SWEEP_EVERY_S = 10 * 60
_swept_at = 0.0


_sweep_failures: list[str] = []


def _forget(user: str):
    mem = UserMemory(user)

    def go(session: str) -> int:
        try:
            return mem.remove_sessions(session)
        except Exception:                            # noqa: BLE001


            _sweep_failures.append(f'Could not delete knowledge-base session {session}.')
            return 0

    return go


def _sweep(user: str, policy: keep.Policy | None = None) -> keep.SweepReport:
    global _swept_at
    root = journey_root()
    rep = keep.sweep(root, policy or keep.read_policy(root), _date.today(),
                     load=_load, save=_save, forget=_forget(user),
                     expire_frames=_expire_frames)
    _swept_at = time.monotonic()
    _sweep_failures[:] = rep.failures[-20:]
    return rep


def _sweep_if_due(user: str) -> None:
    if _swept_at and time.monotonic() - _swept_at < SWEEP_EVERY_S:
        return
    try:
        _sweep(user)
    except OSError as exc:                            # noqa: BLE001
        _sweep_failures[:] = [f'Cleanup failed: {exc}']


def _has_records(day: str) -> bool:
    d = journey_root() / day
    if any(not s.get("deleted") for s in _load(day)):
        return True
    return (d / "report.json").is_file()


@router.get("/days")
def days(limit: int = 400, user: str = Depends(current_user)) -> list[str]:
    _sweep_if_due(user)
    root = journey_root()
    try:
        names = sorted((d.name for d in root.iterdir()
                        if d.is_dir() and _ok_day(d.name) and (d / "segments.json").is_file()),
                       reverse=True)
    except OSError:
        return []


    return [d for d in names if _has_records(d)][:max(1, limit)]


DENY_MAX = 100
DENY_LEN = 80


def _deny_file() -> Path:
    return journey_root() / "deny.json"


def _clean_list(v) -> list[str]:
    out: list[str] = []
    for x in (v or []):
        t = str(x).strip()[:DENY_LEN]
        if t and t not in out:
            out.append(t)
    return out[:DENY_MAX]


class JourneyRetentionIn(BaseModel):
    segment_days: int = keep.DEFAULT_SEGMENT_DAYS
    thumb_days: int = keep.DEFAULT_THUMB_DAYS


class JourneyRetentionOut(BaseModel):
    segment_days: int
    thumb_days: int
    frame_days: int
    segment_choices: list[int]
    thumb_choices: list[int]

    days: int
    segments: int
    described: int
    thumbs: int
    reports: int
    bytes: int
    oldest: str

    failures: list[str] = []

    swept: dict = {}


def _retention_out(policy: keep.Policy, swept: dict | None = None) -> JourneyRetentionOut:
    root = journey_root()
    u = keep.usage(root, _load)
    return JourneyRetentionOut(**policy.as_dict(), frame_days=FRAME_KEEP_DAYS,
                               segment_choices=list(keep.SEGMENT_CHOICES),
                               thumb_choices=list(keep.THUMB_CHOICES),
                               **u.as_dict(), failures=list(_sweep_failures),
                               swept=swept or {})


@router.get("/retention", response_model=JourneyRetentionOut)
def get_retention(user: str = Depends(current_user)) -> JourneyRetentionOut:
    return _retention_out(keep.read_policy(journey_root()))


@router.put("/retention", response_model=JourneyRetentionOut)
def put_retention(body: JourneyRetentionIn,
                  user: str = Depends(current_user)) -> JourneyRetentionOut:
    policy = keep.write_policy(journey_root(),
                              keep.Policy(segment_days=body.segment_days,
                                          thumb_days=body.thumb_days))
    rep = _sweep(user, policy)
    return _retention_out(policy, rep.as_dict())


@router.delete("/all", response_model=JourneyRetentionOut)
def delete_all(user: str = Depends(current_user)) -> JourneyRetentionOut:
    rep = keep.wipe_all(journey_root(), load=_load, forget=_forget(user))
    _sweep_failures[:] = rep.failures[-20:]
    return _retention_out(keep.read_policy(journey_root()), rep.as_dict())


@router.get("/deny", response_model=JourneyDenyOut)
def get_deny(user: str = Depends(current_user)) -> JourneyDenyOut:
    try:
        j = json.loads(_deny_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        j = {}
    return JourneyDenyOut(apps=_clean_list(j.get("apps")), words=_clean_list(j.get("words")),
                          builtin_apps=list(BUILTIN_DENY_APPS), builtin_words=list(BUILTIN_DENY_WORDS))


@router.put("/deny", response_model=JourneyDenyOut)
def put_deny(body: JourneyDenyIn, user: str = Depends(current_user)) -> JourneyDenyOut:
    root = journey_root()
    root.mkdir(parents=True, exist_ok=True)
    data = {"apps": _clean_list(body.apps), "words": _clean_list(body.words)}
    _deny_file().write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return JourneyDenyOut(**data, builtin_apps=list(BUILTIN_DENY_APPS),
                          builtin_words=list(BUILTIN_DENY_WORDS))


@router.get("/day", response_model=JourneyDayOut)
def day(date: str = "", user: str = Depends(current_user)) -> JourneyDayOut:
    day_s = date or _date.today().isoformat()
    segs = _load(day_s)


    if _expire_frames(day_s, segs):
        _save(day_s, segs)
    return JourneyDayOut(
        date=day_s,
        **{k: v for k, v in _load_report(day_s).items() if k in
           ("report", "report_segments", "report_at", "report_notes")},


        segments=[JourneySegment(**{k: s.get(k, "") for k in
                                    ("start", "end", "app", "title")},
                                 desc=tighten(s.get("desc") or ""),
                                 n=int(s.get("n") or 0),
                                 has_frame=bool(s.get("frames")),
                                 has_thumb=bool(s.get("thumb")),
                                 skip=str(s.get("skip") or ""),
                                 i=n)
                  for n, s in enumerate(segs) if not s.get("deleted")],
        minutes=round(sum(_secs(s) for s in segs if not s.get("deleted")) / 60),
    )


def _secs(s: dict) -> float:
    from datetime import datetime
    try:
        return (datetime.fromisoformat(s["end"]) - datetime.fromisoformat(s["start"])).total_seconds()
    except (KeyError, TypeError, ValueError):
        return 0.0


@router.post("/catch-up", response_model=JourneyRunOut)
async def catch_up(date: str = "", limit: int = 20,
                   user: str = Depends(current_user)) -> JourneyRunOut:
    day_s = date or _date.today().isoformat()
    segs = _load(day_s)
    mem = UserMemory(user)
    described = ingested = skipped = 0
    failed: VisionError | None = None

    for i, seg in enumerate(segs):
        if described >= limit:
            break


        if seg.get("desc") or seg.get("skip") or seg.get("deleted"):
            continue
        frame = (seg.get("frames") or [None])[0]
        if not frame or not Path(frame).is_file():
            seg["desc"] = ""
            seg["skip"] = 'No screenshot'


            seg["frames"] = []
            skipped += 1
            continue
        try:
            raw = await ask_image('What is this person doing?', Path(frame).read_bytes(),
                                  max_tokens=600, system=DESCRIBE_SYSTEM)
        except VisionError as exc:


            failed = exc
            break
        desc = pick_answer(raw)
        seg["desc"] = desc
        described += 1
        _drop_frame(seg)
        if not worth_keeping(desc):
            seg["skip"] = 'No concrete activity was described'
            skipped += 1
            continue
        session = f"screen-{day_s.replace('-', '')}-{i:03d}"

        title = f"{_hhmm_local(seg.get('start', ''))}–{_hhmm_local(seg.get('end', ''))} · {seg.get('app', '')}"
        try:
            mem.remember([{"role": "user", "content": desc}],
                         session_id=session, date=day_s, title=title)
            seg["session"] = session
            ingested += 1
        except Exception as exc:                       # noqa: BLE001


            if "already exists" not in str(exc):
                raise
            seg["session"] = session
    if described or skipped:
        _save(day_s, segs)
    if failed is not None and not described:
        raise HTTPException(502, f'Image analysis failed: {failed}') from failed
    left = sum(1 for s in segs if not s.get("desc") and not s.get("skip") and not s.get("deleted"))
    return JourneyRunOut(date=day_s, described=described, ingested=ingested,
                         skipped=skipped, left=left)


@router.get("/thumb")
def thumb(date: str, i: int, user: str = Depends(current_user)):
    segs = _load(date)
    if not 0 <= i < len(segs):
        raise HTTPException(404, 'Segment not found')
    raw = segs[i].get("thumb") or ""
    root = _day_dir(date).resolve()
    try:
        p = Path(raw).resolve()
        p.relative_to(root)
    except (OSError, ValueError):
        raise HTTPException(404, 'This segment has no thumbnail') from None
    if not p.is_file():
        raise HTTPException(404, 'This segment has no thumbnail')
    return FileResponse(p, media_type="image/jpeg")


@router.post("/report", response_model=JourneyReportOut)
async def report(date: str = "", user: str = Depends(current_user)) -> JourneyReportOut:
    t0 = time.perf_counter()
    day_s = date or _date.today().isoformat()
    segs = _load(day_s)
    st = day_stats(day_s, [s for s in segs if not s.get("deleted")])
    told = [s for s in segs if (s.get("desc") or "").strip() and not s.get("deleted")]
    if not told:

        raise HTTPException(400, 'This day has no descriptions. Choose Describe these segments first.')


    runs = group_runs(sorted(told, key=lambda x: x.get("start") or ""))

    lines = [f"{_hhmm_local(r['start'])}–{_hhmm_local(r['end'])} {r['app']} {r['desc']}"
             + (f"（{len(r['segs'])} segments)" if len(r["segs"]) > 1 else "")
             for r in runs]
    text = await llm.complete(
        [{"role": "system", "content": prompts.compose_system(REPORT_SYSTEM, "journey", user)},
         {"role": "user", "content": report_user(day_s, lines, render_churn(st))}],
        max_tokens=1200, temperature=0.3)

    md = render_time_block(st) + "\n" + text.strip() + "\n"


    notes = check_report(text.strip(), lines).notes()
    d = _day_dir(day_s)
    d.mkdir(parents=True, exist_ok=True)
    meta = {"report": md, "report_segments": len(told),
            "report_at": _dt.now().astimezone().isoformat(timespec="seconds"),
            "report_notes": notes}
    (d / "report.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return JourneyReportOut(date=day_s, report=md, segments=len(told),
                            report_at=meta["report_at"], notes=notes,
                            took_ms=round((time.perf_counter() - t0) * 1000, 1))


@router.post("/span", response_model=JourneySpanOut)
async def span(date_from: str = "", date_to: str = "", days: int = 7,
               user: str = Depends(current_user)) -> JourneySpanOut:
    t0 = time.perf_counter()
    to_s = date_to or _date.today().isoformat()
    from_s = date_from or (_date.fromisoformat(to_s) - timedelta(days=max(1, days) - 1)).isoformat()
    if from_s > to_s:
        raise HTTPException(400, 'The start date must precede the end date')

    reports: list[tuple[str, str]] = []
    missing: list[str] = []
    d = _date.fromisoformat(from_s)
    while d <= _date.fromisoformat(to_s):
        key = d.isoformat()
        md = (_load_report(key).get("report") or "").strip()
        (reports.append((key, md)) if md else missing.append(key))
        d += timedelta(days=1)

    if not reports:

        raise HTTPException(400, f'{from_s} to {to_s} has no daily reports. Write reports for those days first.')

    text = await llm.complete(
        [{"role": "system", "content": prompts.compose_system(SPAN_SYSTEM, "journey", user)},
         {"role": "user", "content": span_user(from_s, to_s, reports)}],
        max_tokens=2000, temperature=0.3)

    title = f'{from_s} – {to_s} period review'
    body = text.strip() + "\n"
    if missing:


        body += (f"\n---\n\n(This review uses {len(reports)} daily reports. No daily reports are available for: {'、'.join(missing[:10])}{('…' if len(missing) > 10 else '')}.)\n")

    parent = store.journal_node(user, _date.fromisoformat(to_s), depth=3)
    note = store.create_note(user, title, f"# {title}\n\n{body}", parent, source="journey")
    return JourneySpanOut(date_from=from_s, date_to=to_s, days=len(reports),
                          missing=missing, note_id=note["id"], title=title,
                          took_ms=round((time.perf_counter() - t0) * 1000, 1))


@router.post("/report/save", response_model=JourneySpanOut)
def save_report(date: str = "", user: str = Depends(current_user)) -> JourneySpanOut:
    day_s = date or _date.today().isoformat()
    md = (_load_report(day_s).get("report") or "").strip()
    if not md:
        raise HTTPException(400, 'Write a review for this day first.')
    parent = store.journal_node(user, _date.fromisoformat(day_s), depth=4)
    note = store.upsert_child(user, parent, 'Screen activity review',
                              f'# {day_s} screen activity\n\n{md}',
                              source="journey", icon="bx-desktop")
    return JourneySpanOut(date_from=day_s, date_to=day_s, days=1,
                          note_id=note["id"], title=note["title"])


@router.delete("/segment", response_model=JourneyRunOut)
def delete_segment(date: str, i: int, user: str = Depends(current_user)) -> JourneyRunOut:
    segs = _load(date)
    if not 0 <= i < len(segs):
        raise HTTPException(404, 'Segment not found')
    seg = segs[i]
    gone = UserMemory(user).remove_sessions(seg["session"]) if seg.get("session") else 0
    _drop_frame(seg)
    for f in (seg.get("thumb"),):
        if f:
            try:
                Path(f).unlink()
            except OSError:
                pass
    segs[i] = {"start": seg.get("start", ""), "end": seg.get("end", ""),
               "app": "", "title": "", "desc": "", "deleted": True, "n": 0}
    _save(date, segs)
    return JourneyRunOut(date=date, described=0, ingested=0, skipped=0,
                         left=sum(1 for x in segs if not x.get("desc") and not x.get("skip")
                                  and not x.get("deleted")),
                         removed_facts=gone)


@router.delete("/day", response_model=JourneyRunOut)
def delete_day(date: str, user: str = Depends(current_user)) -> JourneyRunOut:
    day_s = date
    segs = _load(day_s)
    d = _day_dir(day_s)


    fails: list[str] = []
    keep.rm_tree(d, fails)
    if fails:


        lines = [f.replace(f"{d}/", "").replace(f"{d}：", 'the day directory itself: ').replace(f"{d}: ", 'the day directory itself: ')
                 for f in fails[:10]]
        more = f' ({len(fails) - 10} others)' if len(fails) > 10 else ""
        raise HTTPException(
            500, f'Could not fully delete this day. Under {d}, {len(fails)} items could not be removed{more}：\n' + "\n".join(lines))
    mem = UserMemory(user)
    gone = 0
    for s in segs:
        if s.get("session"):
            gone += mem.remove_sessions(s["session"])
    return JourneyRunOut(date=day_s, described=0, ingested=0, skipped=0,
                         left=0, removed_facts=gone)
