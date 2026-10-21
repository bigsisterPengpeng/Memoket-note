"""Fix what's already written, before writing more.

Continuation only ever appends. By round three, what round one wrote may
already repeat, contradict or drift from the rest -- and nothing looks back
at it. Without this pass the text can only grow, and grows more crooked.

Not in BASE: block generation has no "already written" to fix. It rewrites
the whole block each round, which is a different operation.

The user-facing half of this is the coloured diff with per-hunk accept /
reject. That makes one property non-negotiable: **every revision must be
attributable**. A rejected suggestion is reported (a ``dropped`` event with
the reason), never silently discarded -- if the model proposed eight edits
and three were unusable, the user should be able to see which and why.
"""

from __future__ import annotations

import re
from typing import AsyncIterator

from .. import prompts
from ...util import llm
from ...editor import outline
from ..checks import grounding_rules as grounding_check
from ..events import CUSTOM_DROPPED, CUSTOM_PHASE_DELTA, CUSTOM_REVISION, CUSTOM_SCRUB, Event
from ..revision import (absorb_trailing_citations, apply_revision, breakage,
                        drop_citation_only_paragraphs, expand_sources, tidy_blank_lines,
                        reject_revision, user_text_touched)
from . import save
from ..state import State

# One pass proposes at most this many edits. Beyond it the model stops
# finding real problems and starts rephrasing for its own sake -- and each
# one still costs an anchor resolution that can go wrong.
DEFAULT_MAX_REVISIONS = 6

VALID_OPS = ("insert", "delete", "replace")

_LOCATED = re.compile(r"[「『“《`]([^」』”》`\n]{4,120})[」』”》`]")


def actionable_revision(st: State) -> bool:
    if grounding_check.placeholder_lines(st.content):
        return True
    if grounding_check.audit_voice_lines(st.content, before=_started_with(st)):
        return True
    if st.bag.get("dup_hints"):
        return True
    notes: list[str] = []
    if st.bag.get("focus_note"):
        notes.append(str(st.bag["focus_note"]))
    if st.ev is not None:
        notes.extend(score.note for score in st.ev.scores.values() if score.level < 2)
    for note in notes:
        for quoted in _LOCATED.findall(note):
            q = quoted.strip()
            if q and q in st.content:
                return True
    return False


def _started_with(st: State) -> str:
    return str(st.bag.get("content_at_start") or "")


def _protected(st: State) -> str:
    return "" if st.bag.get("polish") else _started_with(st)


def _body_lang(st: State) -> str:
    if "body_lang" not in st.bag:
        from ..checks.language import main_language
        st.bag["body_lang"] = main_language(_started_with(st))
    return str(st.bag.get("body_lang") or "")


def fresh_paragraphs(content: str, before: str) -> list[str]:
    if not (before or "").strip():
        return []
    import re
    return [p.strip() for p in re.split(r"\n\s*\n", content or "")
            if p.strip() and p.strip() not in before]


class Revise:
    name = "revise"
    hooks = ("before_produce", "after_run")
    after: tuple[str, ...] = ("repeats",)   # the pass wants this round's pairs

    async def after_run(self, st: State) -> AsyncIterator[Event]:
        n = int(st.bag.get("revisions_user_guarded") or 0)
        if n:
            yield Event.custom(CUSTOM_DROPPED, {
                "round": st.round,
                "detail": (f'Blocked {n} revisions of pre-existing text. Continuation preserves existing wording except mechanical numbering, heading-level and punctuation fixes. Use Polish to revise existing content.')})

    async def before_produce(self, st: State) -> AsyncIterator[Event]:
        # Reset first: the loop's no-progress check reads this, and a stale
        # count from an earlier round would keep a dead run alive.
        st.bag["revisions_applied"] = 0


        st.bag["revisions_proposed"] = 0
        st.bag["revisions_dropped"] = 0
        if st.round < 2 or not st.content.strip():
            return          # nothing written yet; nothing to fix
        if st.bag.get("cleanup_only") and not actionable_revision(st):


            st.bag["revision_skipped_unlocated"] = True
            return
        st.bag["revision_skipped_unlocated"] = False

        policy = st.bag.get("policy")
        max_revisions = getattr(policy, "max_revisions", DEFAULT_MAX_REVISIONS)
        # Anchors already touched **in this run**, not this pass. Two rounds
        # rewriting the same passage with nothing but wording changes is the
        # revision pass arguing with itself.
        edited: set[str] = st.bag.setdefault("edited_spans", set())


        tried: dict[str, str] = st.bag.setdefault("dropped_spans", {})
        focus = st.bag.get("focus", "")

        protected = _protected(st)

        from ...editor import intent as doc_intent
        from .. import feedback, workflows
        system = (doc_intent.block(st.ctx.intent)
                  + workflows.system_block(st.ctx.intent, "revise")
                  + feedback.system_block(st.bag.get("writing_feedback"))
                  + prompts.compose_system(
                      prompts.EDIT_SYSTEM, "edit", st.ctx.user, st.skill_menu, None))
        user = prompts.edit_user(
            st.bag.get("spine", ""), st.bag.get("beats") or [], st.content,


            list(st.facts) + list(st.bag.get("cited_facts") or []),
            st.bag.get("profile") or [], focus,
            st.bag.get("dup_hints") or [],


            fresh_paras=fresh_paragraphs(st.content, protected) if protected else None,
            # Deterministic defects go in as concrete lines. Asking the model
            # to find placeholders and audit voice by reading is strictly
            # worse than telling it which lines they are.


            defect_lines=(grounding_check.placeholder_lines(st.content)
                          + grounding_check.audit_voice_lines(
                              st.content, before=_started_with(st))),
            focus_note=st.bag.get("focus_note", ""),
            tried=list(tried.items()),
            style_anchors=list(st.bag.get("style_anchors") or []))

        try:
            # Streamed so the user can watch: this step took tens of seconds
            # with a frozen interface, and the model's reasoning -- the most
            # interesting part of it -- was being discarded. The JSON is still
            # accumulated in full before parsing.
            text = ""
            async for kind, piece in llm.stream_events(
                    [{"role": "system", "content": system},
                     {"role": "user", "content": user}],


                    max_tokens=4000, temperature=0.1):
                if kind == "output":
                    text += piece
                yield Event.custom(CUSTOM_PHASE_DELTA, {
                    "round": st.round, "phase": "edit", "kind": kind,
                    "text": piece})
        except Exception as exc:                       # noqa: BLE001
            # A failed revision pass costs this round's fixes, not the round.
            # Measured: under sustained load a single call passed the 300s
            # timeout, and with no guard here the exception escaped the SSE
            # generator -- the client saw the connection cut, not an error.


            yield Event.custom(CUSTOM_DROPPED,
                               {"round": st.round,
                                "detail": f'Revision request failed; skipped this round: {exc}'[:200]})
            return

        parsed = llm.extract_json(text)
        if not isinstance(parsed, list):
            return
        if not text.rstrip().rstrip("`").rstrip().endswith("]"):


            yield Event.custom(CUSTOM_DROPPED, {
                "round": st.round,
                "detail": f'Revision output was truncated ({len(text)} characters); applied only the {len(parsed)} completely parsed revisions.'})


        proposals = parsed[:max_revisions]
        st.bag["revisions_proposed"] = len(proposals)

        applied = 0
        # How much has already been inserted at each anchor. Two inserts at
        # the same anchor both mean "immediately after it", so the second one
        # lands in front of the first: the model handed over 「### 3. …」 then
        # 「### 4. …」 in the right order and the note ended up with 4 before
        # 3. Any "add two paragraphs in the same place" hits this.
        insert_offsets: dict[str, int] = {}
        removed_total = 0
        outline_mode = bool(st.bag.get("outline_mode"))

        for item in proposals:
            if not isinstance(item, dict):
                continue
            op = str(item.get("op") or "").lower()
            if op not in VALID_OPS:
                continue
            anchor = str(item.get("anchor") or "")
            if not anchor or anchor not in st.content:
                continue
            body = str(item.get("text") or "")
            anchor_end = str(item.get("anchor_end") or "")
            reason = str(item.get("reason") or "")
            key = " ".join(anchor.split())[:40]


            why_not = user_text_touched(st.content, op, anchor, body, anchor_end,
                                        before=protected)
            if why_not:
                st.bag["revisions_user_guarded"] = int(st.bag.get("revisions_user_guarded") or 0) + 1
                tried[key[:24]] = 'This changes content written before the run; only insertion or mechanical fixes are allowed.'
                yield Event.custom(CUSTOM_DROPPED,
                                   {"round": st.round, "detail": why_not})
                continue
            why_not = reject_revision(st.content, op, anchor, body, anchor_end,
                                      edited, before=_started_with(st),
                                      body_lang=_body_lang(st))
            if why_not:
                # Dropping a revision is **the guards working**, not an error.
                # Reported as an error it renders as a wall of red, and
                # several get dropped every round.
                tried[key[:24]] = why_not.split('; discarded')[0].split(": ")[0]
                yield Event.custom(CUSTOM_DROPPED,
                                   {"round": st.round, "detail": why_not})
                continue


            anchor_end = absorb_trailing_citations(st.content, op, anchor, anchor_end)

            updated = apply_revision(
                st.content, op, anchor, body,
                insert_offset=insert_offsets.get(anchor, 0), anchor_end=anchor_end)
            if updated == st.content:
                continue
            destructive = too_destructive(st.content, updated, removed_total)
            if destructive:
                tried[key[:24]] = 'Too much text deleted at once'
                yield Event.custom(CUSTOM_DROPPED, {"round": st.round, "detail": destructive})
                continue
            removed_total += max(0, len(st.content) - len(updated))
            broke = breakage(st.content, updated)
            if broke:
                tried[key[:24]] = f'Would split a word: "{broke}」'
                yield Event.custom(CUSTOM_DROPPED, {
                    "round": st.round,
                    "detail": f'Discarded revision that would split a word: "{broke}": {key[:24]}…'})
                continue
            if outline_mode and not outline.structure_intact(st.content, updated):
                # When the user supplied the outline, anything that alters or
                # deletes one of their headings is dropped. The prompt already
                # says not to touch them; the model does anyway. This is the
                # hard guard behind the request.
                tried[key[:24]] = 'Would change a user-written heading'
                yield Event.custom(CUSTOM_DROPPED, {
                    "round": st.round,
                    "detail": f'Discarded revision that would change a user-written heading: {(reason or op)[:60]}'})
                continue

            if op == "insert":
                insert_offsets[anchor] = insert_offsets.get(anchor, 0) + len(body)
            st.content = tidy_blank_lines(updated)
            if op in ("replace", "delete"):
                edited.add(key)
            tried.pop(key[:24], None)
            applied += 1


            yield Event.custom(CUSTOM_REVISION, {
                "op": op,
                "anchor": anchor,
                "anchor_end": anchor_end,
                "text": body,
                "reason": reason,
                # EDIT_SYSTEM already asks the model to report which facts a
                # revision rests on. The one-shot endpoint read them and this
                # path didn't: the signal existed and was being dropped.
                "sources": expand_sources(item.get("sources") or [], st.facts)[:3],
            })

        # **Clean up after revising too.** This used to run only where
        # continuation was saved, and a single replace can put audit voice
        # straight back into the text -- measured on the folder path after
        # the continuation-side scrub was already in place.


        st.content, meta_gone = grounding_check.scrub_meta_sentences_v(
            st.content, _started_with(st))
        for sentence in meta_gone:

            yield Event.custom(CUSTOM_SCRUB, {"round": st.round, "sentence": sentence, "why": 'meta commentary'})
        for sentence in meta_gone[:3]:
            yield Event.custom(CUSTOM_DROPPED, {
                "round": st.round,
                "detail": f'Removed meta commentary that does not belong in the note: {sentence[:60]}'})


        st.content, orphan_paras = drop_citation_only_paragraphs(st.content)
        for para in orphan_paras:
            yield Event.custom(CUSTOM_SCRUB, {"round": st.round, "sentence": para, "why": 'dangling citation'})
            yield Event.custom(CUSTOM_DROPPED, {
                "round": st.round,
                "detail": f'Removed a paragraph containing citation identifiers without body text: {para[:60]}'})

        if applied or meta_gone or orphan_paras:


            save.persist(st)
        st.bag["revisions_applied"] = applied


        st.bag["revisions_dropped"] = max(0, len(proposals) - applied)
        st.bag["no_change_rounds"] = 0 if applied else st.bag.get("no_change_rounds", 0) + 1


MAX_DELETE_ONE = 0.35
MAX_DELETE_ROUND = 0.5
MIN_DELETE_GUARD = 300


def too_destructive(before: str, after: str, removed_so_far: int) -> str | None:
    removed = len(before) - len(after)
    if removed <= 0 or len(before) < MIN_DELETE_GUARD:
        return None
    base = len(before) + removed_so_far
    if removed > MAX_DELETE_ONE * base:
        return (f'Discarded revision deleting {removed} characters ({removed * 100 // base}% of the body), above the per-revision {int(MAX_DELETE_ONE * 100)}% limit.')
    if removed_so_far + removed > MAX_DELETE_ROUND * base:
        return (f"Discarded revision bringing this round's deletion to {removed_so_far + removed} characters ({(removed_so_far + removed) * 100 // base}% of the body), above the {int(MAX_DELETE_ROUND * 100)}% limit.")
    return None
