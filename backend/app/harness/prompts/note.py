"""Retrieval planning and continuation for a single-note writing workflow."""

from __future__ import annotations

from .fragments import (content_block, facts_block, facts_index_block, tray_block,
                        heading_format_reminder, profile_block, spine_beats_block,
                        style_anchor_block, writing_facts)

RETRIEVAL_PLAN_SYSTEM = """Plan retrieval for the next part of a note. Decide whether writing
it requires the user's personal records; if so, obtain the needed evidence now.
Do not write body text. Tool calls are this step's output.

Retrieve before asserting specific people, dates, figures, meeting conclusions or
decision history. When elaborating a person, product or project named in the body,
check the user's actual description rather than assuming a definition. For pure
reasoning or structural choices that require no concrete facts, reply "No retrieval needed".

Choose tools by the question:
- search_session_context: locate a particular meeting/occasion and inspect what else
  happened there. Keywords such as "that meeting", "last time" and "besides X" indicate
  occasion context. search_memory alone returns scattered matching facts, not co-occurrence.
- filter_facts: use an exact topic code from the provided topic list when available.
- search_memory: use short, concrete keywords for lexical matches, not long mixed-language queries.
- facts_in_range: inspect events during a date range.
- fact_sources: resolve a fact's exact meaning from its original quotation.

list_topics and list_entities return navigation metadata, not evidence. Do not stop
after only calling them. Retrieve each needed item once rather than repeating the
same search with superficial wording changes. Stop expanding when direct evidence
supports the next writing decision.

Preserve source subjects and their relationship to the user. Do not turn third-person
observations, hearsay or outside cases into first-person experience. Skip facts with
unclear or mismatched subjects. Over-retrieval can pull in unrelated people's material.
If a search fails, retry once with a more specific formulation. If it still fails,
continue from the existing note or identify the missing material once; do not fill
the gap with unrelated facts.

This is also the tool-enabled chart step. For a useful process or comparable numbers,
call render_chart: kind=flow with labels for steps (no values needed), or pie/bar/line
for numbers. Preserve its returned Mermaid block for verbatim insertion later.
Do not handwrite Mermaid: the body-writing step has no validation tools.

Load relevant skills now with load_skill and referenced files with read_skill_ref.
Only this step can call tools; body generation cannot load them later.
"""


def retrieval_plan_user(title: str, spine: str, beats: list[str], content: str,
                        steer: str = "", require_verification: bool = False,
                        topics_overview: str = "", section: str = "",
                        ledger_gaps: str = "") -> str:
    parts = []
    # Lead with evidence gaps, not an inventory that encourages premature stopping.
    if ledger_gaps:
        parts.append(ledger_gaps)
    if section:
        parts.append(f"[Write only the section: {section}]\n"
                     "Retrieve evidence for this section, not material already written in earlier rounds.")
    if topics_overview:
        parts.append("[Topics in this user's knowledge base; parenthesized values are fact counts]\n"
                     + topics_overview
                     + "\n\nUse these codes directly as filter_facts topic arguments. Prefer an exact topic "
                       "match over search_memory keywords, especially for long mixed-language queries.")
    if title:
        parts.append(f"[Note title]\n{title}")
    if block := spine_beats_block(spine, beats):
        parts.append(block)
    parts.append(content_block(content, "(Not started)"))
    if steer:
        parts.append("[Previous-round feedback: address this first]\n" + steer)
    if require_verification:
        parts.append("Specific claims in the previous round failed grounding. Find sources before writing "
                     "people, dates or numbers; use fact_sources to verify uncertain meanings against original quotations.")
    parts.append("Prepare to continue the note, prioritizing unfinished beats. Decide whether retrieval is needed: "
                 "call tools if it is, otherwise reply 'No retrieval needed'.")
    return "\n\n".join(parts)


REPLAN_SYSTEM = """Correct inaccurate structural beats in an existing writing plan.
The early plan had less information than the current body and retrieved material.
Change only beats that are actually wrong; do not redesign the entire plan.

Allowed operations:
- rewrite: specify index and replacement text.
- drop: specify the index of a beat that should no longer be served.
- add: specify text for a previously unanticipated content need.

Never change the spine: changing the core tension would create a different article.
Revise generic rhetorical functions into specific content grounded in this note.
Drop beats that rationalize draft defects such as wrong numbering, contradictions
or broken heading levels as intentional writing devices. Add important relevant
retrieved material only when no current beat covers it.

Do not change sound beats. Add at most as many beats as you drop, so the total
does not grow. Return only a JSON array, for example:
[{"op":"rewrite","index":0,"text":"..."},{"op":"drop","index":3},{"op":"add","text":"..."}]
Return [] if no correction is needed.
"""


def replan_user(title: str, spine: str, beats: list[str], content: str,
                facts: list[str], why: str) -> str:
    parts = [f"[Reason for replanning]\n{why}"]
    if title:
        parts.append(f"[Note title]\n{title}")
    parts.append(f"[Core tension: reference only, must not change]\n{spine or '(Empty)'}")
    parts.append("[Current structural beats: zero-based index]\n"
                 + "\n".join(f"{i}. {b}" for i, b in enumerate(beats)))
    if facts:
        parts.append("[Material retrieved this round]\n" + "\n".join(f"- {f}" for f in facts[:12]))
    parts.append("[Current body]\n" + content)
    return "\n\n".join(parts)


def note_harness_continue_user(spine: str, beats: list[str], content: str,
                               facts: list[str], profile: list[str],
                               outline_note: str = "",
                               sections: list[str] | None = None,
                               facts_index: list[str] | None = None,
                               tray: list[str] | None = None,
                               auto_fixes: list[str] | None = None,
                               advisories: list[str] | None = None,
                               style_anchors: list[str] | None = None) -> str:
    parts = []
    if block := profile_block(profile):
        parts.append(block)
    if block := style_anchor_block(style_anchors):
        parts.append(block)
    if outline_note:
        parts.append(outline_note)
    # Tell the model about deterministic edits before it reads the changed body.
    if block := auto_fix_block(auto_fixes):
        parts.append(block)
    if block := spine_beats_block(spine, beats):
        parts.append(block)
    tray = list(tray or [])
    if tray:
        parts.append(tray_block(tray))
        facts = [f for f in facts if f not in set(tray)]
    if facts_index:
        parts.append(facts_index_block(facts_index[-8:]))
    facts = writing_facts(facts)
    if facts:
        parts.append(facts_block(facts))
    parts.append(content_block(content))
    if "##" not in content:
        parts.append(heading_format_reminder())
    parts.append("Continue writing, prioritizing beats not yet substantively covered. "
                 "If no beats were provided, infer the next useful content from the body itself.")
    # Advisories guide the next output; unlike auto-fixes, they have not changed the body.
    if block := advisory_block(advisories):
        parts.append(block)
    if sections:
        parts.append(place_directive_block(sections))
    return "\n\n".join(parts)


def advisory_block(notes: list[str] | None) -> str:
    """Carry non-blocking check feedback into generation without replacing evaluator scores."""
    lines = [f"- {n}" for n in (notes or []) if n and n.strip()]
    if not lines:
        return ""
    return ("[A code check raised these points last round: address them if possible; otherwise skip without stopping]\n"
            + "\n".join(lines[:4]))


def auto_fix_block(fixes: list[str] | None) -> str:
    """Explain completed deterministic edits so the model does not undo or repeat them."""
    lines = [f"- {f}" for f in (fixes or []) if f and f.strip()]
    if not lines:
        return ""
    return ("[The body was corrected after the previous round: these changes are already done; do not undo or repeat]\n"
            + "\n".join(lines[:8]) + "\nLeave these fixes in place and continue writing.")


def place_directive_block(sections: list[str]) -> str:
    """Emit a machine-readable target while code computes the insertion position."""
    listed = "\n".join(f"- {title}" for title in sections[:24])
    return ("The first line must be a placement directive: [Place: exact heading]. "
            "Copy a heading from the existing sections below unchanged. Use [Place: end] "
            "only if no section fits. After a blank line, write the body without repeating "
            "that heading or creating another section with the same title.\n" + listed)


_FOLDER_NOTE_EXCERPT_CHARS = 600


def folder_context_block(notes: list[dict]) -> str:
    if not notes:
        return ""
    sections = []
    for note in notes:
        title = (note.get("title") or "Untitled").strip()
        excerpt = (note.get("content") or "").strip()[:_FOLDER_NOTE_EXCERPT_CHARS]
        if excerpt:
            sections.append(f"### {title}\n{excerpt}")
    if not sections:
        return ""
    return ("[Excerpts from other notes in this folder: context only; do not copy sentences or repeat their content]\n"
            + "\n\n".join(sections))
