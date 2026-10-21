"""The quality floor of writing templates that code can decide. Semantic quality stays with the
workflow_fidelity dimension.

The phrase detectors below are language specific. Chinese notes are the ones measured so far, so
most patterns match Chinese user content; they are written with unicode escapes (the repo
keeps Han characters out of code) and each carries an English comment saying what it matches.
A cheap English alternative is added where one exists. Section headings are looked up through
``workflows.section_titles`` so a note written from the Chinese UI (Chinese headings) and one
from the English UI (English headings) are both recognised.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from ...editor import outline
from .. import workflows
from ..state import State
from ..types import Verdict
from .pick import pick_dimension

# Explicit "nothing recorded" filler counts as substantive: "no (relevant) records", "no (explicit)
# action items / decisions / blockers / risks", "to be confirmed", "needs to be filled in".
_LACK = re.compile(
    r"\u6682\u65e0(?:\u76f8\u5173)?\u8bb0\u5f55|\u6ca1\u6709(?:\u660e\u786e)?(?:\u884c\u52a8\u9879|\u51b3\u5b9a|\u963b\u585e|\u98ce\u9669)"
    r"|\u5f85\u786e\u8ba4|\u9700\u8981\u8865\u4e0a"
    r"|no (?:relevant )?records?|none recorded|to be confirmed|\bTB[CD]\b", re.I)
# Letters, digits and CJK ideographs (U+3400..U+9FFF).
_MEANINGFUL = re.compile(r"[A-Za-z0-9\u3400-\u9fff]")
# Generic uplifting journal lines: "this experience taught me", "every ... is a (growth | gift)",
# "the road ahead is long", "become a better me", "a precious treasure", "a chance to grow".
_UPLIFT = re.compile(
    r"\u8fd9\u6bb5\u7ecf\u5386\u8ba9\u6211\u660e\u767d|\u6bcf\u4e00\u6b21.{0,12}\u90fd\u662f.{0,12}(?:\u6210\u957f|\u793c\u7269)|\u672a\u6765\u7684\u8def\u8fd8\u5f88\u957f|"
    r"\u6210\u4e3a\u66f4\u597d\u7684\u81ea\u5df1|\u5b9d\u8d35\u7684\u8d22\u5bcc|\u6210\u957f\u7684\u5951\u673a"
    r"|this experience taught me|a better version of myself|every setback is a"
    , re.I)
# Still unresolved: "not yet decided" (two forms), "not (able to be) determined", "to be confirmed", "open".
_UNRESOLVED = re.compile(
    r"\u5c1a\u672a\u51b3\u5b9a|\u8fd8\u6ca1\u51b3\u5b9a|\u672a(?:\u80fd)?\u786e\u5b9a|\u5f85\u786e\u8ba4|\u672a\u51b3"
    r"|to be confirmed|not yet decided|undecided|\bTB[CD]\b", re.I)
# A list item with only its marker; U+3001 is the ideographic enumeration comma ("1\u3001").
_EMPTY_LIST_ITEM = re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)\u3001])\s*$")
_EMPTY_LIST_LINE = re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)\u3001])\s*\n?")
_MALFORMED_BOLD_ITEM = re.compile(r"(?m)^(\s*[-*+]\s+)\*\*[-*+]\s+\*\*")
# Bold that closes before a fullwidth closing parenthesis: **text (fullwidth-open ...** fullwidth-close.
_MALFORMED_BOLD_PAREN = re.compile(r"\*\*([^*\n]*\uff08[^*\n]*)\*\*\uff09")
_MALFORMED_BOLD_PAREN_FIX = "**\\1\uff09**"
# Future markers: "tomorrow", "next week", "plan (to / at / colon)", "will (be / at / on)".
_FUTURE = re.compile(
    r"\u660e\u5929|\u4e0b\u5468|\u8ba1\u5212(?:\u5728|\u4e8e|\uff1a|:)?|\u5c06(?:\u4f1a|\u5728|\u4e8e)"
    r"|\btomorrow\b|\bnext week\b", re.I)
# "next week" (three Chinese forms).
_NEXT_WEEK = re.compile(r"\u4e0b\u5468|\u4e0b\u4e2a\u661f\u671f|\u4e0b\u661f\u671f|\bnext week\b", re.I)
# An "in progress" status label, alone or after a colon / bold marker (ASCII or fullwidth colon).
_IN_PROGRESS = re.compile(
    r"(?:^|[*\uff1a:])\u8fdb\u884c\u4e2d(?:[*\uff1a:]|$)|(?:^|[*:])\s*in progress\s*(?:[*:]|$)", re.I | re.M)
# "decided / confirmed / determined / selected / chose / adopted <object>" up to the clause end.
_DECISION = re.compile(
    r"(?:\u51b3\u5b9a|\u786e\u8ba4|\u786e\u5b9a|\u9009\u5b9a|\u9009\u62e9|\u91c7\u7528)([^\u3002\uff01\uff1f!?\uff1b;\n\[]+)")
# "who owns <task> is (still) not (yet) decided" in the meeting material.
_UNASSIGNED_TASK = re.compile(
    r"\u8c01\u8d1f\u8d23(?P<task>[^\uff0c\u3002\uff1b\n]{1,30}?)(?:\u8fd8)?(?:\u6ca1\u6709|\u5c1a\u672a|\u672a)(?:\u786e)?\u5b9a"
)
# Journal sentences that fill an unknown step with an absence: "the (exact / latest) time / answer
# ... was not noted / left", "at / after the meeting ... was not (re)discussed / decided / formed",
# "no follow-up ... arranged / explained".
_JOURNAL_UNSUPPORTED_ABSENCE = re.compile(
    r"(?:\u5177\u4f53(?:\u7684)?|\u6700\u665a)?(?:\u65f6\u95f4|\u7b54\u6848).{0,16}(?:\u6ca1\u6709|\u6ca1).{0,24}(?:\u8bb0|\u7559\u4e0b)|"
    r"\u4f1a(?:\u4e0a|\u540e).{0,14}(?:\u6ca1\u6709|\u6ca1)(?:\u91cd\u65b0)?(?:\u8ba8\u8bba|\u51b3\u5b9a|\u5f62\u6210)|"
    r"(?:\u6ca1\u6709|\u6ca1).{0,10}(?:\u540e\u7eed|\u540e\u9762).{0,10}(?:\u5b89\u6392|\u8bf4\u6e05)"
)
# An open question in the source: "still don't know", "not sure", "no answer", "whether ... or", "whether".
_JOURNAL_OPEN = re.compile(
    r"\u8fd8\u4e0d\u77e5\u9053|\u4e0d\u786e\u5b9a|\u6ca1\u6709\u7b54\u6848|\u7a76\u7adf.{0,30}\u8fd8\u662f|\u662f\u5426")
# Self-improvement / future-test phrasing: "later I want to see", "when I look back I want to confirm",
# "can't only look at ... also look at", "wait for ... result then", "next time I should / could I ...
# earlier".
_JOURNAL_SELF_IMPROVEMENT = re.compile(
    r"\u4e4b\u540e(?:\u8fd8)?(?:\u6211)?(?:\u60f3|\u8981)\u770b|\u4e4b\u540e\u56de\u770b\u65f6.{0,12}(?:\u60f3|\u8981)\u786e\u8ba4|"
    r"\u4e4b\u540e\u56de\u770b.{0,30}(?:\u8981|\u8bb0\u4f4f|\u770b)|\u4e0d\u80fd\u53ea\u770b.{0,30}\u8fd8\u8981\u770b|"
    r"\u7b49.{0,24}(?:\u7ed3\u679c|\u4ee5\u540e).{0,16}(?:\u518d|\u56de\u5934)|"
    r"(?:\u4ee5\u540e|\u4e0b\u6b21).{0,24}(?:\u5e94\u8be5|\u8981|\u80fd\u4e0d\u80fd|\u66f4\u65e9)|\u80fd\u4e0d\u80fd\u66f4\u65e9"
)
# Inner-life words: afraid, worried, relieved, unwilling, feel, think, judge, don't know, unsure,
# maybe, if, after all, or, conflicted, sad, happy, anxious, nervous, regret.
_JOURNAL_INNER = re.compile(
    r"\u6015|\u62c5\u5fc3|\u677e(?:\u4e86)?\u4e00\u53e3\u6c14|\u4e0d\u7518\u5fc3|\u89c9\u5f97|\u8ba4\u4e3a|\u5224\u65ad|\u4e0d\u77e5\u9053|\u4e0d\u786e\u5b9a|\u4e5f\u8bb8|\u5982\u679c|\u7a76\u7adf|\u8fd8\u662f|\u77db\u76fe|"
    r"\u96be\u8fc7|\u9ad8\u5174|\u7126\u8651|\u7d27\u5f20|\u540e\u6094"
)
# Split after a sentence end (ideographic full stop, fullwidth ! ?, ASCII ! ?).
_SENTENCE_END = re.compile(r"(?<=[\u3002\uff01\uff1f!?])")
# Same, plus fullwidth and ASCII semicolons.
_CLAUSE_END = re.compile(r"(?<=[\u3002\uff01\uff1f!?\uff1b;])")
# Facts retrieved as original words carry this marker: "[<id> <original words>] ..." (hooks/note.py).
_QUOTE_MARKER = ' \u7684\u539f\u8bdd]'
_CJK = re.compile(r"[\u3400-\u9fff]")
_IDEOGRAPHS = r"[A-Za-z0-9\u3400-\u9fff]"
# Filler for an emptied open-questions section, Chinese form: "No other open questions."
_NO_OTHER_OPEN_ZH = '\u6682\u65e0\u5176\u4ed6\u672a\u51b3\u95ee\u9898\u3002'

# Section indexes of the four original recipes (see workflows.RECIPES)
DAILY_RESULTS = 0
WEEKLY_RESULTS, WEEKLY_PROGRESS, WEEKLY_NEXT = 0, 1, 3
JOURNAL_EVENTS, JOURNAL_FEELINGS, JOURNAL_LATER = 0, 1, 2
MEETING_DECISIONS, MEETING_ACTIONS, MEETING_OPEN = 1, 2, 3


def _bodies(content: str) -> dict[str, str]:
    return {title.strip(): body.strip() for title, body in outline.section_bodies(content)}


def _titles(recipe: workflows.Recipe, index: int) -> tuple[str, ...]:
    return workflows.section_titles(recipe)[index]


def _present_title(bodies: dict[str, str], titles: tuple[str, ...]) -> str:
    """The alias actually used in the note (English or Chinese); the English one when neither is."""
    for title in titles:
        if title in bodies:
            return title
    return titles[0]


def _section(bodies: dict[str, str], recipe: workflows.Recipe, index: int) -> str:
    titles = _titles(recipe, index)
    return bodies.get(_present_title(bodies, titles), "")


def _substantive(body: str) -> bool:
    if _LACK.search(body or ""):
        return True
    plain = "".join(_MEANINGFUL.findall(body or ""))
    return len(plain) >= 6


def _section_pattern(title: str) -> re.Pattern[str]:
    return re.compile(rf"(?ms)(^##\s+{re.escape(title)}\s*\n)(.*?)(?=^##\s+|\Z)")


def _drop_daily_future_from_results(text: str, title: str) -> str:
    """Drop whole in-progress / future-plan paragraphs from the results section; other sections stay."""
    pattern = _section_pattern(title)

    def clean(match: re.Match[str]) -> str:
        paragraphs = re.split(r"\n\s*\n", match.group(2).strip())
        kept = [p for p in paragraphs
                if p.strip() and not _FUTURE.search(p) and not _IN_PROGRESS.search(p)]
        body = "\n\n".join(kept)
        return match.group(1) + ("\n" + body + "\n\n" if body else "\n")

    return pattern.sub(clean, text, count=1)


def _unsupported_journal_absence_sentences(text: str, started: str) -> list[str]:
    """A step the material never described must not become 'it happened but I did not note it'."""
    if _JOURNAL_UNSUPPORTED_ABSENCE.search(started or ""):
        return []
    return [sentence for sentence in _SENTENCE_END.split(text or "")
            if _JOURNAL_UNSUPPORTED_ABSENCE.search(sentence)
            and sentence.strip() not in (started or "")]


def _drop_unsupported_journal_absence(text: str, started: str) -> str:
    for sentence in _unsupported_journal_absence_sentences(text, started):
        text = text.replace(sentence, "")
    return re.sub(r"\n{3,}", "\n\n", text)


def _journal_self_improvement_paragraphs(text: str, source: str, recipe: workflows.Recipe) -> list[str]:
    """When the source only has an open question, find the future-test / self-improvement paragraphs
    the model added."""
    if not _JOURNAL_OPEN.search(source or "") or _JOURNAL_SELF_IMPROVEMENT.search(source or ""):
        return []
    body = _section(_bodies(text), recipe, JOURNAL_LATER)
    return [p for p in re.split(r"\n\s*\n", body) if _JOURNAL_SELF_IMPROVEMENT.search(p)]


def _drop_journal_self_improvement(text: str, source: str, recipe: workflows.Recipe) -> str:
    for paragraph in _journal_self_improvement_paragraphs(text, source, recipe):
        text = text.replace(paragraph, "")
    return re.sub(r"\n{3,}", "\n\n", text)


def _replace_section(text: str, title: str, body: str) -> str:
    return _section_pattern(title).sub(lambda m: m.group(1) + "\n" + body.strip() + "\n\n", text, count=1)


def _overlap(a: str, b: str) -> float:
    left = "".join(re.findall(_IDEOGRAPHS, a or "")).lower()
    right = "".join(re.findall(_IDEOGRAPHS, b or "")).lower()
    if not left or not right:
        return 0.0
    match = SequenceMatcher(None, left, right).find_longest_match().size
    return match / min(len(left), len(right))


def _task_present(task: str, text: str) -> bool:
    """An action phrase may be reordered naturally (notify sales / sales notification), but one shared
    character is not a match."""
    needle = "".join(re.findall(_IDEOGRAPHS, task or "")).lower()
    hay = "".join(re.findall(_IDEOGRAPHS, text or "")).lower()
    if not needle:
        return False
    if needle in hay:
        return True
    width = len(needle) + 2
    return any(set(needle) <= set(hay[i:i + width])
               for i in range(max(1, len(hay) - width + 1)))


def _decision_objects(text: str) -> list[str]:
    out = []
    for match in _DECISION.finditer(text or ""):
        value = "".join(re.findall(_IDEOGRAPHS, match.group(1))).lower()
        if len(value) >= 2:
            out.append(value)
    return out


def _drop_repeated_weekly_decisions(text: str, recipe: workflows.Recipe) -> str:
    """When a decision already appears in the progress section, drop the same decision from the results
    section and keep the quantified result."""
    bodies = _bodies(text)
    decisions = _decision_objects(_section(bodies, recipe, WEEKLY_PROGRESS))
    results_title = _present_title(bodies, _titles(recipe, WEEKLY_RESULTS))
    result = bodies.get(results_title, "")
    if not result or not decisions:
        return text
    kept: list[str] = []
    for chunk in _CLAUSE_END.split(result):
        own = _decision_objects(chunk)
        repeated = any(a in b or b in a for a in own for b in decisions)
        if chunk.strip() and not repeated:
            kept.append(chunk)
    cleaned = "".join(kept).strip()
    if cleaned and cleaned != result.strip():
        return _replace_section(text, results_title, cleaned)
    return text


def _journal_role_cleanup(text: str, facts: list[str], recipe: workflows.Recipe) -> str:
    """Put the three journal sections back in their roles: prefer the user's original words, and do not
    restate the events verbatim in the feelings section."""
    bodies = _bodies(text)
    event_title = _present_title(bodies, _titles(recipe, JOURNAL_EVENTS))
    feeling_title = _present_title(bodies, _titles(recipe, JOURNAL_FEELINGS))
    event = bodies.get(event_title, "")
    feeling = bodies.get(feeling_title, "")
    if not event or not feeling:
        return text
    original_event, original_feeling = event.strip(), feeling.strip()

    originals = [f.split(_QUOTE_MARKER, 1)[1].strip() for f in facts
                 if _QUOTE_MARKER in f and len(f.split(_QUOTE_MARKER, 1)[1].strip()) >= 60]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", feeling) if p.strip()]
    # When the model already placed the user's original words in the feelings section, the model's
    # own summary next to them is usually just a paraphrase.
    if originals and len(paragraphs) > 1:
        ranked = [(max((_overlap(p, src) for src in originals), default=0.0), p)
                  for p in paragraphs]
        best_ratio, best = max(ranked, key=lambda item: item[0])
        if best_ratio >= 0.72:
            feeling = best

    event_sents = [s.strip() for s in _SENTENCE_END.split(event) if s.strip()]
    feeling_sents = [s.strip() for s in _SENTENCE_END.split(feeling) if s.strip()]
    # A sentence in the feelings section without an inner-life word that overlaps the events section
    # heavily is just a restated event: drop it.
    feeling_sents = [s for s in feeling_sents if _JOURNAL_INNER.search(s)
                     or not any(_overlap(s, e) >= 0.78 for e in event_sents)]
    # A bodily detail already written with its emotion in the feelings section is not repeated in
    # the events section.
    event_sents = [e for e in event_sents
                   if not any(_JOURNAL_INNER.search(s) and _overlap(e, s) >= 0.78
                              for s in feeling_sents)]
    event_new = "".join(event_sents).strip()
    feeling_new = "".join(feeling_sents).strip()
    if event_sents and event_new != original_event:
        text = _replace_section(text, event_title, event_new)
    if feeling_sents and feeling_new != original_feeling:
        text = _replace_section(text, feeling_title, feeling_new)
    return text


def _no_other_open_questions(sample: str) -> str:
    """Filler sentence in the language of the surrounding text."""
    return _NO_OTHER_OPEN_ZH if _CJK.search(sample or "") else "No other open questions."


def workflow_quality(st: State) -> Verdict | None:
    """Empty headings do not count as finished; plus a few high-confidence, mechanically locatable
    scenario errors."""
    recipe = workflows.recipe_of(st.ctx.intent)
    if not recipe:
        return None
    bodies = _bodies(st.content)

    # A revision replace sometimes deletes only the list text and leaves a bare '-'. That is a
    # deterministic Markdown defect; deleting the line is more reliable than another model round.
    if _MALFORMED_BOLD_ITEM.search(st.content):
        def _repair_bold_items(text: str) -> str:
            return _MALFORMED_BOLD_ITEM.sub(r"\1**", text)
        return Verdict(
            dimension=pick_dimension(st, "prose_quality"),
            message="The template body has a nested, broken bold list marker. Restored it to a plain bold list item.",
            fix=_repair_bold_items,
            fix_done=lambda text: not _MALFORMED_BOLD_ITEM.search(text),
            fix_note="Repaired a nested, broken Markdown list marker",
        )

    if _MALFORMED_BOLD_PAREN.search(st.content):
        def _repair_bold_parens(text: str) -> str:
            return _MALFORMED_BOLD_PAREN.sub(_MALFORMED_BOLD_PAREN_FIX, text)
        return Verdict(
            dimension=pick_dimension(st, "prose_quality"),
            message="A bold marker in the template body ends before the closing parenthesis. Moved the parenthesis back inside the bold span.",
            fix=_repair_bold_parens,
            fix_done=lambda text: not _MALFORMED_BOLD_PAREN.search(text),
            fix_note="Repaired a closing parenthesis that fell outside its bold marker",
        )

    if _EMPTY_LIST_ITEM.search(st.content):
        def _drop_empty_items(text: str) -> str:
            return _EMPTY_LIST_LINE.sub("", text)
        return Verdict(
            dimension=pick_dimension(st, "prose_quality"),
            message="The template body left empty list items behind. Removed the lines that have only a bullet and no content.",
            fix=_drop_empty_items,
            fix_done=lambda text: not _EMPTY_LIST_ITEM.search(text),
            fix_note="Removed empty list items",
        )

    # Name each missing section by the heading the note actually uses (English or Chinese).
    missing = [_present_title(bodies, titles) for titles in workflows.section_titles(recipe)
               if not any(_substantive(bodies.get(title, "")) for title in titles)]
    if missing:
        return Verdict(
            dimension=pick_dimension(st, "beat_coverage", "prose_quality"),
            message=(f"These {recipe.label} sections still have only a heading or filler: {', '.join(missing)}. "
                     "Write verifiable text under each; when the material has nothing, say so explicitly "
                     "instead of leaving it blank."),
        )

    if recipe.id == "daily":
        results_title = _present_title(bodies, _titles(recipe, DAILY_RESULTS))
        if hit := _FUTURE.search(bodies.get(results_title, "")):
            return Verdict(
                dimension=pick_dimension(st, "workflow_fidelity", "prose_quality"),
                message=(f"'{results_title}' contains the future marker '{hit.group(0)}'. Removed the paragraphs "
                         "with future plans from that section; keep only results that already happened there."),
                fix=lambda text: _drop_daily_future_from_results(text, results_title),
                fix_done=lambda text: not _FUTURE.search(_bodies(text).get(results_title, "")),
                fix_note=f"Removed future plans that slipped into '{results_title}'; tomorrow's actions stay in their own section",
            )

    if recipe.id == "weekly":
        results_title = _present_title(bodies, _titles(recipe, WEEKLY_RESULTS))
        next_title = _present_title(bodies, _titles(recipe, WEEKLY_NEXT))
        if hit := _NEXT_WEEK.search(bodies.get(results_title, "")):
            return Verdict(
                dimension=pick_dimension(st, "workflow_fidelity", "prose_quality"),
                message=(f"'{results_title}' contains the future marker '{hit.group(0)}'. Move that sentence to "
                         f"'{next_title}'; this week's results keep only what already happened this week."),
            )
        cleaned = _drop_repeated_weekly_decisions(st.content, recipe)
        if cleaned != st.content:
            progress_title = _present_title(bodies, _titles(recipe, WEEKLY_PROGRESS))
            return Verdict(
                dimension=pick_dimension(st, "non_repetition", "workflow_fidelity"),
                message=(f"'{results_title}' and '{progress_title}' both state the same decision. Removed the "
                         "repeated decision from the results section; results keep observable outcomes, "
                         "decisions stay in the progress section."),
                fix=lambda _text: cleaned,
                fix_done=lambda text: _drop_repeated_weekly_decisions(text, recipe) == text,
                fix_note=f"Removed from '{results_title}' a decision already stated in '{progress_title}'",
            )

    # Only the words written this round: never turn the user's own wording against them.
    fresh = st.fresh or ""
    if recipe.id == "journal":
        started = str(st.bag.get("content_at_start") or "")
        source = "\n".join([started, *(st.facts or [])])
        role_cleaned = _journal_role_cleanup(st.content, list(st.facts or []), recipe)
        if role_cleaned != st.content:
            return Verdict(
                dimension=pick_dimension(st, "non_repetition", "workflow_fidelity"),
                message=("The journal's event and feeling sections restate the same facts, or a paraphrase was "
                         "added next to the writer's own words. Kept the passage closest to the original words "
                         "in the feeling section and left pure event sentences in the event section."),
                fix=lambda _text: role_cleaned,
                fix_done=lambda text: _journal_role_cleanup(text, list(st.facts or []), recipe) == text,
                fix_note="Gave events and feelings one section each and removed the paraphrase next to the original words",
            )
        self_improvement = _journal_self_improvement_paragraphs(st.content, source, recipe)
        if self_improvement:
            sample = self_improvement[0].strip()
            return Verdict(
                dimension=pick_dimension(st, "workflow_fidelity", "prose_quality"),
                message=(f"The journal turned an open question into a future test or self-improvement goal: "
                         f"'{sample}'. Removed it; the last section keeps the writer's original open question "
                         "and does not design an answer for them."),
                fix=lambda text: _drop_journal_self_improvement(text, source, recipe),
                fix_done=lambda text: not _journal_self_improvement_paragraphs(text, source, recipe),
                fix_note="Removed the future test / self-improvement paragraph added for the user; the open question stays",
            )
        unsupported = _unsupported_journal_absence_sentences(st.content, started)
        if unsupported:
            sample = unsupported[0].strip()
            return Verdict(
                dimension=pick_dimension(st, "factual_grounding", "workflow_fidelity"),
                message=(f"The journal added a process the material never described: '{sample}'. Removed such "
                         "sentences; an unknown step must not become 'it happened but was not recorded' or "
                         "'to be confirmed' -- what the material does not say is not written."),
                fix=lambda text: _drop_unsupported_journal_absence(text, started),
                fix_done=lambda text: not _unsupported_journal_absence_sentences(text, started),
                fix_note="Removed sentences that filled an unknown step with 'happened but not recorded / to be confirmed'",
            )
    if recipe.id == "journal" and _UPLIFT.search(fresh):
        phrase = _UPLIFT.search(fresh).group(0)  # type: ignore[union-attr]
        return Verdict(
            dimension=pick_dimension(st, "prose_quality", "style_fit"),
            message=(f"The journal added a generic uplifting line: '{phrase}'. Delete it and return to what the "
                     "writer actually experienced, felt and left unresolved; do not summarise life lessons for them."),
        )

    if recipe.id == "meeting":
        decisions_title = _present_title(bodies, _titles(recipe, MEETING_DECISIONS))
        actions_title = _present_title(bodies, _titles(recipe, MEETING_ACTIONS))
        open_title = _present_title(bodies, _titles(recipe, MEETING_OPEN))
        decision = bodies.get(decisions_title, "")
        start_bodies = _bodies(str(st.bag.get("content_at_start") or ""))
        start_decision = start_bodies.get(_present_title(start_bodies, _titles(recipe, MEETING_DECISIONS)), "")
        found = _UNRESOLVED.search(decision)
        new_unresolved = (len(_UNRESOLVED.findall(decision))
                          > len(_UNRESOLVED.findall(start_decision)))
        if found and new_unresolved:
            return Verdict(
                dimension=pick_dimension(st, "factual_grounding", "prose_quality"),
                message=(f"The '{decisions_title}' section contains '{found.group(0)}', which is still unresolved. "
                         f"Move that sentence to '{open_title}'; the decisions section keeps only what the material "
                         "shows was settled."),
                advisory=True,
            )
        # An ownership gap written explicitly into the meeting material must not vanish from the notes.
        # It is not a placeholder but information that drives what happens after the meeting. Advisory
        # only, the semantic judge still runs; the next writing round receives it and adds the gap to the
        # action items or open questions.
        started = str(st.bag.get("content_at_start") or "")
        meeting_source = "\n".join([started, *(st.facts or [])])
        if owner_gap := _UNASSIGNED_TASK.search(meeting_source):
            task = owner_gap.group("task").strip()
            action = bodies.get(actions_title, "")
            unresolved = bodies.get(open_title, "")
            target = "\n".join((action, unresolved))
            if (_task_present(task, action) and _UNRESOLVED.search(action)
                    and _task_present(task, unresolved) and _UNRESOLVED.search(unresolved)):
                def _drop_duplicate_owner_gap(text: str) -> str:
                    remaining = [p for p in re.split(r"\n\s*\n|\n(?=\s*[-*+]\s+)", unresolved)
                                 if p.strip() and not _task_present(task, p)]
                    body = "\n".join(remaining).strip() or _no_other_open_questions(unresolved)
                    return _replace_section(text, open_title, body)
                return Verdict(
                    dimension=pick_dimension(st, "non_repetition", "workflow_fidelity"),
                    message=(f"The missing owner for '{task}' is written in both action items and open questions. "
                             "Kept it only in action items so the same ownership gap is not stated twice."),
                    fix=_drop_duplicate_owner_gap,
                    fix_done=lambda text: not _task_present(task, _bodies(text).get(open_title, "")),
                    fix_note=f"Kept the pending owner of '{task}' in action items only and removed the duplicate from open questions",
                )
            if not _task_present(task, target) or not _UNRESOLVED.search(target):
                return Verdict(
                    dimension=pick_dimension(st, "workflow_fidelity", "factual_grounding"),
                    message=(f"The meeting material explicitly says '{owner_gap.group(0)}', but action items and open "
                             f"questions do not keep the ownership gap for '{task}'. Add it and mark the owner as to be confirmed."),
                    advisory=True,
                )
    return None
