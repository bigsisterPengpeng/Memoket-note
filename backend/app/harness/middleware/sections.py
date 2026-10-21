"""Keep recent sections verbatim and expose older sections through an inspectable index."""

from __future__ import annotations

from ..params import SECTION_INDEX
from ..state import State
from ..tools.longform_tools import SCRATCH_READ, SCRATCH_SECTIONS
from .compact import compact_context

SECTION_MARKER = "##"


MAX_INDEX_LINES = 40
INDEX_LINE_CHARS = 44


class Sections:
    name = "sections"
    hooks = ("before_round", "before_produce")
    after: tuple[str, ...] = ("revise",)

    async def before_round(self, st: State) -> None:
        publish(st)

    async def before_produce(self, st: State) -> None:
        publish(st)
        st.bag["content_for_continue"] = content_for_continue(
            st.content,
            keep_last_chars=st.mode.context_keep_last,
            read_back=[n for n in (st.ctx.scratch.get(SCRATCH_READ) or [])],
        )


def publish(st: State) -> list[tuple[str, str]]:
    secs = split_sections(st.content)
    st.ctx.scratch[SCRATCH_SECTIONS] = secs
    return secs


def split_sections(content: str, marker: str = SECTION_MARKER) -> list[tuple[str, str]]:
    """Split at Markdown headings while retaining original section text."""
    out: list[tuple[str, str]] = []
    head, sep, rest = content.partition(f"\n{marker}")
    if head.strip():
        out.append((_first_heading(head), head))
    if not sep:
        return out or ([("", content)] if content.strip() else [])
    for chunk in rest.split(f"\n{marker}"):
        text = f"{marker}{chunk}"
        out.append((_first_heading(text), text))
    return out


def _first_heading(section: str) -> str:
    for line in section.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("# ").strip()
    return ""


def _hint(section: str) -> str:
    for line in section.splitlines():
        s = line.strip().lstrip("-*> ").strip()
        if not s or s.startswith("#") or s.startswith("```"):
            continue
        return s[:INDEX_LINE_CHARS] + ("…" if len(s) > INDEX_LINE_CHARS else "")
    return '(No body text yet)'


def index_block(sections: list[tuple[str, str]], verbatim_from: int) -> str:
    """Render stable section numbers for read_section without presenting summaries as evidence."""
    if not sections:
        return ""
    lines = [f"[Section index: {len(sections)} sections]"]
    first = max(0, len(sections) - MAX_INDEX_LINES)
    if first:
        lines.append(f"- (Sections 1–{first} are omitted from this index; "
                     f"read_section(n) can still retrieve their full text.)")
    for i, (title, text) in enumerate(sections[first:], start=first + 1):
        mark = ' (Full text appears below)' if i >= verbatim_from else ""
        name = title or '(Untitled opening)'
        lines.append(f"- Section {i}: {name} — {_hint(text)}{mark}")
    lines.append(
        '**The lines above are an index, not original text. Call read_section(n) for the '
        'full section, using its number above.** Do not infer concrete section contents '
        'from a summary alone.'
    )
    return "\n".join(lines)


def content_for_continue(content: str, *, keep_last_chars: int,
                         read_back: list[int] | None = None) -> str:
    """Combine a compact section index, explicit read-backs and the recent verbatim tail."""
    if not SECTION_INDEX:


        return compact_context(content, keep_last_chars=keep_last_chars)
    if len(content) <= keep_last_chars:
        return content

    sections = split_sections(content)
    if len(sections) < 2:


        return compact_context(content, keep_last_chars=keep_last_chars)


    kept: list[int] = []
    total = 0
    for i in range(len(sections) - 1, -1, -1):
        if kept and total + len(sections[i][1]) > keep_last_chars:
            break
        kept.append(i)
        total += len(sections[i][1])
    kept.reverse()
    verbatim_from = kept[0] + 1

    parts = [index_block(sections, verbatim_from)]
    for n in sorted({n for n in (read_back or [])
                     if 1 <= n <= len(sections) and n < verbatim_from}):
        title, text = sections[n - 1]
        parts.append(f"[Requested section {n}: {title or 'Untitled opening'}; full text]\n{text}")


    parts.append(f"[Body from section {verbatim_from}, verbatim]\n"
                 + "\n".join(t for _title, t in sections[kept[0]:]).lstrip("\n"))
    out = "\n\n".join(p for p in parts if p)


    return out if len(out) < len(content) else content
