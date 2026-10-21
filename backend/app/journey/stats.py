"""One day's segments -> counted facts. No model calls, no I/O."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from ..util import i18n
from .prompt import prompt_tr

# Grouping key for segments without an app name; shown through the dictionary.
UNKNOWN_APP = "(unknown)"

# A gap this long between two segments counts as "not recording" (lunch, a meeting, away from the
# desk). Same number as GAP_MIN in the frontend's JourneyPage: the same strip must look the same on
# both sides.
GAP_MIN = 15

# A stretch of continuous focus has to be at least this long to be worth calling out - 3 minutes of
# "focus" is not focus.
FOCUS_MIN = 10

# Returning to the same place: only this many back-and-forths count. 2 is normal (writing code <->
# reading docs); **3 or more, with other places in between**, is the "going round in circles in one
# place" signal.
CHURN_VISITS = 3


def _at(s: str) -> datetime | None:
    """Read a segment timestamp as a timezone-aware datetime. None when it cannot be read -
    one bad row must not collapse a whole day's statistics (round 636 capture: the whole day 500).

    Without a timezone it is taken as local time: the shell always writes UTC (`toISOString()`),
    so a value without a timezone can only have been put in by hand.
    """
    try:
        t = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    return t if t.tzinfo else t.astimezone()


def seg_secs(seg: dict) -> float:
    a, b = _at(seg.get("start", "")), _at(seg.get("end", ""))
    return max(0.0, (b - a).total_seconds()) if a and b else 0.0


@dataclass(frozen=True)
class AppSpan:
    """How long one app took in total today."""

    app: str
    secs: float
    segments: int


@dataclass(frozen=True)
class Stretch:
    """One uninterrupted stretch of time (same app, no gap in between).

    `title` is the window title that took the most time in this block - **"52 minutes in Code this
    afternoon" says almost nothing, "in capture.ts" does**. Empty when there is no title.
    """

    app: str
    start: datetime
    end: datetime
    secs: float
    title: str = ""


@dataclass(frozen=True)
class Churn:
    """A place returned to again and again: how many back-and-forths, and how long in total."""

    app: str
    title: str
    visits: int
    secs: float


@dataclass
class DayStats:
    date: str
    """Time actually recorded (sum of segments, gaps excluded)."""
    total_secs: float = 0.0
    """How long from the first segment to the last (gaps included)."""
    span_secs: float = 0.0
    gap_secs: float = 0.0
    apps: list[AppSpan] = field(default_factory=list)
    stretches: list[Stretch] = field(default_factory=list)
    churn: list[Churn] = field(default_factory=list)
    first: datetime | None = None
    last: datetime | None = None


def day_stats(date: str, segs: list[dict]) -> DayStats:
    """Count one day's segments into a statistic. **Reordered by time** - the on-disk order is usually
    time order, but paths like filling in descriptions or moving across day directories can shuffle it, and
    both the "continuous focus" and "back and forth" signals depend on order."""
    usable = [s for s in segs if _at(s.get("start", "")) and _at(s.get("end", ""))]
    usable.sort(key=lambda s: _at(s["start"]))          # type: ignore[arg-type,return-value]
    out = DayStats(date=date)
    if not usable:
        return out

    out.first, out.last = _at(usable[0]["start"]), _at(usable[-1]["end"])
    out.total_secs = sum(seg_secs(s) for s in usable)
    if out.first and out.last:
        out.span_secs = max(0.0, (out.last - out.first).total_seconds())

    by_app: dict[str, list[float]] = {}
    for s in usable:
        by_app.setdefault(s.get("app") or UNKNOWN_APP, []).append(seg_secs(s))
    out.apps = sorted((AppSpan(a, sum(v), len(v)) for a, v in by_app.items()),
                      key=lambda x: -x.secs)

    # Gaps + continuous focus: one sweep. Two adjacent segments more than GAP_MIN apart break the
    # stretch, and consecutive segments of the same app merge into one block.
    cur_app, cur_start, cur_end = usable[0].get("app"), _at(usable[0]["start"]), _at(usable[0]["end"])
    titles: dict[str, float] = {}

    def close() -> None:
        top = max(titles.items(), key=lambda kv: kv[1])[0] if titles else ""
        out.stretches.append(Stretch(cur_app or "", cur_start, cur_end,           # type: ignore[arg-type]
                                     (cur_end - cur_start).total_seconds(), top))  # type: ignore[operator]

    titles[(usable[0].get("title") or "").strip()] = seg_secs(usable[0])
    titles.pop("", None)
    for prev, s in zip(usable, usable[1:]):
        a, b = _at(s["start"]), _at(s["end"])
        idle = (a - _at(prev["end"])).total_seconds()    # type: ignore[operator]
        broke = idle >= GAP_MIN * 60
        if broke:
            out.gap_secs += idle
        if broke or s.get("app") != cur_app:
            close()
            cur_app, cur_start, titles = s.get("app"), a, {}
        t = (s.get("title") or "").strip()
        if t:
            titles[t] = titles.get(t, 0.0) + seg_secs(s)
        cur_end = b
    close()
    out.stretches = sorted((x for x in out.stretches if x.secs >= FOCUS_MIN * 60),
                           key=lambda x: -x.secs)

    out.churn = _churn(usable)
    return out


def _churn(segs: list[dict]) -> list[Churn]:
    """Returning to the same place: the same (app, title) left and came back, **with other places visited in between**.

    Count the "returns", not the segments: several consecutive segments of the same place are one stay, not
    three back-and-forths. This signal is unique to screen records - meeting notes and notes have no such thing
    as "you are going round in circles here" (section 4.1).
    """
    visits: dict[tuple[str, str], list[float]] = {}
    prev_key: tuple[str, str] | None = None
    for s in segs:
        key = (s.get("app") or "", (s.get("title") or "").strip())
        if key != prev_key:
            visits.setdefault(key, []).append(0.0)
        visits[key][-1] += seg_secs(s)
        prev_key = key
    out = [Churn(app, title, len(v), sum(v))
           for (app, title), v in visits.items()
           if len(v) >= CHURN_VISITS and title]        # without a title we cannot tell whether it is the same place; not counted
    return sorted(out, key=lambda c: (-c.visits, -c.secs))


# ---------------------------------------------------------------- the part written for the model /
# the report

def say_span(sec: float, tr: Callable[..., str] = i18n.msg) -> str:
    m = round(sec / 60)
    if m < 1:
        return tr("under 1 min")
    if m < 60:
        return tr("{m} min", m=m)
    h, rest = divmod(m, 60)
    return tr("{h} h {rest} min", h=h, rest=rest) if rest else tr("{h} h", h=h)


def _app_name(app: str, tr: Callable[..., str] = i18n.msg) -> str:
    return tr(app) if app == UNKNOWN_APP else app


def _hhmm(t: datetime | None) -> str:
    return t.astimezone().strftime("%H:%M") if t else "—"


def render_time_block(st: DayStats) -> str:
    """The "where the time went" section is **hard-written by code**, not handed to the model.

    A model counting durations gets them wrong, and when it does it reads exactly like getting them right. The
    daily report uses this markdown verbatim for that section, and the prompt says outright "do not recompute,
    and do not repeat this section". The text follows the request language (it lands in the user's note).
    """
    title = "## " + i18n.msg("Where the time went")
    if not st.apps:
        return title + "\n\n" + i18n.msg("No records for this day.") + "\n"
    span = dict(first=_hhmm(st.first), last=_hhmm(st.last), total=say_span(st.total_secs))
    lines = [
        title,
        "",
        i18n.msg("{first} – {last}, recorded {total}, with {gap} not recorded in between.",
                 gap=say_span(st.gap_secs), **span)
        if st.gap_secs >= GAP_MIN * 60 else i18n.msg("{first} – {last}, recorded {total}.", **span),
        "",
    ]
    lines += [i18n.msg("- **{app}** {span} ({n} segments)", app=_app_name(a.app), span=say_span(a.secs),
                       n=a.segments) for a in st.apps[:8]]
    if st.stretches:
        lines += ["", i18n.msg("Uninterrupted stretches:")]
        lines += [f"- {_hhmm(x.start)}–{_hhmm(x.end)} {_app_name(x.app)}"
                  + (f" · {x.title}" if x.title else "") + f" {say_span(x.secs)}"
                  for x in st.stretches[:5]]
    return "\n".join(lines) + "\n"


def render_churn(st: DayStats) -> str:
    """Places returned to again and again, fed to the model as clues for "where it got stuck" - **clues, not
    conclusions**: eight back-and-forths may mean stuck, or that the task simply needs both sides side by side.
    Written in the prompt language (`prompt_tr`), since it is part of the prompt."""
    if not st.churn:
        return ""
    lines = [prompt_tr("Places returned to again and again today (left and came back, with other places in between):")]
    lines += [prompt_tr("- {app} · {title}: {visits} times, {span} in total", app=_app_name(c.app, prompt_tr),
                        title=c.title, visits=c.visits, span=say_span(c.secs, prompt_tr))
              for c in st.churn[:6]]
    return "\n".join(lines) + "\n"
