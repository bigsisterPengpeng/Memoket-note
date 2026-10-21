"""Advisory checks for model-authored activity reports; computed time totals are excluded."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...journey.runs import similar
from .anchors import has_concrete_anchor


SECTIONS = ("What moved forward", "Where it got stuck", "Unplanned",
            '\u63a8\u8fdb\u4e86\u4ec0\u4e48', '\u5361\u5728\u54ea', '\u8ba1\u5212\u5916\u7684')


DUP_BULLET = 0.55


_DURATION = re.compile('\\d+(?:\\.\\d+)?\\s*(?:\u5206\u949f|\u5c0f\u65f6|\u4e2a\u5c0f\u65f6|\u79d2|minutes?\\b|hours?\\b|mins?\\b|seconds?\\b|secs?\\b)')

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
_BULLET = re.compile(r"^\s*[-*]\s+(.+?)\s*$", re.M)


def _sections(text: str) -> list[tuple[str, str]]:
    """Split Markdown sections, keeping any introduction under an empty heading."""
    parts = re.split(r"(?m)^#{1,6}\s+(.+?)\s*$", text or "")
    out: list[tuple[str, str]] = []
    if parts and parts[0].strip():
        out.append(("", parts[0]))
    for i in range(1, len(parts) - 1, 2):
        out.append((parts[i].strip(), parts[i + 1]))
    return out


@dataclass(frozen=True)
class ReportCheck:
    """Advisory report findings; these do not prevent saving."""

    bullets: int = 0
    recomputed_durations: list[str] = field(default_factory=list)
    stray_sections: list[str] = field(default_factory=list)
    vague_bullets: list[str] = field(default_factory=list)
    duplicate_bullets: list[tuple[str, str, float]] = field(default_factory=list)
    unsourced_terms: list[str] = field(default_factory=list)

    def notes(self) -> list[str]:
        out: list[str] = []
        if self.recomputed_durations:
            out.append("Durations absent from the source records: "
                       + ", ".join(self.recomputed_durations[:4])
                       + ". Use time totals computed from timestamps rather than model estimates.")
        if self.stray_sections:
            out.append("Unexpected sections: " + ", ".join(self.stray_sections[:3])
                       + ". Use only the three sections: What moved forward, Where it got stuck, Unplanned. "
                       "Omit sections with no content.")
        if self.unsourced_terms:
            out.append("Names or identifiers absent from today's records: "
                       + ", ".join(self.unsourced_terms[:6]) + ". Ground the report in the supplied records.")
        if self.vague_bullets:
            out.append("Items without concrete details such as files, names, errors or numbers: "
                       + "; ".join(b[:28] for b in self.vague_bullets[:2])
                       + ". Replace generic progress statements with specific events.")
        for a, b, ratio in self.duplicate_bullets[:2]:
            out.append(f"Two items in the same section overlap ({ratio:.0%} similarity): "
                       f"{a[:26]}…; {b[:26]}…. Describe each event once.")
        return out


def check_report(text: str, lines: list[str]) -> ReportCheck:
    """Compare model-authored prose with the exact source lines supplied to the model."""
    body = (text or "").strip()
    source = "\n".join(lines or [])
    low = source.lower()
    english_report = any(f"## {title}" in body for title in SECTIONS[:3])

    stray = [t for t in (m.group(1).strip() for m in _HEADING.finditer(body))
             if t not in SECTIONS]

    durations = [d for d in _DURATION.findall(body) if d not in source]

    vague: list[str] = []
    dups: list[tuple[str, str, float]] = []
    terms: list[str] = []
    total = 0
    for _title, chunk in _sections(body):
        items = [m.group(1).strip() for m in _BULLET.finditer(chunk)]
        total += len(items)
        for b in items:
            if not has_concrete_anchor(b):
                vague.append(b)


            for t in re.findall(r"[A-Za-z][A-Za-z0-9_.#-]{2,}", b):
                name = t.strip(".-")
                # In English, ordinary prose is not evidence of an invented name.
                # Check recognizable code/file identifiers; legacy reports retain
                # their original Latin-name check.
                if english_report and not (
                    re.search(r"[_.#0-9]|[a-z][A-Z]", name) or name.isupper()
                ):
                    continue
                if len(name) >= 3 and name.lower() not in low and name not in terms:
                    terms.append(name)
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                ratio = similar(items[i], items[j])
                if ratio >= DUP_BULLET:
                    dups.append((items[i], items[j], round(ratio, 2)))

    return ReportCheck(bullets=total, recomputed_durations=durations,
                       stray_sections=stray, vague_bullets=vague,
                       duplicate_bullets=dups, unsourced_terms=terms)
