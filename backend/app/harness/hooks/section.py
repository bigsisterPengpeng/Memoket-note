"""Hooks for one section of a folder-level writing plan.

The plan loop -- pick the next section, decide whether the plan needs more
sections, keep the tracking note in sync -- stays in the router. What runs
here is one section: gather, continue (or repair), judge, repeat.

Long-form's merge rule is the opposite of the block harness's: each round
*appends* to what is already there, so ``produce`` joins rather than
replaces, and everything written in earlier rounds stays under judgement.
"""

from __future__ import annotations

import re

from typing import AsyncIterator

from .. import prompts
from ..prompts.fragments import writing_facts
from .. import agent_loop
from .. import query_cache
from ..tools import is_tool_notice
from ...editor import outline
from .mirror import _record_dropped, _scrub_and_record
from ..tailing import acceptable_tail, needs_tail
from ...util import llm
from ..agent_loop import ToolTrace
from ..middleware import ledger as ledger_mw
from ..params import (AGENT_TOOLS, CONTINUE_MAX_TOKENS, CONTINUE_TAIL_TOKENS,
                      LEDGER_IN_PROMPT)
from ...database.retrieval import retrieve as _retrieve
from ..state import State


ANCHOR_FACTS = 4
_FACT_ID = re.compile(r"^\s*\[([^\]\s]+)\]")


def _merge_anchored(st: State, title: str, facts: list[str]) -> list[str]:
    try:
        anchored, _ids, _took = _retrieve(st.ctx.user, st.content, title, [],
                                          limit=ANCHOR_FACTS, title=title, anchor_first=True)
    except Exception:                      # noqa: BLE001
        return facts
    def fid(f: str) -> str:
        m = _FACT_ID.match(f)
        return m.group(1) if m else " ".join(f.split())[:40]
    seen: set[str] = set()
    out: list[str] = []
    for f in anchored + facts:
        k = fid(f)
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


class SectionHooks:
    """One section of a plan. ``st.ctx.note_id`` is the note it writes into."""

    def __init__(self, *, goal: str, other_summaries: list[str],
                 folder_ctx: str = "", profile: list[str] | None = None):
        self.goal = goal
        self.other_summaries = list(other_summaries)
        self.folder_ctx = folder_ctx
        self.profile = list(profile or [])

    # ------------------------------------------------------------ gather --
    async def prepare(self, st: State) -> tuple[list[str], ToolTrace]:
        llm.set_cache_key(st.ctx.note_id, st.mode.key)
        title = st.ctx.note_title
        trace = ToolTrace()
        if not AGENT_TOOLS:
            facts, _ids, _took = _retrieve(
                st.ctx.user, st.content, title, [], limit=6,
                title=title, anchor_first=True)
            return facts, trace


        topics = query_cache.dispatch("list_topics", {"limit": 40}, st.ctx)
        led = ledger_mw.ledger_of(st)


        ledger_mw.note_topics(led, topics)
        msgs = [
            {"role": "system", "content": prompts.compose_system(
                prompts.RETRIEVAL_PLAN_SYSTEM, st.mode.skill_scope, st.ctx.user,
                st.skill_menu, [])},
            {"role": "user", "content": prompts.retrieval_plan_user(
                title, self.goal, self.other_summaries, st.content,
                topics_overview=topics,


                ledger_gaps=(ledger_mw.gap_summary(led) if LEDGER_IN_PROMPT
                             else ""))},
        ]
        _extra, trace = await agent_loop.gather_context(
            msgs, st.ctx, groups=list(st.mode.groups))
        facts = _merge_anchored(st, title, list(trace.as_facts()))

        # A failed tool loop must not mean writing empty-handed: fall back to
        # the pre-agent keyword retrieval rather than producing a round with
        # no material behind it.
        if trace.error and not facts:
            facts, _ids, _took = _retrieve(
                st.ctx.user, st.content, title, [], limit=6,
                title=title, anchor_first=True)

        # A section title often anchors to a specific occasion ("that time",
        # "last week"). Those need the multi-hop lookup, which the plain tool
        # loop does not reach on its own.
        probe = f"{title}\n{st.content[-400:]}"
        if agent_loop.is_scoped_question(probe):
            hop = query_cache.dispatch(
                "search_session_context",
                {"question": f"{title}——{self.goal[:100]}", "limit": 10},
                st.ctx)
            hop_facts = [line.strip() for line in hop.splitlines()
                         if line.strip() and not is_tool_notice(line.strip())]
            facts = hop_facts + facts

        return facts, trace

    # ----------------------------------------------------------- produce --
    async def produce(self, st: State) -> AsyncIterator[str]:
        if st.bag.get("cleanup_only"):
            # The repair already happened in Revise's before_produce. Writing
            # more now is precisely what this round exists to avoid.
            return

        system = prompts.compose_system(prompts.MAGIC_TAP_SYSTEM_LEAN, st.mode.skill_scope,
                                        st.ctx.user, st.skill_menu,
                                        st.skill_bodies)
        current_facts = writing_facts(st.facts_new or st.facts[-12:])
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompts.section_write_user(
                st.ctx.note_title, self.goal, self.other_summaries,
                st.content_for_continue(), current_facts, self.folder_ctx,
                self.profile, focus=st.bag.get("focus", ""),
                facts_index=st.bag.get("facts_index"))},
        ]

        text = ""
        stats: dict = {}
        async for piece in llm.stream(messages, max_tokens=CONTINUE_MAX_TOKENS,
                                      stats=stats):
            text += piece
            yield piece
        # Hitting the token ceiling truncates mid-sentence. Finish the
        # sentence rather than dropping it -- deleting what was written is
        # the one response that loses work.

        if stats.get("finish_reason") == "length" and needs_tail(text):
            tail = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": prompts.FINISH_THE_SENTENCE},
            ]
            tail_text = ""
            async for piece in llm.stream(tail, max_tokens=CONTINUE_TAIL_TOKENS):
                tail_text += piece
            if acceptable_tail(text, tail_text):
                text += tail_text
                yield tail_text

        # Drop paragraphs the note already contains before joining. This
        # guard lived only on the single-note harness once, and the first
        # benchmark of the folder path caught verbatim repetition inside a
        # single sentence.
        streamed = text
        text = outline.drop_already_written(st.content, text) or text


        _record_dropped(st, streamed, text)
        st.content = _scrub_and_record(st, prompts.join_round_text(st.content, text))

    # ------------------------------------------------------------ commit --
    async def commit(self, st: State) -> None:
        from ..middleware.save import persist_if_changed
        persist_if_changed(st)
