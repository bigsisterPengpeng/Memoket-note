"""Hooks for the single-note harness: continue writing one note to completion.

Two things live here that no other harness has:

* **The skeleton.** ``spine`` (the note's central tension) and ``beats`` (its
  structural steps) are produced once in ``before_run`` and then belong to
  the run. They sit in ``st.bag`` rather than on ``State`` because only this
  harness has them -- putting them on State would be putting one feature's
  vocabulary into the shared type.
* **Outline mode.** When the user has already written the headings, those
  headings *are* the goal: continuation fills one named section at a time and
  writes no headings of its own. The whole harness changes shape around this,
  and every mechanism that touches structure has to know about it.
"""

from __future__ import annotations


import os
from typing import AsyncIterator

from .. import feedback, prompts, workflows
from ..prompts.fragments import writing_facts
from .. import agent_loop
from .. import query_cache
from ..tools import is_tool_notice
from ...util import llm
from ...editor import outline
from ...editor import intent as doc_intent
from .mirror import _record_dropped, _scrub_and_record
from ..tailing import acceptable_tail, needs_tail
from ..agent_loop import ToolTrace
from ...database import store
from ...database.retrieval import retrieve as _retrieve


from ...database.kb.relations import cn_month_to_digits as _cn_month
from ..middleware import ledger as ledger_mw
from .. import params
from .. import tray as tray_mod
from ..params import (AGENT_TOOLS, CONTINUE_MAX_TOKENS, CONTINUE_TAIL_TOKENS,
                      LEDGER_IN_PROMPT)
from ..checks import relevance
from ..checks.skeleton import (beats_budget, check_skeleton, skeleton_length_rule,
                               verify_beats)
from ..events import CUSTOM_WARNING, CUSTOM_SKELETON, Event
from ..state import State

# How many of the user's own headings become beats. Past this the skeleton
# stops being a plan and becomes a copy of the table of contents.
MAX_OUTLINE_BEATS = 12


def _facts_for_writing(st: State) -> list[str]:
    tray = [f for f in (st.bag.get("tray_lines") or []) if f]
    fresh = [f for f in (st.facts_new or []) if f not in tray]
    accumulated = [f for f in (st.facts or []) if f not in tray]
    chosen = writing_facts(fresh or accumulated[-12:])
    return tray + [f for f in chosen if f not in tray]


def refill_facts(user: str, content: str, spine: str, beats: list[str], *,
                 title: str = "", scope: str = "all", retrieve=None) -> list[str]:
    _r = retrieve or _retrieve

    def _once(c: str, s: str, b: list[str]) -> list[str]:
        try:
            more, _ids, _took = _r(user, c, s, b, limit=6,
                                   title=title, anchor_first=True, scope=scope)
            return list(more)
        except Exception:                                    # noqa: BLE001
            return []

    got = _once(content, spine, beats)
    if got:
        return got


    return _once("", spine, [])


class NoteHooks:
    """``polish`` only repairs; it never continues."""

    def __init__(self, *, polish: bool = False, spine: str = "",
                 beats: list[str] | None = None, profile: list[str] | None = None):
        self.polish = polish
        self.spine = spine
        self.beats = list(beats or [])
        self.profile = list(profile or [])

    # -------------------------------------------------------- before_run --
    async def skeleton(self, st: State) -> AsyncIterator[Event]:
        """Establish spine/beats and whether this note is an outline.

        Called by the router before the loop starts, because a failure here
        has to be reportable without a round having begun. Yields ordinary
        ``Event``s -- **one event vocabulary, no exceptions**: this used to
        yield ``(name, payload)`` tuples that the router serialised with the
        old custom names, and when the frontend switched to the AG-UI names
        the skeleton silently stopped arriving.
        """
        content = st.content
        # **Outline protection is off in polish mode.** The two are directly
        # opposed: polishing exists to fix structural defects (duplicated
        # headings, scaffolding headings, broken numbering) and outline
        # protection exists to freeze structure. Measured: polish seeds are
        # short notes with one sentence per section, which is exactly what
        # is_outline() detects, so structure froze and every revision that
        # tried to delete a duplicated heading was rejected -- non_repetition
        # scored 0 twenty times in a row.
        is_outline = (not self.polish) and outline.is_outline(content)
        st.bag["outline_mode"] = is_outline

        if is_outline and not self.beats:
            # The user built the table of contents. **Do not generate another
            # one.** This cost a user their structure once: they wrote a
            # nine-section outline for the AI to fill in, the skeleton step

            # had moved to the bottom, three sub-headings were gone and

            self.beats = [txt for _lv, txt in outline.headings(content)][:MAX_OUTLINE_BEATS]
            self.spine = self.spine or f"Fill the user's existing outline section by section: {', '.join(self.beats[:4])}…"
        elif not self.spine and not self.beats:


            budget = beats_budget(len(content))
            system = (doc_intent.block(st.ctx.intent)
                      + workflows.system_block(st.ctx.intent, "plan")
                      + feedback.system_block(st.bag.get("writing_feedback"))
                      + prompts.compose_system(prompts.SKELETON_SYSTEM, "skeleton", st.ctx.user)
                      + skeleton_length_rule(len(content)))
            try:
                parsed = await llm.complete_json(
                    [{"role": "system", "content": system},
                     {"role": "user", "content": prompts.skeleton_user(
                         st.ctx.note_title, content, self.profile)}],
                    max_tokens=1600, temperature=0.4)
                if isinstance(parsed, dict):
                    raw = parsed.get("beats")

                    self.spine, self.beats = store.clamp_skeleton(
                        str(parsed.get("spine") or ""),
                        [str(b) for b in raw][:budget] if isinstance(raw, list) else [])


                    self.spine, self.beats = store.clamp_skeleton(
                        self.spine, verify_beats(self.beats, content))
            except Exception as exc:                   # noqa: BLE001
                # Scoring still works without a skeleton -- spine_fidelity and
                # beat_coverage judge on weaker evidence, not on none. Losing
                # the whole session over it would be the worse trade.


                from ...util import llm as _llm
                yield Event.custom(CUSTOM_WARNING, {"middleware": 'skeleton', "hook": "skeleton",
                                                    "error": f"Skeleton generation failed; continuing without a skeleton: {_llm.describe_error(exc)}"})


        if half := store.truncated_beats(self.beats):
            yield Event.custom(CUSTOM_WARNING, {
                "middleware": 'skeleton', "hook": "skeleton",
                "error": (f"Stored outline items {', '.join(str(i) for i in half)} contain incomplete sentences"
                          f" (truncated by the legacy {store.LEGACY_BEAT_MAX}-character limit). "
                          f"The model receives those incomplete items. Regenerate the outline to repair them.")})
        st.bag["spine"], st.bag["beats"] = self.spine, self.beats
        st.bag["profile"] = self.profile


        notes = ([] if is_outline
                 else check_skeleton(self.spine, self.beats).notes())
        yield Event.custom(CUSTOM_SKELETON, {"spine": self.spine,
                                             "beats": self.beats,
                                             "notes": notes})

    # ------------------------------------------------------------ gather --
    async def prepare(self, st: State) -> tuple[list[str], ToolTrace]:
        llm.set_cache_key(st.ctx.note_id, st.mode.key)
        trace = ToolTrace()
        if self.polish or st.bag.get("cleanup_only"):
            # Repair rounds write nothing, so new material has nowhere to go.
            return [], trace

        spine = st.bag.get("spine", "")
        beats = st.bag.get("beats") or []
        title = st.ctx.note_title
        policy = st.bag.get("policy")


        tray = tray_mod.lines_of(st.ctx.tray)
        st.bag["tray_lines"] = tray

        # **Decide which section this round writes before retrieving.** The
        # order used to be reversed, so retrieval never knew the target and
        # every round came back with the same facts -- the model, holding
        # material about crowdfunding and told to write the "team" section,
        # could only say the same things again under a new heading.
        target = outline.next_gap(st.content) if st.bag.get("outline_mode") else None
        st.bag["outline_target"] = target

        if not AGENT_TOOLS:
            facts, _ids, _took = _retrieve(
                st.ctx.user, st.content, spine, beats, limit=6,
                title=title, anchor_first=True, scope=st.ctx.scope)
            return tray + [f for f in facts if f not in tray], trace

        # Two stages: ask the model whether and what to retrieve, then write.
        # The first version hung the tools off the continuation call itself
        # and **the model never once retrieved anything**: 4300 characters of
        # "keep writing" with the tool description tacked on the end reads as
        # "you decide", and it decided no. Making the retrieval decision its
        # own call makes *that question* the task. The model can still answer
        # "nothing needed" -- what changed is the context it is asked in.


        topics = query_cache.dispatch("list_topics", {"limit": 40}, st.ctx)
        led = ledger_mw.ledger_of(st)


        ledger_mw.note_topics(led, topics)
        msgs = [
            {"role": "system", "content": self._plan_system(st)},
            {"role": "user", "content": prompts.retrieval_plan_user(
                title, spine, beats, st.content_for_continue(),
                steer=getattr(policy, "steer", ""),
                require_verification=getattr(policy, "require_verification", False),
                topics_overview=topics,


                ledger_gaps=(ledger_mw.gap_summary(led) if LEDGER_IN_PROMPT else ""),
                section=target[0] if target else "")},
        ]


        plan_steer = getattr(policy, "steer", "") or ""
        st.bag["steer_in_plan"] = bool(plan_steer) and plan_steer in msgs[-1]["content"]

        # Mode decides which groups exist; the policy may add to them for a
        # round (escalating to verification tools, say). It may not replace
        # them -- doing so is how the skill tools became unreachable.
        groups = list(st.mode.groups)
        for extra in getattr(policy, "extra_tool_groups", ()) or ():
            if extra not in groups:
                groups.append(extra)
        _extra, trace = await agent_loop.gather_context(
            msgs, st.ctx, groups=groups,
            max_iters=getattr(policy, "tool_iters", 2),


            known_ids=set(led.get("facts") or ()))
        facts = list(trace.as_facts())

        if trace.error and not facts:
            # Fall back to the zero-LLM keyword retrieval rather than writing
            # empty-handed. One transient 500 used to push the round into the
            # known-worst state -- no material, so invent some -- while a
            # two-millisecond fallback sat unused.
            facts, _ids, _took = _retrieve(
                st.ctx.user, st.content, spine, beats, limit=6,
                title=title, anchor_first=True, scope=st.ctx.scope)

        # When last round's facts were judged unsupported, trace the top few
        # back to the original conversation lines and put them in front of the
        # model. ``fact_sources`` is a two-step tool and the model has never
        # been observed reaching the second step on its own -- the budget goes
        # on breadth in the first round.
        if getattr(policy, "require_verification", False) and trace.used:
            for fid in agent_loop.fact_ids_in(trace)[:3]:
                src = query_cache.dispatch("fact_sources", {"fact_id": fid}, st.ctx)
                if src and not is_tool_notice(src):
                    facts.append(f"[{fid} source quotation] " + src.replace("\n", " ")[:300])


        recipe = workflows.recipe_of(st.ctx.intent)
        if recipe and recipe.id == "journal" and trace.used:
            already = {f.split(" source quotation]", 1)[0].lstrip("[")
                       for f in facts if " source quotation]" in f}
            for fid in agent_loop.fact_ids_in(trace)[:3]:
                if fid in already:
                    continue
                src = query_cache.dispatch("fact_sources", {"fact_id": fid}, st.ctx)
                if src and not is_tool_notice(src):
                    facts.append(f"[{fid} source quotation] " + src.replace("\n", " ")[:300])

        # A question anchored to a specific occasion ("that time", "besides X")
        # needs the multi-hop lookup. Prompt-level instructions to choose that
        # tool were measured to have no effect on this model, so it is run
        # directly instead of hoped for.
        probe = f"{title}\n{st.content_for_continue()[-400:]}"
        if agent_loop.is_scoped_question(probe):


            hop = query_cache.dispatch(
                "search_session_context",
                {"question": f"{title}——{spine or st.content[:120]}", "limit": 10},
                st.ctx)
            hop_facts = [line.strip() for line in hop.splitlines()
                         if line.strip() and not is_tool_notice(line.strip())]
            if hop_facts:
                facts = hop_facts + facts


        context = "\n".join([title or "", spine or "", *beats, st.content,
                             relevance.queries_of(trace.calls)])

        def _refill() -> list[str]:
            return refill_facts(st.ctx.user, st.content, spine, beats,
                                title=title, scope=st.ctx.scope)

        facts, dropped = relevance.gate(facts, trace.calls, context,
                                        apply=params.RELEVANCE_FILTER,
                                        refill=_refill, normalize=_cn_month)
        st.bag["facts_irrelevant"] = dropped
        st.bag["facts_irrelevant_dropped"] = bool(params.RELEVANCE_FILTER)
        st.bag["facts_irrelevant_total"] = int(st.bag.get("facts_irrelevant_total") or 0) + len(dropped)

        return tray + [f for f in facts if f not in tray], trace

    def _plan_system(self, st: State) -> str:
        """The retrieval-planning prompt, carrying the skill menu.

        **The menu has to be here, not only in the writing prompt.** Tools
        exist on this call and nowhere else, so a model that first reads
        "these skills are available" while writing has already lost its
        chance to load one. Measured: with the menu only in the writing
        prompt, ``load_skill`` was never called once.

        Bodies are deliberately empty here -- what to retrieve is not what a
        writing skill has an opinion about, and they land in the writing
        prompt where they belong.
        """


        return (doc_intent.block(st.ctx.intent)
                + workflows.system_block(st.ctx.intent, "retrieve")
                + feedback.system_block(st.bag.get("writing_feedback"))
                + prompts.compose_system(
                    prompts.RETRIEVAL_PLAN_SYSTEM, st.mode.skill_scope, st.ctx.user,
                    st.skill_menu, []))

    # ----------------------------------------------------------- produce --
    async def produce(self, st: State) -> AsyncIterator[str]:
        if self.polish or st.bag.get("cleanup_only"):
            return

        policy = st.bag.get("policy")


        legacy = os.getenv("MEMOKET_LEGACY_WRITING_PROMPT") == "1"
        base = ((prompts.MAGIC_TAP_SYSTEM if "chart" in st.mode.groups
                 else prompts.MAGIC_TAP_SYSTEM_NOCHART)
                if legacy else
                (prompts.MAGIC_TAP_SYSTEM_LEAN if "chart" in st.mode.groups
                 else prompts.MAGIC_TAP_SYSTEM_LEAN_NOCHART))


        system = (doc_intent.block(st.ctx.intent)
                  + workflows.system_block(st.ctx.intent, "write")
                  + feedback.system_block(st.bag.get("writing_feedback"))
                  + prompts.compose_system(
                      base, st.mode.skill_scope, st.ctx.user,
                      st.skill_menu, st.skill_bodies))

        note_block = ""
        target = st.bag.get("outline_target")
        if st.bag.get("outline_mode"):
            note_block = outline.outline_block(st.content)
            if target:
                note_block += (f"\n\n**Write only the body of section [{target[0]}] in this round**. "
                               "Do not add headings or modify other sections.")


        sections = ([t for _lv, t in outline.headings(st.content)]
                    if (not target and len(outline.headings(st.content)) >= 2) else [])
        st.bag["insert_at"] = None
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompts.note_harness_continue_user(
                st.bag.get("spine", ""), st.bag.get("beats") or [],
                st.content_for_continue(), _facts_for_writing(st), self.profile,
                outline_note=note_block, sections=sections,


                facts_index=st.bag.get("facts_index"),

                tray=st.bag.get("tray_lines"),


                auto_fixes=st.bag.get("auto_fixes"),


                advisories=st.bag.get("advisories"),
                style_anchors=list(st.bag.get("style_anchors") or []))},
        ]

        text = ""
        stats: dict = {}
        temp = getattr(policy, "continue_temperature", 0.7)


        head = ""
        directive_done = not sections
        place: str | None = None
        async for piece in llm.stream(messages, max_tokens=CONTINUE_MAX_TOKENS,
                                      temperature=temp, stats=stats):
            if not directive_done:
                head += piece
                if "\n" not in head and len(head) < 120:
                    continue
                directive_done = True
                first, _nl, rest = head.partition("\n")
                place = outline.parse_place_directive(first)
                if place is None and not outline.PLACE_DIRECTIVE.match(first):
                    rest = head
                pos = outline.section_end(st.content, place) if place else None
                st.bag["insert_at"] = ({"section": place, "pos": pos} if pos is not None else None)
                piece = rest.lstrip("\n")
                if not piece:
                    continue
            text += piece
            yield piece
        if not directive_done and head:
            text += head
            yield head

        # Hitting the ceiling truncates mid-sentence -- real output ended on

        # truncation by throwing away work the model already did. Ask it to
        # finish, once.


        if stats.get("finish_reason") == "length" and needs_tail(text):
            unclosed = ((
                '\n**The final ``` code block is still open. Complete and close it before '
                'finishing**; an unclosed fence prevents correct rendering.'
            )
                        if text.count("```") % 2 == 1 else "")
            tail = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content":
                    (
                        'The preceding text was cut off mid-sentence by the output limit. Complete that '
                        'sentence and finish the current paragraph. **Do not repeat existing text** or '
                        'start a new topic.'
                    ) + unclosed},
            ]
            tail_text = ""
            async for piece in llm.stream(tail, max_tokens=CONTINUE_TAIL_TOKENS,
                                          temperature=temp):
                tail_text += piece
            if acceptable_tail(text, tail_text):
                text += tail_text
                yield tail_text

        if not text.strip():
            return

        if st.bag.get("outline_mode") and target:
            # Insert **at the target heading**, not at the end. Appending makes
            # the model create a second heading with the same name further

            # own headings are stripped: the prompt says not to write any and
            # it writes them anyway, flattening the user's ### into ##.
            body = outline.drop_already_written(
                st.content, outline.strip_headings(text))
            _record_dropped(st, text, body)
            if body:
                st.content = _scrub_and_record(st,
                    outline.insert_into(st.content, target[1], body))
            return

        # Appending repeats too -- just less visibly than in outline mode,
        # where the duplicated sections sit side by side.
        streamed = text
        text = outline.drop_already_written(st.content, text) or text
        placed = st.bag.get("insert_at")
        if placed and placed.get("pos") is not None:

            body = text
            for line in body.split("\n", 1)[:1]:
                if line.lstrip("# ").strip() == (placed.get("section") or "").strip():
                    body = body.split("\n", 1)[1] if "\n" in body else ""
            _record_dropped(st, streamed, body)
            st.content = _scrub_and_record(st,
                outline.insert_into(st.content, placed["pos"], body))
            return
        _record_dropped(st, streamed, text)
        st.content = _scrub_and_record(st,
            prompts.join_round_text(st.content, text))

    # ------------------------------------------------------------ commit --
    async def commit(self, st: State) -> None:
        from ..middleware.save import persist_if_changed
        persist_if_changed(st)
