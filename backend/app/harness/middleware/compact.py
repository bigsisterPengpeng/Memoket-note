"""Shrink the continuation prompt when the piece gets long.

**Only the continuation prompt.** Revision and scoring keep reading the full
text: both are hunting for drift and repetition *across* the whole piece, and
compacting hides exactly what they're looking for. That's why this writes to
``bag`` instead of touching ``st.content``.

Not in BASE -- only long-form runs into the limit. Block generation produces
a few hundred characters.
"""

from __future__ import annotations


from ..state import State


class Compact:
    name = "compact"
    hooks = ("before_produce",)
    # Revise rewrites st.content in the same hook; compacting
    # before it runs would shrink the *pre-revision* text and
    # hand the continuation prompt something already stale.
    after: tuple[str, ...] = ("revise",)

    async def before_produce(self, st: State) -> None:
        st.bag["content_for_continue"] = compact_context(
            st.content, keep_last_chars=st.mode.context_keep_last)


# Deterministic, non-LLM progressive context compaction.
# Meant for the continuation prompt only, not for anything that has to judge
# the whole document (drift detection, dedup, rubric scoring) -- compressing
# the very content those need to inspect would defeat the point. See the
# caller's own decision about which prompts get the compacted vs. full
# version; this function has no opinion about that.

def _gist(section: str) -> str:
    """Cheap, deterministic per-section summary: first line (usually the
    heading or topic sentence) plus the last non-empty line (usually the
    conclusion). No LLM call -- this is a budget-reduction heuristic, not a
    quality one."""
    lines = [line.strip() for line in section.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    return f"{lines[0]} … {lines[-1]}"


DEFAULT_SUMMARY_PREAMBLE = (
    "(Summary of earlier content, for reference only -- not verbatim wording.)"
)


def compact_context(
    content: str,
    *,
    keep_last_chars: int,
    section_marker: str = "##",
    summary_preamble: str = DEFAULT_SUMMARY_PREAMBLE,
    max_summary_chars: int | None = None,
) -> str:
    """Return ``content`` unchanged if it's within ``keep_last_chars``.
    Otherwise, keep the last ``keep_last_chars`` verbatim and collapse
    everything before that into one gist line per ``section_marker``-
    delimited section, so a long-running session's prompt cost stops
    growing linearly with round count."""
    if len(content) <= keep_last_chars:
        return content

    split_at = len(content) - keep_last_chars
    # don't split mid-section: back up to the nearest section boundary at
    # or before split_at so the kept tail starts on a real section, not a
    # fragment of one that's half-compacted and half-verbatim.
    boundary = content.rfind(f"\n{section_marker}", 0, split_at)
    if boundary == -1:
        boundary = split_at
    older, recent = content[:boundary], content[boundary:]

    sections = older.split(f"\n{section_marker}")
    gists = []
    for i, section in enumerate(sections):
        text = section if i == 0 else f"{section_marker}{section}"
        gist = _gist(text)
        if gist:
            gists.append(f"- {gist}")


    if max_summary_chars is not None:
        total = 0
        kept: list[str] = []
        for g in reversed(gists):
            if total + len(g) > max_summary_chars:
                break
            kept.append(g)
            total += len(g)
        dropped = len(gists) - len(kept)
        gists = ([f"- … ({dropped} earlier sections omitted)"] if dropped else []) + list(reversed(kept))
    summary = summary_preamble + "\n" + "\n".join(gists)
    compacted = summary + "\n\n" + recent.lstrip("\n")
    # Short/terse sections can gist down to nearly their own length (or the
    # fixed preamble alone can outweigh what little there was to compress) --
    # a "compaction" that grows the output defeats its own purpose, so fall
    # back to the original rather than ever making things bigger.
    return compacted if len(compacted) < len(content) else content
