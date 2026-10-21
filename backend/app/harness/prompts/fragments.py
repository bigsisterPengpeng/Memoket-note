"""Shared prompt sections and citation formatting."""

from __future__ import annotations

import re


def profile_block(profile: list[str]) -> str:
    return "[Personal preferences]\n" + "\n".join(f"- {p}" for p in profile) if profile else ""


def style_anchor_block(anchors: list[str] | None) -> str:
    if not anchors:
        return ""
    return ("[Writing samples: imitate only sentence length, rhythm, tone and organization]\n"
            + "\n\n".join(f"Sample {i + 1}: {p}" for i, p in enumerate(anchors[:3]))
            + "\nThe samples' facts, people and numbers are not material for this note. Do not copy them.")


def spine_beats_block(spine: str, beats: list[str]) -> str:
    parts = []
    if spine:
        parts.append("[Core tension]\n" + spine)
    if beats:
        parts.append("[Structural beats]\n" + "\n".join(f"- {b}" for b in beats))
    return "\n\n".join(parts)


FOCUS_LABELS = {
    "spine_fidelity": "Whether the body follows the core tension instead of becoming a disconnected log",
    "beat_coverage": "Whether any structural beat lacks corresponding content",
    "topic_fidelity": "Whether this section stays on its own topic without taking content from other sections",
    "non_repetition": "Whether arguments or conclusions repeat across paragraphs or rounds",
    "coherence": "Whether endings, heading levels, numbering, formatting and claims remain internally consistent",
    "factual_grounding": "Whether claims based on retrieved facts are accurate and free of contradictions",
    "style_fit": "Whether tone, structure and wording match personal preferences",
    "prose_quality": "Whether new prose reads as natural, concrete finished writing without planning labels or filler",
    "workflow_fidelity": "Whether the note meets the selected template's actual purpose, beyond headings and formatting",
}

# Generation uses a small evidence window; the ledger and evaluator retain all facts.
WRITING_FACT_LIMIT = 12
_SOURCE_QUOTATION = re.compile(r"(?:source quotation|\u7684\u539f\u8bdd)\]")


def writing_facts(facts: list[str], limit: int = WRITING_FACT_LIMIT) -> list[str]:
    """Deduplicate in order and prioritize quotations with source provenance."""
    unique: list[str] = []
    for fact in facts:
        if fact and fact not in unique:
            unique.append(fact)
    # The second alternative supports provenance labels in existing libraries.
    sourced = [f for f in unique if _SOURCE_QUOTATION.search(f)]
    ordinary = [f for f in unique if f not in sourced]
    return (sourced + ordinary)[:max(0, limit)]


def heading_format_reminder() -> str:
    return (
        'The body has no "## " headings yet; this does not mean formatting is unnecessary. '
        'Use "## " section headings and "- " lists when ideas are parallel or progressive. '
        'Do not turn the whole continuation into undivided prose because no prior style exists. '
        'Do not use **bold** phrases as substitute section headings: bold emphasizes a conclusion '
        'inside a paragraph, while headings organize sections. Keep that distinction consistent.'
    )


_FACT_ID = re.compile(r"^\[[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+\]")


def facts_index_block(index: list[str]) -> str:
    """Put stable summaries before the changing verbatim evidence window.

    Generation has no retrieval tools. Never instruct it to fetch unavailable
    sources, or let a one-line index stand in for a full quotation.
    """
    if not index:
        return ""
    return ("[Material retrieved in earlier rounds: one-line index, originals remain stored]\n"
            + "\n".join(f"- {line}" for line in index)
            + "\nThese lines only mark directions already explored; they are not source quotations. "
              "Do not infer dates, people or numbers from them. For specific claims, use the "
              "verbatim material in [Relevant facts from the knowledge base] below.")


def tray_block(tray: list[str] | None) -> str:
    """Keep explicitly selected material separate from automatically retrieved facts."""
    if not tray:
        return ""
    return ("[Material selected by the user (tray): prioritize these items for this note]\n"
            + "\n".join(f"- {f}" for f in tray)
            + "\n\nThe user selected these items, so prioritize relevant content over automatically "
              "retrieved material. Cite each used item at the end of the corresponding sentence: "
              "copy its initial [fact-id] or [title](note://id) link unchanged. "
              "Do not supply dates, people or numbers missing from the selected material.")


def facts_block(facts: list[str]) -> str:
    if not facts:
        return ""
    block = "[Relevant facts from the knowledge base]\n" + "\n".join(f"- {f}" for f in facts)
    # Only request identifiers when the supplied material actually has them.
    if any(_FACT_ID.match(f) for f in facts):
        block += ("\n\nCitation rules: each initial [fact-id] identifies that fact. When using a fact, "
                  "copy one most direct source's [fact-id] unchanged to the end of its sentence "
                  "(for example: 'scheduled for June 30 [example-1872-5F8]'). "
                  "Use only identifiers listed above; never invent one or stack several on one sentence.")
    return block


_DATA_URI = re.compile(r"\]\(data:[a-zA-Z0-9.+/-]+;base64,[^)\s]{16,}\)")


def strip_data_uris(content: str) -> str:
    """Preserve an embedded-media marker without spending context on base64 data."""
    return _DATA_URI.sub("](embedded image)", content or "")


def content_block(content: str, empty: str = "") -> str:
    return "[Existing body]\n" + (strip_data_uris(content) or empty)
