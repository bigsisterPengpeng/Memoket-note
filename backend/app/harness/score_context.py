"""Build generation and scoring context from the same run materials.

Keep context windows consistent with the writer. Preserve correction notices
when evidence is truncated, and place changing material after the body to retain
a stable prompt prefix. Pure functions also serve benchmark replay."""

from __future__ import annotations

import re
from typing import Sequence

from .params import SECTION_SCORING


# Generation and scoring must use the same context windows.
BEFORE_CHARS = 900
AFTER_CHARS = 450
SELECTION_CHARS = 2000

# Keep this heading identical to the material-use dimension guidance.
MATERIAL_KEY = "Knowledge-base facts"


PROMPT_KEY = "User instruction"


# Evidence may contain whole tool results; preserve useful numeric context.
FACT_CHARS = 500
MATERIAL_CHARS = 6000


# Keep notices at line end so source identifiers remain at the beginning.
NOTICE_MARK = "[Evidence notice]"


def for_block(*, before: str = "", after: str = "",
              prompt: str = "", selection: str = "") -> dict[str, str]:
    """Build the scoring context from the same windows used for generation."""
    ctx: dict[str, str] = {}
    prompt = (prompt or "").strip()
    if prompt:
        ctx[PROMPT_KEY] = prompt
    selection = (selection or "").strip()
    if selection:
        ctx["Selected text to replace"] = selection[:SELECTION_CHARS]


    ctx["Text before this block"] = (before or "")[-BEFORE_CHARS:].strip() or "(Start of note; no preceding text)"
    ctx["Text after this block"] = (after or "")[:AFTER_CHARS].strip() or "(End of note; no following text)"
    return ctx


def material(facts: Sequence[str]) -> str:
    """Render run evidence, retaining correction notices before ordinary facts."""


    # Dropping a correction can make a retained, outdated fact appear authoritative.
    notices = [f for f in facts if NOTICE_MARK in (f or "")]
    ordered = notices + [f for f in facts if NOTICE_MARK not in (f or "")]
    lines: list[str] = []
    used = 0
    for fact in ordered:
        text = (fact or "").strip()
        if not text:
            continue
        if len(text) > FACT_CHARS:
            text = text[:FACT_CHARS] + "…"
        if used + len(text) > MATERIAL_CHARS and lines and NOTICE_MARK not in text:
            break
        lines.append("- " + text)
        used += len(text)
    if not lines:
        return ""
    kept = len(lines)
    total = sum(1 for f in facts if (f or "").strip())
    if kept < total:
        lines.append(f"(Showing {kept} of {total} evidence items, including correction notices. "
                     "Omitted evidence may still exist in the knowledge base; "
                     "do not classify a claim as invented merely because it is absent here.)")
    return "\n".join(lines)


def with_material(context: dict[str, str] | None,
                  facts: Sequence[str]) -> dict[str, str]:
    """Attach accumulated run evidence without performing another retrieval."""
    out = dict(context or {})
    block = material(facts)
    if block:
        out[MATERIAL_KEY] = block
    return out


# Evidence and fresh text change each round; keep them after the stable prefix.
TAIL_KEYS = (MATERIAL_KEY, "New sentences in this run")


FRESH_KEY = TAIL_KEYS[1]
FRESH_CHARS = 3000


def new_sentences(content: str, before: str) -> list[str]:
    """Find sentences introduced since the run began."""
    if not (before or "").strip():
        return []
    out: list[str] = []
    # A period needs following whitespace to avoid splitting decimals and paths.
    for sent in re.split(r"(?<=[。！？!?\n])|(?<=\.)\s+(?=[A-Z\"“])", content or ""):
        s = sent.strip()
        if s and s not in before and not s.startswith(("```", "|")):
            out.append(s)
    return out


def with_fresh(context: dict[str, str] | None, content: str,
               before: str) -> dict[str, str]:
    """Attach only newly written sentences when the run began with existing text."""
    out = dict(context or {})
    fresh = new_sentences(content, before)
    if not fresh:
        return out
    lines: list[str] = []
    used = 0
    for s in fresh:
        if used + len(s) > FRESH_CHARS and lines:
            lines.append(f"({len(fresh) - len(lines)} additional sentences omitted; treat them as user text.)")
            break
        lines.append("- " + s)
        used += len(s)
    out[FRESH_KEY] = "\n".join(lines)
    return out


def split_for_prompt(context: dict[str, str] | None,
                     ) -> tuple[dict[str, str], dict[str, str]]:
    """Move changing evidence after the body to keep the prompt prefix stable."""
    ctx = dict(context or {})
    tail = {k: ctx.pop(k) for k in TAIL_KEYS if k in ctx}
    return ctx, tail


# （[LONG] §3）：


# Match the writing window until judge-specific measurements justify another limit.
SECTION_SCORING_MIN_CHARS = 4000


VERBATIM_MARK = " onward, verbatim]"


def body_for_scoring(content: str, *, keep_last_chars: int = SECTION_SCORING_MIN_CHARS,
                     ) -> str:
    """Summarize older sections while keeping recent sections verbatim."""
    from .middleware.sections import split_sections

    if not SECTION_SCORING or len(content or "") <= keep_last_chars:
        return content


    sections = split_sections(content)
    kept: list[int] = []
    total = 0
    for i in range(len(sections) - 1, -1, -1):
        if kept and total + len(sections[i][1]) > keep_last_chars:
            break
        kept.append(i)
        total += len(sections[i][1])
    kept.reverse()
    first_verbatim = kept[0]
    if first_verbatim == 0:
        return content

    lines = [f"[This note has {len(sections)} sections. The first {first_verbatim} sections "
             "are summarized below by heading, opening text and character count.]"]
    for i, (title, text) in enumerate(sections[:first_verbatim], start=1):
        lines.append(f"- Section {i}: {title or '(Untitled opening)'}: "
                     f"{_first_line(text)} ({len(text)} characters)")
    lines.append(

            'The lines above summarize sections. Use them for cross-section repetition, '
            'coherence and coverage. Judge wording and factual grounding only in the verbatim '
            'sections below. A short summary does not imply an incomplete section.'
        )
    body = "\n".join(lines) + f"\n\n[Section {first_verbatim + 1}{VERBATIM_MARK}\n" \
        + "\n".join(t for _title, t in sections[first_verbatim:]).lstrip("\n")

    # Compression must never make the input longer.
    return body if len(body) < len(content) else content


def _first_line(section: str) -> str:
    """Keep a short evidence hint for a section the judge cannot retrieve."""
    for line in section.splitlines():
        s = line.strip().lstrip("-*> ").strip()
        if not s or s.startswith("#") or s.startswith("```"):
            continue
        return s[:60] + ("…" if len(s) > 60 else "")
    return "(No body text in this section yet)"
