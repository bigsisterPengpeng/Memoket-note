"""Shared writing, revision and continuation prompts."""

from __future__ import annotations

from .fragments import (FOCUS_LABELS, content_block, facts_block,
                        heading_format_reminder, profile_block, spine_beats_block,
                        style_anchor_block, tray_block, writing_facts)

# Beats describe concrete content; rhetorical labels can leak into visible headings.
SKELETON_SYSTEM = """You are a writing adviser. Read the draft and produce an executable
content plan that will guide continuation without appearing verbatim in the body.

- "spine": one sentence identifying the core tension, question or change that drives
  the piece, not merely its topic. Without it the draft would become disconnected notes.
- "beats": 3-6 concrete things each part must make the reader understand. Prefer
  event -> judgment -> action or consequence. Include known dates, numbers, projects,
  decisions or quotations. Summarize what existing sections actually say; mark only
  genuinely missing content for addition.
- Reflect the user's preferences when supplied.
- Draft defects are errors to repair, never authorial intent. Incorrect numbering
  (1, 2, 4, 3), broken headings, fragments, empty headings, repeated conclusions,
  premature summaries and contradictory positions must not become plan requirements.
  Do not rationalize an isolated error as deliberate irony, reversal or formal design.
  A deliberate device needs corroborating cues elsewhere in the writing.
- Every beat must name concrete content: the user's experience, project, decision,
  figures or explicit judgment. "Deepen reflection", "answer reader questions" and
  "provide an actionable framework" are functions, not usable content plans.
  Generic beats can displace the user's real records with generic advice.
- Beats are internal navigation, not candidate headings. Avoid rhetorical labels such
  as "establish context", "introduce a turn", "anticipate questions" or "conclusion".
Return only JSON: {"spine": "...", "beats": ["...", "..."]}.
"""

# Shared by note and section workflows; callers supply the appropriate structural anchor.
EDIT_SYSTEM = """Edit only concrete problems located in the body; do not rewrite generally.
Prioritize cited passages, duplicate paragraph pairs, placeholders, meta-commentary and
claims contradicted by facts. Without a concrete location return []; avoid cosmetic changes.
- Do not replace / delete user-written paragraphs from before this run. Insert after them
  or make mechanical corrections without changing content.
- Missing evidence is not contradiction. Preserve names, dates and numbers unless contradicted.
- For duplicates, keep the more informative, earlier occurrence. A diagram and its prose
  explanation are not duplicates.
- Fix the error itself, not a new discussion of it. Remove resulting empty headings.
- anchor / anchor_end must be unique verbatim body excerpts; omit uncertain edits.
- sources contains used fact IDs, at most one most direct source per revision.
Return only a JSON array, at most 4 items, or [] if none is executable:
{"op":"replace|insert|delete","anchor":"start","anchor_end":"end","text":"new content","reason":"specific reason","sources":["fact-id"]}"""

_MERMAID_HINT = """For these four kinds of structured content, draw a Mermaid diagram when present:
- Dependencies: which unfinished task blocks another.
- Timelines or phases: requirements -> prototype -> production, with key milestones.
- Multiple roles: reporting lines or participants' relationships.
- Conditional branches: conditions, alternative paths and triggered actions.

A diagram may restate the same relationship explained in prose; that is its purpose.
Do not diagram unstructured narrative, reasoning or attitudes. One or two diagrams per
note are enough, not one per section. Adapt this minimal syntax without copying its content:
```mermaid
graph TD
A[Requirements confirmed] --> B[Prototype test]
B --> C[Design finalized]
```
Never put quotation marks inside bracketed node labels, including straight or curly
quotation marks copied from source text. Remove those marks entirely; do not escape
them or substitute another kind of quotation mark.
"""

MAGIC_TAP_SYSTEM_LEAN = f"""You are the coauthor of the user's note. Your output goes directly
into its body and must read as finished prose, not a plan, analysis report or AI work log.

Before writing, silently:
1. Choose one concrete unresolved question that advances the core tension. If beats
   exist, advance the next unfinished content without copying the beat's wording.
2. Select only directly relevant evidence. Skip strained analogies. If evidence is
   thin, narrow the claim rather than filling space with generalities.
3. Preserve the author's perspective, tone and strength of judgment. Connect what
   happened, its interpretation and its consequences. Do not introduce first person
   when the existing body does not use it.
4. Remove generic advice, writing-process commentary, repeated conclusions, slogans,
   abstract filler and incomplete sentences.

Finished-prose requirements:
- Write events and judgments, not "this section will" or explanations of how you write.
  Beats are internal navigation. Headings must state the subject or conclusion rather
  than labels such as writing intent, context, conflict, verification or closure.
- Each paragraph makes one clear advance with real cause, contrast or progression.
  Prefer concrete nouns and verbs over strings of abstract framework terminology.
- Use relevant dates, figures, projects, decisions and quotations from the materials.
  Copy each used source [fact-id] at the end of its sentence. Preserve the original
  subject: never turn another person's experience or an external case into "I" or "we".
- Never invent people, dates, numbers, meetings, outcomes or sources. Quantitative
  reasoning must explicitly identify assumptions. "In a discussion", "at the meeting"
  and "we found" also claim real events and require support in the body or materials.
  Without [Relevant facts from the knowledge base], do not invent a scene just to
  satisfy a beat requesting an example; skip it, reason from existing text, or say "if".
- Do not expose "knowledge base", "KB", retrieval mechanics or evidence-audit commentary
  in the note. Leave no missing-material placeholders; omit unsupported details.
- Do not rephrase existing conclusions. Numbering, grammar and heading defects belong
  to revision; do not reinterpret them as the author's intent.
- Write one complete section or 1-3 natural paragraphs, usually 150-350 characters.
  Prefer a short meaningful advance over padding. End at a full sentence and paragraph.
- Match the body's language and Markdown style. Add a heading only for a genuine topic
  transition; short continuations need no forced heading. {_MERMAID_HINT}
"""

MAGIC_TAP_SYSTEM = f"""Continue the user's writing directly in the body.

- Read the existing body first and remember its claims, conclusions and figures.
  Do not repeat the same conclusion in new words as a summary or echo.
- Never present invented content as real. Attribution to a quotation, meeting,
  project or measurement requires actual support in the supplied records.
  Illustrative numbers are useful only when explicitly marked as assumptions.
- Never create empty template placeholders, numbered filler tasks, blank owners or
  deadlines, or nonexistent source documents. Write only items supported by material.
- Do not mention knowledge-base or retrieval mechanics, "KB", or evidence-sufficiency
  disclaimers. If a needed record is absent, at most state briefly which actual record
  is needed; do not turn the note into an audit report.
- This is the user's own note. Generic textbook advice is not a substitute for the
  user's projects, mistakes, measurements and decisions. If a paragraph would fit
  any stranger's note unchanged, replace it with relevant content or keep it shorter.
- Preserve the subject of source material. Do not turn third-person observations,
  hearsay or external cases into the user's first-person experience. Skip unrelated facts.
- Before adding a section, check the topics already covered. If its content fits an
  existing heading, add details there rather than retelling it under a new heading.
  "Implementation detail" is not a reason to repeat an existing section.
- Draft defects are not writing material. Leave numbering errors, broken headings,
  fragments and empty headings to revision rather than analyzing or reproducing them.
- Continue the Markdown conventions: lists for parallel ideas, numbered lists for
  ordered steps, and bold for key conclusions. Format parallel sections consistently.
- Use a concise ## heading only at a genuine structural transition. Put headings on
  their own line, preceded by a blank line; never append ## to an existing sentence.
  A heading introduces the content below rather than restating the preceding sentence.
- Headings must carry information, not scaffolding labels such as "Closure", "Summary",
  "Expansion" or "Supplement". A "function: real title" prefix also leaks the internal
  plan; use only the substantive title. Examples describe format, not content to copy.
- {_MERMAID_HINT}
- Follow the next unfinished beat and preserve the core tension when supplied.
- Use relevant supplied facts consistently with the user's records. Paraphrase facts
  into the body's language rather than inserting a foreign-language source sentence.
- Explicitly label hypothetical numbers as assumptions, rough estimates or examples
  in every section that uses them. A number introduced hypothetically must not later
  become an established price or decision without evidence. Do not avoid useful
  quantitative reasoning merely to avoid stating its assumptions.
- Evaluate relevance: retrieved facts need not be used. Do not force an unrelated
  product record into a personal note as a strained analogy.
- Respect personal preferences and otherwise follow the existing context naturally.
- Match the body's language.
- This is one round in a checked multi-round workflow: write one section or 1-2
  paragraphs, usually 200-400 characters, and leave further topics for later rounds.
- End at a natural boundary: finish the sentence, paragraph or list. Never leave a
  dangling half-sentence for the next round to splice awkwardly.
"""

_NO_CHART_NOTE = """Do not draw diagrams in this continuation. Do not output Mermaid code blocks:
this generation step has no diagram-validation tools. The user can request an illustration
separately. Use ordered lists for steps and concise prose for dependencies or branches."""

MAGIC_TAP_SYSTEM_NOCHART = MAGIC_TAP_SYSTEM.replace(_MERMAID_HINT, _NO_CHART_NOTE)
assert MAGIC_TAP_SYSTEM_NOCHART != MAGIC_TAP_SYSTEM, "The Mermaid guidance must be replaced"

MAGIC_TAP_SYSTEM_LEAN_NOCHART = MAGIC_TAP_SYSTEM_LEAN.replace(_MERMAID_HINT, _NO_CHART_NOTE)
assert MAGIC_TAP_SYSTEM_LEAN_NOCHART != MAGIC_TAP_SYSTEM_LEAN


def skeleton_user(title: str, content: str, profile: list[str]) -> str:
    parts = []
    if block := profile_block(profile):
        parts.append(block)
    head = f"Title: {title}\n\n" if title else ""
    parts.append(f"{head}Body:\n{content}")
    return "\n\n".join(parts)


def edit_user(spine: str, beats: list[str], content: str, facts: list[str],
              profile: list[str], focus: str = "", dup_hints: list | None = None,
              outline_note: str = "", defect_lines: list[str] | None = None,
              focus_note: str = "", tried: list[tuple[str, str]] | None = None,
              fresh_paras: list[str] | None = None,
              style_anchors: list[str] | None = None) -> str:
    parts = []
    if block := profile_block(profile):
        parts.append(block)
    if block := style_anchor_block(style_anchors):
        parts.append(block)
    if outline_note:
        parts.append(outline_note)
    # None means polish mode; [] means writing mode with no editable new paragraphs.
    if fresh_paras is not None:
        if fresh_paras:
            listed = "\n".join(f"- {p[:60]}{'…' if len(p) > 60 else ''}" for p in fresh_paras[:20])
            parts.append("[Paragraphs written in this run: replace / delete only these]\n" + listed
                         + "\nUnlisted paragraphs were written by the user before this run. Only insert after them "
                           "or make mechanical numbering, heading-level or punctuation corrections without changing wording.")
        else:
            parts.append("[No new paragraphs in this run]\nAll existing paragraphs belong to the user. "
                         "Only insert or make mechanical corrections without changing wording; do not replace / delete paragraphs.")
    if block := spine_beats_block(spine, beats):
        parts.append(block)
    parts.append("[Knowledge-base facts]\n" + ("\n".join(f"- {f}" for f in facts) if facts else "(No relevant records)"))
    if focus:
        label = FOCUS_LABELS.get(focus, focus)
        block = (f"[Priority for this round]\nThe previous evaluation's weakest criterion was: {label}. "
                 "Check whether that problem is resolved. Other rules still apply, but need not be checked again one by one.")
        if focus_note:
            block += ("\nThe evaluator identified this specific problem: " + focus_note
                      + "\nLocate the corresponding passage and fix it in place.")
        parts.append(block)
    if dup_hints:
        pairs = "\n".join(
            f"- Paragraph A: {h.a[:150]}\n  Paragraph B: {h.b[:150]} (similarity {h.similarity:.0%})"
            for h in dup_hints[:5]
        )
        parts.append("[Suspected duplicate paragraph pairs: judge whether they repeat and which to keep]\n" + pairs)
    if defect_lines:
        parts.append("[Fix these passages in place]\n" + "\n".join(f"- {d}" for d in defect_lines)
                     + "\nPlaceholders: fill from evidence, delete the unsupported row/cell, or briefly state which actual record is needed."
                       "\nAudit voice or mechanism leakage: remove commentary about evidence sufficiency and references to "
                       "knowledge-base or retrieval mechanics. This is the user's note, not an audit report."
                       "\nDo not leave any flagged passage unchanged.")
    if tried:
        parts.append("[Previously attempted but not applied: do not repeat these unchanged]\n"
                     + "\n".join(f"- {a} ({why})" for a, why in tried[:8])
                     + "\nUse a genuinely different effective revision, or skip the passage and spend the budget elsewhere.")
    parts.append("[Body]\n" + content)
    return "\n\n".join(parts)


def magic_tap_user(spine: str, beats: list[str], content: str, facts: list[str],
                   profile: list[str], folder_context: str = "",
                   following: str = "", title: str = "", tray: list[str] | None = None) -> str:
    parts = []
    if title.strip():
        parts.append(f"[Note title]\n{title.strip()}")
    if block := profile_block(profile):
        parts.append(block)
    if block := spine_beats_block(spine, beats):
        parts.append(block)
    if folder_context:
        parts.append(folder_context)
    if tray:
        parts.append(tray_block(list(tray)))
        facts = [f for f in facts if f not in set(tray)]
    facts = writing_facts(facts)
    if facts:
        parts.append(facts_block(facts))
    # Put following context before the body so generation continues from the body.
    if following.strip():
        parts.append("[Existing content after the cursor: opening excerpt for continuity, do not rewrite]\n"
                     + _cut_at_boundary(following.strip(), 600))
    parts.append(content_block(content))
    if "##" not in content:
        parts.append(heading_format_reminder())
    if following.strip():
        parts.append("Continue the body above with one paragraph that flows into the existing content after the cursor. "
                     "Do not repeat that following content or introduce a new heading.")
    else:
        parts.append("Continue writing.")
    return "\n\n".join(parts)


FINISH_THE_SENTENCE = (
    "The preceding output was cut off mid-sentence by the length limit. Continue from the unfinished sentence "
    "without repeating existing content, and finish only the current paragraph.")


def _cut_at_boundary(text: str, limit: int) -> str:
    """Bound following context without cutting through a sentence or word."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    for sep in ("\n\n", "\n", "\u3002", "\uff1b", "\uff01", "\uff1f", ". ", "; ", "! ", "? "):
        i = head.rfind(sep)
        if i > limit // 3:
            return head[:i + len(sep)].rstrip()
    if " " in head:
        return head.rsplit(" ", 1)[0] + "…"
    return head + "…"


def join_round_text(content: str, round_text: str) -> str:
    """Separate rounds so a closing code fence cannot merge with the next heading."""
    if not round_text:
        return content
    if not content:
        return round_text
    return content.rstrip("\n") + "\n\n" + round_text.lstrip("\n")
