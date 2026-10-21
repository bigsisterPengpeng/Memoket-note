"""Advisory checks for a single continuation against its supplied pre-run text and material."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ..middleware import repeats
from ..tailing import needs_tail


RESTATE_RATIO = repeats.DEFAULT_THRESHOLD
MIN_PARAGRAPH = repeats.MIN_PARAGRAPH_LEN


SCAFFOLD_TITLES = ('\u6536\u675f', '\u603b\u7ed3', '\u5c0f\u7ed3', '\u7ed3\u8bed', '\u5c55\u5f00', '\u8fc7\u6e21', '\u8865\u5145',
                   '\u7ed3\u8bba', '\u547c\u5e94', '\u627f\u63a5', '\u94fa\u57ab',
                   "closure", "summary", "expansion", "supplement", "conclusion", "transition")

# Only current verbatim examples belong here; stale entries create false alarms.
# Generation and benchmarks share this table. A regression test checks prompt membership.
PROMPT_EXAMPLES = (
    "Requirements confirmed",
    "Prototype test",
    "Design finalized",
    "Hardware battery-life options",
)

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)


def scaffold_headings(text: str) -> list[str]:
    out: list[str] = []
    for m in _HEADING.finditer(text or ""):
        title = m.group(1).strip()
        head = re.sub(r"[：:].*$", "", title).strip()
        if head.casefold() in SCAFFOLD_TITLES:
            out.append(title)
    return out


def leaked_prompt_examples(text: str) -> list[str]:
    return [e for e in PROMPT_EXAMPLES if e in (text or "")]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in (text or "").split("\n\n")
            if len(p.strip()) >= MIN_PARAGRAPH]


def restated_paragraphs(written: str, before: str) -> list[tuple[str, str, float]]:
    mine, theirs = _paragraphs(written), _paragraphs(before)
    out: list[tuple[str, str, float]] = []
    for a in mine:
        best = max(((SequenceMatcher(None, a, b, autojunk=False).ratio(), b) for b in theirs),
                   default=(0.0, ""))
        if best[0] >= RESTATE_RATIO:
            out.append((a, best[1], round(best[0], 2)))
    return out


@dataclass(frozen=True)
class TapCheck:
    unfinished: bool = False

    restated: list[tuple[str, str, float]] = field(default_factory=list)

    scaffold_titles: list[str] = field(default_factory=list)

    leaked_examples: list[str] = field(default_factory=list)

    def notes(self) -> list[str]:
        out: list[str] = []
        if self.unfinished:
            out.append('The passage ends mid-sentence. Place the cursor at its end and continue, or undo and retry.')
        for mine, theirs, ratio in self.restated[:2]:
            out.append(f'This passage repeats earlier content (similarity {ratio:.0%}）：「{mine[:32]}..." versus "{theirs[:32]}…」。')
        if self.scaffold_titles:
            out.append("These headings describe the section's role instead of its subject: "
                       + "、".join(f"「{t}」" for t in self.scaffold_titles[:3])
                       + '. Use a self-contained conclusion as the heading.')
        if self.leaked_examples:
            out.append('The body copies example wording from the prompt: '
                       + "、".join(f"「{e}」" for e in self.leaked_examples[:3])
                       + '. This is an example from the writing instructions, not content belonging to the note.')
        return out


def check_tap(written: str, before: str = "") -> TapCheck:
    text = (written or "").strip()
    if not text:
        return TapCheck()
    return TapCheck(
        unfinished=needs_tail(text),
        restated=restated_paragraphs(text, before),
        scaffold_titles=scaffold_headings(text),
        leaked_examples=leaked_prompt_examples(text),
    )
