"""Read a current-note section without treating document text as retrieved evidence."""

from __future__ import annotations

from .registry import ToolContext, register


SCRATCH_SECTIONS = "harness_sections"
SCRATCH_READ = "harness_sections_read"


@register(
    name="read_section",
    description=(
        (
            "Read the full text of section n in the current note. The continuation prompt's "
            'section index contains short summaries; use its section number to inspect the '
            'original text.'
        )),
    params={"n": {"type": "integer",
                  "description": 'One-based section number from the section index'}},
    required=["n"],
    group="longform",


    max_calls_per_round=3,
)
def read_section(ctx: ToolContext, n: int) -> str:
    sections = ctx.scratch.get(SCRATCH_SECTIONS) or []
    if not sections:


        return '(This run has no sectioned long-form note. Continue writing directly; this tool is not applicable.)'
    try:
        idx = int(n)
    except (TypeError, ValueError):
        return f"(Section number must be an integer; received {n!r}.)"
    if not 1 <= idx <= len(sections):
        return (f"(This note has {len(sections)} sections; section {idx} does not exist. "
                f"Section numbers appear at the start of each index entry.)")
    title, text = sections[idx - 1]


    read = ctx.scratch.setdefault(SCRATCH_READ, [])
    if idx not in read:
        read.append(idx)
    return f"[Section {idx}: {title or 'Untitled opening'}; full text]\n{text}"
