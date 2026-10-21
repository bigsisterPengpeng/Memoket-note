"""Plan, write and extend a collection of related notes."""

from __future__ import annotations

from .fragments import (FOCUS_LABELS, content_block, facts_block, facts_index_block,
                        heading_format_reminder, profile_block, writing_facts)

PLAN_SYSTEM = """Divide the user's writing goal into an ordered list of section topics.
Each topic becomes an independent note. Topics should be parallel or progressive,
non-overlapping, and together cover the goal.
- Usually 3-8 sections are enough; a larger goal may need more. Later rounds can add gaps.
- Use short topic phrases, such as "Hardware battery-life options", without empty
  prefixes such as "Introduce" or "Explain".
- Do not nest one section's subject inside another or repeat a subject in different words.
- Ground the plan in supplied notes and facts rather than inventing an unrelated outline.
Return only a JSON array of topic strings. Match the language of the user's goal.
"""


def plan_user(goal: str, facts: list[str], folder_context: str) -> str:
    parts = [f"[Writing goal]\n{goal}"]
    if folder_context:
        parts.append(folder_context)
    if facts:
        parts.append(facts_block(facts))
    parts.append("Provide the section list.")
    return "\n\n".join(parts)


def section_write_user(section_title: str, goal: str, prior_summaries: list[str],
                       content: str, facts: list[str], folder_context: str,
                       profile: list[str], focus: str = "",
                       facts_index: list[str] | None = None) -> str:
    parts = []
    if block := profile_block(profile):
        parts.append(block)
    parts.append(f"[This note's section topic]\n{section_title}")
    if goal:
        parts.append(f"[Overall writing-plan goal]\n{goal}")
    if prior_summaries:
        parts.append("[Completed sections: avoid repeating their content; refer back only when useful]\n"
                     + "\n".join(f"- {s}" for s in prior_summaries))
    if folder_context:
        parts.append(folder_context)
    # Stable index precedes the changing verbatim evidence window.
    if facts_index:
        parts.append(facts_index_block(facts_index[-8:]))
    facts = writing_facts(facts)
    if facts:
        parts.append(facts_block(facts))
    parts.append(content_block(content, "(This section has not been started)"))
    if "##" not in content:
        parts.append(heading_format_reminder()
                     + " The note title already names the topic; do not repeat it as a level-one heading.")
    if focus:
        label = FOCUS_LABELS.get(focus, focus)
        parts.append(f"[Weakest criterion in the previous round]\n{label}; prioritize it in this round.")
    parts.append("Continue only this section's topic. Do not write material belonging to another section.")
    return "\n\n".join(parts)


MORE_SECTIONS_SYSTEM = """All planned sections have been written. Decide whether an obvious
gap in the writing goal deserves another independent section.
- No additional section is a normal completion condition; do not invent one to fill a quota.
- Propose a section only when supplied facts or existing notes contain relevant material
  not covered by any completed section.
- Compare each proposal against completed titles and their listed coverage/subheadings.
  Synonyms, reordered words or extracting an existing subheading do not make a new topic.
- Numbering, repetition, contradictions and other defects in completed sections belong
  to revision of those notes, not a new note about fixing them.
Return only a JSON array of new topic strings, or [] when none is needed.
Match the language of the writing goal.
"""


def more_sections_user(goal: str, section_summaries: list[str], facts: list[str],
                       folder_context: str) -> str:
    parts = [f"[Writing goal]\n{goal}"]
    if section_summaries:
        parts.append("[Completed section summaries]\n" + "\n".join(f"- {s}" for s in section_summaries))
    if folder_context:
        parts.append(folder_context)
    if facts:
        parts.append("[Relevant facts retrieved again this round; some may be new]\n"
                     + "\n".join(f"- {f}" for f in facts))
    parts.append("Are there any further sections worth writing?")
    return "\n\n".join(parts)


def render_tracking_doc(goal: str, status: str, sections: list[dict]) -> str:
    """Render a read-only mirror; workflow decisions use database state, not this Markdown."""
    lines = ["# Writing progress", "", "## Goal", goal or "(Not set)", "", "## Progress"]
    status_label = {"pending": "Pending", "in_progress": "In progress", "done": "Completed"}
    for section in sections:
        mark = status_label.get(section["status"], section["status"])
        lines.append(f"- {mark} **{section['title']}**")
        if section.get("summary"):
            lines.append(f"  {section['summary']}")
    lines.append("")
    plan_status_label = {"active": "In progress", "done": "Completed", "abandoned": "Stopped"}
    lines.append(f"## Plan status: {plan_status_label.get(status, status)}")
    return "\n".join(lines)
