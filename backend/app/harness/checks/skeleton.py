"""Deterministic, advisory checks and coverage labels for generated writing plans."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .anchors import has_concrete_anchor


MIN_BEATS = 3


DUP_BEAT_RATIO = 0.55


MIN_SPINE_CHARS = 15


_DEFECT_AS_INTENT = re.compile(
    '\u7f16\u53f7(\u9519\u4f4d|\u9519\u5e8f|\u8df3\u53f7|\u6df7\u4e71|\u9519\u4e71)|\u6807\u9898\u5c42\u7ea7(\u6df7\u4e71|\u4e0d\u7edf\u4e00|\u9519\u4e71)|\u81ea\u76f8\u77db\u76fe|\u81ea\u6211\u62c6\u53f0|\u53cd\u8f6c\u5f20\u529b|\u5f62\u5f0f\u4e0e\u5185\u5bb9\u7684\u8131\u8282|\u9519\u4f4d\u5448\u73b0|\u75c5\u53e5|\u7a7a\u58f3\u6807\u9898|\u91cd\u590d\u51fa\u73b0\u7684\u7ed3\u8bba|(?:use|using|through)\\s+(?:deliberate\\s+)?(?:incorrect numbering|broken headings|self-contradiction)', re.I)


@dataclass(frozen=True)
class SkeletonCheck:
    """Advisory findings; an empty notes list indicates no detected issue."""

    beats: int
    thin_spine: bool
    duplicate_beats: list[tuple[int, int, float]] = field(default_factory=list)
    all_rhetoric: bool = False
    defect_as_intent: list[str] = field(default_factory=list)

    @property
    def too_few_beats(self) -> bool:
        return self.beats < MIN_BEATS

    def notes(self) -> list[str]:
        out: list[str] = []
        if self.thin_spine:
            out.append("Core tension is too brief. Describe the question or change that connects the piece.")
        if self.too_few_beats:
            out.append(f"Structural beats: only {self.beats}; usually 3–6 are needed to guide continuation.")
        for i, j, ratio in self.duplicate_beats[:2]:
            out.append(f"Beats {i} and {j} cover the same subject ({ratio:.0%} similarity). "
                       "Combining them can prevent duplicate passages.")
        if self.all_rhetoric:
            out.append("Every beat is a rhetorical function without a concrete project, date, number, "
                       "decision or quotation. Ground the plan in the author's material.")
        if self.defect_as_intent:
            out.append("Draft defects were treated as writing intent: "
                       + "; ".join(x[:40] for x in self.defect_as_intent[:2])
                       + ". Repair numbering, heading or contradiction errors rather than designing around them.")
        return out


BEAT_TARGET_CHARS = 120


BEATS_PER_CHARS = 2000
BEATS_MIN_BUDGET = 6
BEATS_MAX_BUDGET = 12


def beats_budget(n_chars: int) -> int:
    """Limit plan size according to the body length."""
    import math
    return max(BEATS_MIN_BUDGET, min(BEATS_MAX_BUDGET, math.ceil(max(0, n_chars) / BEATS_PER_CHARS)))


def skeleton_length_rule(n_chars: int) -> str:
    """Describe plan size and status labels for the generation prompt."""
    k = beats_budget(n_chars)
    return (f"\nAdditional requirements for this draft:\n"
            f"- The body has about {n_chars} characters. Provide 3–{k} beats, covering each major section.\n"
            f"- Keep each beat within {BEAT_TARGET_CHARS} characters (one or two short sentences).\n"
            '- Start each beat with "Written:" or "Missing:". Use "Missing:" only when that content '
            'is actually absent from the draft.\n')


# Legacy labels remain readable in existing notes; new labels are English.
_STATUS = re.compile(
    r"^\s*[\u3010\[\uff08(]?\s*(?:(?P<w>(?:written|completed)(?=\s*(?:[\u3011\]\uff09):\uff1a,\uff0c\u3001—-]|\(from body line|\uff08\u6b63\u6587\u7b2c|$))|"
    r"\u5df2\u5199(?:\u5e76\u9700\u7ee7\u7eed\u6536\u7d27|\u5e76\u9700\u6536\u7d27|\u4f46\u9700\u6536\u7d27)?|\u5df2\u6709|\u5df2\u5b8c\u6210)"
    r"|(?P<m>(?:missing|to fill)(?=\s*(?:[\u3011\]\uff09):\uff1a,\uff0c\u3001—-]|\(from body line|\uff08\u6b63\u6587\u7b2c|$))|\u5f85\u8865\u5145|\u5f85\u8865|\u5c1a\u7f3a|\u7f3a\u5931|\u672a\u5199|\u5f85\u5199|\u5c1a\u672a\u5199|\u5f85\u5199\u5165))",
    re.I,
)
_STATUS_TAIL = re.compile(
    r"^\s*[\u3011\]\uff09)]?\s*"
    r"(?:(?:\(from body line\s*(\d+)\s*\)|\uff08\u6b63\u6587\u7b2c\s*(\d+)\s*\u884c\u8d77\uff09))?"
    r"\s*[:\uff1a,\uff0c\u3001—-]*\s*", re.I,
)
BEAT_WRITTEN = "Written: "
BEAT_MISSING = "Missing: "


def split_beat_label(beat: str) -> tuple[str | None, str]:
    """Parse current English labels and labels saved by earlier versions."""
    m = _STATUS.match(beat or "")
    if not m:
        return None, (beat or "").strip()
    status = "written" if m.group("w") else "missing"
    rest = _STATUS_TAIL.sub("", beat[m.end():], count=1)
    return status, rest.strip()


_COV_EN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
_COV_NUM = re.compile(r"\d+(?:\.\d+)?")
_COV_EN_STOP = frozenset("a an the and or but if then of to in on at for from with by as "
                         "is are was were be been being it its this that these those "
                         "we our you your they their he she his her have has had do does did "
                         "will would can could should must not into".split())
_COV_CJK = re.compile('[\u4e00-\u9fff]+')
_COV_STOP = set('\u7684\u4e86\u5728\u662f\u548c\u4e0e\u53ca\u6216\u628a\u88ab\u5bf9\u5230\u4ece\u8fd9\u90a3\u6211\u4eec\u4f60\u4ed6\u5979\u5b83\u5c31\u4e5f\u90fd\u8fd8\u53c8\u5f88\u4e0d\u6ca1\u6709\u4e2a\u4e00\u4e86\u7740\u8fc7\u4e3a\u4ee5\u53ca\u4ee5\u5e76\u5c06\u5176\u5e76\u4e14\u800c\u4e14\u4f46\u662f\u5982\u679c\u90a3\u4e48\u8fd9\u6837\u8fd9\u4e9b\u90a3\u4e9b\u4ec0\u4e48\u600e\u4e48\u5df2\u7ecf\u53ef\u4ee5\u9700\u8981\u5fc5\u987b\u5e94\u8be5\u80fd\u591f\u901a\u8fc7\u8fdb\u884c\u4f5c\u4e3a')


def _cov_terms(text: str) -> set[str]:
    out = {w.lower() for w in _COV_EN.findall(text or "")
           if len(w) >= 2 and w.lower() not in _COV_EN_STOP}
    out |= set(_COV_NUM.findall(text or ""))
    for run in _COV_CJK.findall(text or ""):
        for i in range(len(run) - 1):
            g = run[i:i + 2]
            if g[0] not in _COV_STOP and g[1] not in _COV_STOP:
                out.add(g)
    return out


def _paragraphs(content: str) -> list[tuple[int, str]]:
    """Return one-based paragraph start lines, preserving blank-line boundaries."""
    out: list[tuple[int, str]] = []
    lines = (content or "").split("\n")
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start, buf = i, []
        while i < len(lines) and lines[i].strip():
            buf.append(lines[i])
            i += 1
        out.append((start + 1, "\n".join(buf)))
    return out


_PLACEHOLDER_CELL = re.compile('^\\s*(?:\u586b\u5199|\u5f85\u586b|\u5f85\u8865|\u5f85\u5b9a|\u5f85\u786e\u8ba4|\u5f85\u6838\u5b9e|\u8bf7\u586b|TBD\\b|N/?A\\b|to be (?:filled|confirmed|verified)\\b|fill in\\b)', re.I)


def _strip_placeholders(content: str) -> str:
    """Remove unfilled cells without changing line numbers."""
    out: list[str] = []
    for line in (content or "").split("\n"):
        if "|" in line:
            out.append("|".join("" if _PLACEHOLDER_CELL.match(c) else c for c in line.split("|")))
        elif _PLACEHOLDER_CELL.match(line):
            out.append("·")
        else:
            out.append(line)
    return "\n".join(out)


COVER_WINDOW = 3
COVER_MIN = 0.42


def beat_coverage(body: str, content: str) -> tuple[float, int | None]:
    """Measure token coverage in the best consecutive paragraph window."""
    bt = _cov_terms(body)
    if not bt:
        return 0.0, None
    paras = _paragraphs(_strip_placeholders(content))
    if not paras:
        return 0.0, None
    pterms = [(ln, _cov_terms(t)) for ln, t in paras]
    best, best_line = 0.0, None
    for i in range(len(pterms)):
        win = pterms[i:i + COVER_WINDOW]
        union: set[str] = set()
        for _ln, t in win:
            union |= t
        score = len(bt & union) / len(bt)
        if score > best:
            best = score
            best_line = max(win, key=lambda x: len(bt & x[1]))[0]
    return round(best, 3), best_line


_ENUM_RUN = re.compile('[\u4e00-\u9fffA-Za-z0-9]{2,8}(?:\u3001[\u4e00-\u9fffA-Za-z0-9]{2,8}){2,}(?:(?:\u4e0e|\u548c|\u53ca|\u4ee5\u53ca)[\u4e00-\u9fffA-Za-z0-9]{2,8})?')
COVER_ITEM_MIN = 0.5


def enum_items(body: str) -> list[str]:
    """Extract legacy CJK lists of at least three items."""
    m = _ENUM_RUN.search(body or "")
    if not m:
        return []
    return [x for x in re.sub('(\u4e0e|\u548c|\u53ca|\u4ee5\u53ca)', "、", m.group(0)).split("、") if x]


def enum_inner_items(body: str) -> list[str]:
    """Check only internal items, avoiding ambiguous phrase boundaries."""
    return enum_items(body)[1:-1]


def uncovered_items(body: str, content: str) -> list[str]:
    """Find enumerated items missing from the best coverage window."""
    items = enum_inner_items(body)
    if not items:
        return []
    bt = _cov_terms(body)
    paras = _paragraphs(_strip_placeholders(content))
    if not bt or not paras:
        return []
    pterms = [(ln, _cov_terms(t)) for ln, t in paras]
    best, union = 0.0, set()
    for i in range(len(pterms)):
        win = pterms[i:i + COVER_WINDOW]
        u: set[str] = set()
        for _ln, t in win:
            u |= t
        score = len(bt & u) / len(bt)
        if score > best:
            best, union = score, u
    out: list[str] = []
    for it in items:
        t = _cov_terms(it)
        if t and len(t & union) < COVER_ITEM_MIN * len(t):
            out.append(it)
    return out


def verify_beats(beats: list[str], content: str, *, threshold: float = COVER_MIN) -> list[str]:
    """Normalize labels and promote missing beats only when covered by the body."""
    out: list[str] = []
    for b in beats or []:
        status, body = split_beat_label(b)
        if not body:
            continue
        score, line = beat_coverage(body, content)
        if status == "missing":


            if score >= threshold and line and not uncovered_items(body, content):
                out.append(f"Written (from body line {line}): {body}")
            else:
                out.append(BEAT_MISSING + body)
        elif status == "written":

            label = _STATUS.match(b or "")
            kept = _STATUS_TAIL.match(b[label.end():]) if label else None
            line = (kept.group(1) or kept.group(2)) if kept else None
            out.append((f"Written (from body line {line}): " if line else BEAT_WRITTEN) + body)
        else:
            out.append((BEAT_WRITTEN + body) if score >= threshold else body)
    return out


def check_skeleton(spine: str, beats: list[str]) -> SkeletonCheck:
    """Return advisory plan findings without accessing storage or a model."""
    clean = [str(b).strip() for b in (beats or []) if str(b).strip()]

    dups: list[tuple[int, int, float]] = []
    for i in range(len(clean)):
        for j in range(i + 1, len(clean)):
            ratio = difflib.SequenceMatcher(None, clean[i], clean[j]).ratio()
            if ratio >= DUP_BEAT_RATIO:
                dups.append((i + 1, j + 1, round(ratio, 2)))

    blob = "\n".join([spine or ""] + clean)
    offenders = [line for line in ([spine or ""] + clean)
                 if line and _DEFECT_AS_INTENT.search(line)]

    return SkeletonCheck(
        beats=len(clean),


        thin_spine=bool((spine or "").strip()) and len((spine or "").strip()) < MIN_SPINE_CHARS,
        duplicate_beats=dups,
        all_rhetoric=bool(clean) and not any(has_concrete_anchor(split_beat_label(b)[1]) for b in clean),
        defect_as_intent=offenders if _DEFECT_AS_INTENT.search(blob) else [],
    )
