"""Convert a note to slides while preserving source citations."""

from __future__ import annotations

from .fragments import content_block

SLIDES_SYSTEM = """Convert a note into Marp-style Markdown slides in the note's language.
Begin with front matter, then separate slides with a standalone --- line:

---
marp: true
slides: true
---

# Note title

One-sentence conclusion.

---

## A complete claim for this slide

- Key point
- Key point

Requirements:
- One subject per slide. The title states a complete claim, such as "The EVT milestone
  moved from June to August", rather than a noun phrase such as "EVT milestone".
- Copy each source [fact-id] from the note onto the corresponding slide unchanged.
  Only use citation identifiers that actually occur in the note.
- Move existing Mermaid code blocks intact to their relevant slides; do not redraw them.
- Use 3-5 points per slide, each no longer than 40 characters. Split an overcrowded
  slide into two rather than removing substantive detail to fit.
- The first slide has the note title and a one-sentence conclusion. The last identifies
  unresolved questions and unsupported claims already present in the note.
- Let content determine the count, usually 8-20 slides. Short notes need fewer slides.
- Do not add speaker notes, a generic thank-you slide, or invented numbers or conclusions.
Output only Markdown, with no explanation or wrapper.
"""

SLIDES_TALK_EXTRA = """
Below each slide's points, add a blank line followed by a blockquote starting with > .
Use two or three conversational sentences explaining why the slide matters.
The script is separate from the 3-5 slide points and does not count toward that limit.
"""


def slides_user(title: str, content: str, style: str = "points") -> str:
    parts = [f"Note title: {title}" if title else "", content_block(content)]
    parts.append("Convert the note above into slides. "
                 + ("Points version: leave space and use one sentence per point." if style != "talk"
                    else "Script version: include a speaking script below each slide's points."))
    return "\n\n".join(p for p in parts if p)
