"""Structural checks: does the new text fit where it's being inserted.

Two of these carry a ``fix``. The boundary for that was established by
running both against real failing output rather than by reasoning:

* heading depth -- fixable. Sinking every heading one level is unambiguous
  and touches no words (verified: stripping ``#`` from before and after
  gives identical text).
* "too many subheadings" -- not fixable. Which one to drop is a judgement
  call, so it goes back to the model.
"""

from __future__ import annotations

import re

from ...editor import outline
from . import blockcheck
from ..middleware import repeats
from ..state import State
from ..types import Verdict
from .pick import pick_dimension

_HEADING = re.compile(r"^(#{1,6})(\s)", re.M)


def _started_with(st: State) -> str:
    return str(st.bag.get("content_at_start") or "")

# Section titles that mean "wrapping up". A block that writes its own
# conclusion right before the note's existing conclusion is fighting the
# document's structure.
_TAIL_WORDS = ("next steps", "what to look at next", "summary", "conclusion",
               '\u63a5\u4e0b\u6765', '\u4e0b\u4e00\u6b65', '\u603b\u7ed3', '\u5c0f\u7ed3')


def table_present(st: State) -> Verdict | None:
    if blockcheck.has_table(st.content):
        return None
    return Verdict(
        pick_dimension(st, "table_validity"),
        'No table was produced. Call render_table to generate a Markdown table and insert its output unchanged. Saying that a tool is needed does not call it.',
    )


def table_columns_match(st: State) -> Verdict | None:
    if not blockcheck.table_column_mismatch(st.content):
        return None
    return Verdict(
        pick_dimension(st, "table_validity"),
        'The table has rows with different column counts. Call render_table again with columns and rows. Keep missing values empty; do not invent values to align the table.',
    )


def heading_fits(st: State) -> Verdict | None:
    """Headings must sit *below* the surrounding section, not beside it."""
    gap = blockcheck.heading_gap(st.before, st.content)
    if not gap:
        return None


    delta = _sink_delta(st.before, st.content)
    return Verdict(
        pick_dimension(st, "fits_context"), gap,
        fix=lambda text: _sink_headings(st.before, text),
        fix_note=(f"Lowered this passage's headings by {delta} levels to fit the parent section. Only heading markers changed."),
    )


def _sink_delta(before: str, block: str) -> int:
    prev = re.findall(r"^(#{1,6})\s", before or "", re.M)
    needed = (len(prev[-1]) if prev else 1) + 1
    mine = re.findall(r"^(#{1,6})\s", block or "", re.M)
    if not mine:
        return 0
    return max(0, needed - min(len(h) for h in mine))


def _sink_headings(before: str, block: str) -> str:
    """Push every heading down until the shallowest is one level below the
    nearest heading above the cursor. Only ``#`` counts change."""
    delta = _sink_delta(before, block)
    if delta <= 0:
        return block
    return _HEADING.sub(
        lambda m: "#" * min(6, len(m.group(1)) + delta) + m.group(2), block)


def tail_clashes(st: State) -> Verdict | None:
    """A self-written closing section colliding with one the note already has.

    Observed: a data-visualisation block ending in "What to look at next",
    inserted directly above the note's own "Next steps" section.
    """
    if not st.after:
        return None
    existing = re.findall(r"^#{1,6}\s+(\S.*)$", st.after, re.M)
    if not any(any(w in h.lower() for w in _TAIL_WORDS) for h in existing):
        return None
    mine = re.findall(r"^#{1,6}\s+(\S.*)$", st.content, re.M)
    clashing = [h for h in mine if any(w in h.lower() for w in _TAIL_WORDS)]
    if not clashing:
        return None
    return Verdict(
        pick_dimension(st, "fits_context"),
        f'This passage adds a closing section ({clashing[0]!r}) although the following body already has one. Remove the extra closing section; the inserted passage is part of the note.',
        fix=lambda text: _drop_tail_sections(text),


        fix_note=(f'Removed the redundant closing section "{clashing[0][:24]}" and its body because a closing section already follows.'),
    )


def _drop_tail_sections(block: str) -> str:
    parts = re.split(r"(?m)^(#{1,6}\s+.*)$", block)
    out, i = [parts[0]], 1
    while i < len(parts) - 1:
        title = re.sub(r"^#+\s+", "", parts[i]).strip().lower()
        if not any(w in title for w in _TAIL_WORDS):
            out += [parts[i], parts[i + 1]]
        i += 2
    return "".join(out).rstrip() + "\n"


def outline_intact(st: State) -> Verdict | None:
    """An outline note must keep its hierarchy.

    Flattening a three-level outline into a flat list was a 20-out-of-20
    reproducible failure once. Prose instructions never stopped it; this does.
    """
    if not outline.is_outline(st.before):
        return None
    if outline.structure_intact(st.before, st.content):
        return None
    return Verdict(
        pick_dimension(st, "fits_context"),
        'The original outline hierarchy was flattened. Preserve its headings and write beneath them.',
    )


def no_same_sources_twice(st: State) -> Verdict | None:
    from .citations import same_sources_twice

    dups = same_sources_twice(st.content, _started_with(st))
    if not dups:
        return None
    a, b = dups[0]
    return Verdict(
        pick_dimension(st, "non_repetition", "style_fit"),
        f'These passages cite the same facts: "{a[:50]}..." and "{b[:50]}...". Keep the more complete passage; remove the other or reduce it to a transition. The same evidence does not establish two independent conclusions.',


        advisory=True,
    )


RESTATED_RATIO = 0.03


def no_restated_paragraph(st: State) -> Verdict | None:
    ratio = repeats.restated_ratio(st.content)
    if ratio < RESTATED_RATIO:
        return None
    dups = repeats.find_restated(st.content)
    if not dups:
        return None
    a, b = dups[0].a, dups[0].b
    return Verdict(
        pick_dimension(st, "non_repetition", "style_fit"),
        f'A paragraph repeats the same point ({ratio:.0%} of the body consists of repetition within paragraphs): "{a[:40]}" and "{b[:40]}". Delete one sentence and retain the more informative one instead of rephrasing both.',


        advisory=True,
    )


def no_repeated_lists(st: State) -> Verdict | None:
    dups = blockcheck.repeated_lists(st.content, _started_with(st))
    if not dups:
        return None
    a, b = dups[0]
    return Verdict(
        pick_dimension(st, "non_repetition", "style_fit"),
        f'The same list appears twice: "{a[:40]}" and "{b[:40]}". Keep the more complete list and replace the other with a brief reference to it.',
    )


PARA_ECHO_RATIO = 0.85

PARA_ECHO_MIN_BODY = 40


def no_echoed_text(st: State) -> Verdict | None:
    before = _started_with(st)

    hit = blockcheck.echoed_sentence(st.content, before)
    if hit:
        echo, sent = hit
        return Verdict(
            pick_dimension(st, "non_repetition", "style_fit"),
            f'The sentence repeats "{echo[:40]}" twice: "{sent[:60]}...". Delete the second occurrence.',
            fix=lambda text, e=echo: blockcheck.drop_echo(text, e),
            fix_done=lambda text, e=echo: not _echo_still_there(text, e),
            fix_note=f'Removed one duplicate occurrence of "{echo[:40]}" and retained the original.',
        )

    cite = blockcheck.repeated_citation(st.content, before)
    if cite:
        fid, para = cite
        return Verdict(
            pick_dimension(st, "non_repetition", "factual_grounding"),
            f'The paragraph cites [{fid}] twice: "{para[:50]}...". Cite each supporting fact once per paragraph.',
            fix=lambda text, f=fid: blockcheck.drop_repeated_citation(text, f),
            fix_done=lambda text, f=fid: (blockcheck.repeated_citation(text, before) or ("",))[0] != f,
            fix_note=f'Removed the duplicate [{fid}] citation from the paragraph and retained the first.',
        )

    for hint in repeats.find_repeats(st.content):
        if hint.similarity < PARA_ECHO_RATIO:
            continue
        if hint.a in before and hint.b in before:
            continue
        if min(len(_bare(hint.a)), len(_bare(hint.b))) < PARA_ECHO_MIN_BODY:
            continue
        return Verdict(
            pick_dimension(st, "non_repetition", "style_fit"),
            f'These passages are nearly identical (verbatim similarity {hint.similarity:.0%}）：「{hint.a[:45]}..." and "{hint.b[:45]}...". Keep the more informative passage and delete the other. Changing an opening does not add information.',
        )
    return None


_BARE = re.compile(r"\[[0-9A-Za-z_-]+-\d+-\d+F\d+\]|\[[^\]]{0,40}\]\(note://[^)]+\)|\s+")


def _bare(para: str) -> str:
    return _BARE.sub("", para or "")


def _echo_still_there(text: str, echo: str) -> bool:
    pat = re.compile(r"\s*".join(re.escape(ch) for ch in echo))
    return len(pat.findall(text or "")) >= 2
