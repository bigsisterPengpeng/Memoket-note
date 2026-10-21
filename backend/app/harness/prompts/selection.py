"""Selection-scoped editing, verification and period-review prompts."""

from __future__ import annotations

from .fragments import facts_block, spine_beats_block

DIGEST_SYSTEM = """Review the chronologically ordered facts from a period and briefly
summarize what happened. Use Markdown level-two headings for Core conclusions,
Key decisions, Follow-ups, and Notable changes, translated to the material's language.
Use 2-4 one-sentence bullet points per section. Rely only on supplied facts.
Omit a section without relevant content rather than filling it. Output only Markdown.
"""

REWRITE_SYSTEM = """Rewrite the selected passage to fit the note's core tension,
structural beats, established tone and facts, rather than merely changing wording.
Return only JSON: {"text":"rewritten passage","reason":"why this change helps"}.
Include only the selected passage, not surrounding text. Keep comparable information
density unless context clearly calls for expansion or compression. Match its language.
"""

POLISH_SYSTEM = """Polish the selected passage: improve expression and remove ambiguity
or verbosity without changing meaning or adding information. Polishing expresses the
same meaning better; it does not rewrite the passage to change its role in context.
Return only JSON: {"text":"polished passage","reason":"what changed and why"}.
Include only the selected passage and match its language.
"""

EXPAND_SYSTEM = """Add missing context before and/or after the selected sentence or
fragment: prerequisites before it, and natural elaboration or consequences after it.
Return only JSON: {"before":"...","after":"...","sources":["verbatim supporting fact"]}.
- Decide before and after independently; leave unnecessary directions empty.
- Quote at most 3 facts actually used in sources. For conservative inference from the
  selected passage alone, use an empty sources array. Never invent provenance.
- Do not repeat the selection.
- Inspect existing content before and after the selection. If adjacent sentences
  already supply the context, leave that direction empty instead of copying it as new.
- Match the original language and connect naturally without forced ordinal transitions.
- Prefer relevant supplied facts over plausible but unsupported background. Without
  supporting material, infer conservatively; never invent names, numbers or conclusions.
"""

VERIFY_SYSTEM = """Verify the selected passage using the complete note and numbered
related facts. Return only a JSON array, with at most 4 genuinely supported findings:
{"verdict":"contradicts|supports|unknown","reason":"...","fact_index":-1}

- contradicts: identify the exact conflict with a supplied fact and its index.
  For an internal contradiction elsewhere in the note, explain where and use -1.
- supports: identify independent supporting evidence and its fact index, preferring
  retrieved facts. A separate independent statement in the note can support it with -1.
  The selected passage's own presence in the note is circular reasoning, not evidence.
- unknown: no relevant evidence permits judgment. Explain briefly and use -1.
  Missing evidence does not itself mean the passage is wrong.
Do not force findings to fill a quota. Return [] if nothing warrants a finding.
Write reasons in the passage's language; keep verdict values exactly as specified.
"""

# Bound long-note context around the selection instead of sending the whole library.
_CONTEXT_MAX_CHARS = 8000
_CONTEXT_RADIUS = 3000


def selection_context(content: str, selection: str,
                      max_chars: int = _CONTEXT_MAX_CHARS, radius: int = _CONTEXT_RADIUS) -> str:
    if len(content) <= max_chars:
        return content
    idx = content.find(selection) if selection else -1
    if idx < 0:
        return content[:max_chars] + f"\n\n… ({len(content) - max_chars} trailing characters omitted)"
    start = max(0, idx - radius)
    end = min(len(content), idx + len(selection) + radius)
    if start > 0:
        cut = content.rfind("\n\n", max(0, start - 400), start)
        if cut >= 0:
            start = cut + 2
    if end < len(content):
        cut = content.find("\n\n", end, min(len(content), end + 400))
        if cut >= 0:
            end = cut
    head = f"… ({start} preceding characters omitted)\n\n" if start > 0 else ""
    tail = f"\n\n… ({len(content) - end} trailing characters omitted)" if end < len(content) else ""
    return head + content[start:end] + tail


def rewrite_user(content: str, selection: str, spine: str, beats: list[str]) -> str:
    parts = []
    if block := spine_beats_block(spine, beats):
        parts.append(block)
    parts.append("[Complete body]\n" + selection_context(content, selection))
    parts.append("[Selected passage to edit]\n" + selection)
    return "\n\n".join(parts)


_EXPAND_NEIGHBOR_CHARS = 150


def expand_user(content: str, selection: str, facts: list[str] | None = None) -> str:
    parts = [f"[Complete body]\n{selection_context(content, selection)}",
             f"[Selection: add context before/after it]\n{selection}"]
    idx = content.find(selection)
    if idx >= 0:
        before_ctx = content[max(0, idx - _EXPAND_NEIGHBOR_CHARS):idx].strip()
        after_ctx = content[idx + len(selection):idx + len(selection) + _EXPAND_NEIGHBOR_CHARS].strip()
        parts.append("[Existing content before the selection: check for repetition before filling before]\n"
                     + (before_ctx or "(No preceding content; this is the beginning)"))
        parts.append("[Existing content after the selection: check for repetition before filling after]\n"
                     + (after_ctx or "(No following content; this is the end)"))
    if facts:
        parts.append(facts_block(facts))
    return "\n\n".join(parts)


def verify_user(content: str, selection: str, facts: list[str]) -> str:
    parts = ["[Complete note body]\n" + selection_context(content, selection),
             "[Passage to verify]\n" + selection]
    if facts:
        numbered = "\n".join(f"[{i}] {f}" for i, f in enumerate(facts))
        parts.append("[Related retrieved facts]\n" + numbered)
    else:
        parts.append("[Related retrieved facts]\n(No related records found)")
    return "\n\n".join(parts)


RELATIONS_SYSTEM = """Confirm proposed relationships between a passage and older records,
initially matched by numeric values or dates. Check whether each concerns the same
event and quantity. For a valid relation, explain in one sentence: the older record's
date/value first, then the passage's statement. Discard invalid relations.
Match the passage's language. Return only a JSON array:
{"index":0,"keep":true,"say":"one sentence"}.
"""


def relations_user(passage: str, candidates: list[dict], facts_by_id: dict[str, dict]) -> str:
    lines = [f"[Body]\n{passage.strip()[:600]}", "[Candidate relations]"]
    for i, candidate in enumerate(candidates):
        refs = "; ".join(f"[{fid}] {facts_by_id[fid].get('date', '')} {facts_by_id[fid].get('text', '')}"
                         for fid in candidate.get("fact_ids", []) if fid in facts_by_id)
        lines.append(f"{i}. {candidate.get('relation', '')}: {candidate.get('say', '')}\n   Evidence: {refs}")
    return "\n".join(lines)


def digest_user(facts: list[str]) -> str:
    return "[Facts in chronological order]\n" + "\n".join(facts)
