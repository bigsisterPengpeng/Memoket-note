"""Hooks for the ``/`` block harness: chart, table, EDA, analysis, prompt,
custom.

What makes this harness different from the long-form ones is one line in
``produce``: a block *replaces* its predecessor rather than continuing it.
Everything else -- accumulating facts across rounds, keeping the charts the
tools really emitted, best-of, stopping -- is shared machinery.
"""

from __future__ import annotations

from typing import AsyncIterator

from .. import agent_loop
from ..tools import is_tool_notice
from ..middleware import ledger as ledger_mw
from ..params import LEDGER_IN_PROMPT
from ...util import llm
from ..agent_loop import ToolTrace
from .. import prompts
from ..prompts import BLOCK_SYSTEM, tray_block
from .. import tray as tray_mod
from ..state import State
from ..score_context import AFTER_CHARS, BEFORE_CHARS, SELECTION_CHARS
from ..checks.grounding_rules import fix_bold_punct
from ...editor import intent as doc_intent

# Sent into the focus round. The model has already explored by this point;
# this round exists only to turn what it found into a chart.
_FOCUS_NUDGE = (

        'Choose the most informative data already retrieved and render a chart with '
        'chart_from_text, chart_column or render_chart. This round only draws the chart; do'
        ' not retrieve more data.'
    )


class BlockHooks:
    """``prompt`` is the whole user-facing instruction for this round."""

    def __init__(self, *, prompt: str = "", selection: str = "",
                 profile: list[str] | None = None, title: str = "",
                 from_tray: bool = False):
        self.prompt = prompt
        self.selection = selection
        self.profile = list(profile or [])
        self.title = title


        self.from_tray = from_tray

    # ------------------------------------------------------------ gather --
    async def prepare(self, st: State) -> tuple[list[str], ToolTrace]:
        gaps = ""
        if LEDGER_IN_PROMPT:
            gaps = ledger_mw.gap_summary(ledger_mw.ledger_of(st))

        tray = tray_mod.lines_of(st.ctx.tray)
        st.bag["tray_lines"] = tray
        msgs = [{"role": "system", "content": self._system(st)},
                {"role": "user", "content": self._user(st, facts="", gaps=gaps)}]
        extra, trace = await agent_loop.gather_context(
            msgs, st.ctx, groups=list(st.mode.groups), max_iters=3)

        if st.mode.focus_groups and not _produced(trace, st.mode.focus_groups):


            extra2, trace2 = await agent_loop.gather_context(
                msgs + extra + [{"role": "user", "content": _FOCUS_NUDGE}],
                st.ctx, groups=list(st.mode.focus_groups), max_iters=3)
            extra += extra2


            trace.merge(trace2)

        # Tool output goes back verbatim as well as summarised. Without the
        # raw text the model never sees the mermaid render_chart produced and
        # falls back to writing its own, which is the bug this harness exists
        # to prevent.
        facts = list(trace.as_facts()) if trace.used else []
        raw = [r for _n, _a, r in trace.calls if r and not is_tool_notice(r)]

        return tray + [f for f in facts + raw if f not in tray], trace

    # ----------------------------------------------------------- produce --
    async def produce(self, st: State) -> AsyncIterator[str]:
        tray = set(st.bag.get("tray_lines") or ())
        user = self._user(st, facts="\n\n".join(f for f in st.facts if f not in tray))
        if st.steer:
            user += f"\n\n[Issues to fix from the previous round]\n{st.steer}"
        if st.content:
            user += ('\n\n[Previous block: rewrite it to fix the issues above; do not append to it]\n' + st.content
                     + (
                         "\n\nThe previous round's ```mermaid blocks came from tools and have passed rendering"
                         ' checks. **Copy them verbatim**; do not rewrite them or claim charts are '
                         'unavailable merely because no tool was called in this round.'
                     ))
        fresh = ""
        async for piece in llm.stream(
                [{"role": "system", "content": self._system(st)},
                 {"role": "user", "content": user}],
                max_tokens=st.mode.max_tokens, temperature=0.4):
            fresh += piece
            yield piece
        # Replace, don't append: each round rewrites the block from scratch.

        st.content = fix_bold_punct(fresh.strip()) or st.content

    # ------------------------------------------------------------ commit --
    async def commit(self, st: State) -> None:
        """Nothing to persist. The block is handed to the editor, which
        decides where it lands; writing it server-side would insert it twice."""

    # ------------------------------------------------------------ prompt --
    def _system(self, st: State) -> str:
        """Base rules, the skills the user scoped to block work, and the menu
        of the rest. Same treatment as the two long-form harnesses -- the six
        block modes had no skill scope at all until now, so anything a user
        configured for them silently did nothing."""


        return doc_intent.block(st.ctx.intent) + prompts.compose_system(
            BLOCK_SYSTEM, st.mode.skill_scope, st.ctx.user, st.skill_menu,
            st.skill_bodies)


    def _user(self, st: State, *, facts: str, gaps: str = "") -> str:
        """The round's user message.

        Only the cursor's neighbourhood goes in, never the whole note. With
        the whole note the model continues the *end of the document* instead
        of filling the position it was asked about, and an eight-round run
        blows the context window besides.
        """
        parts: list[str] = []
        if gaps:


            parts.append(gaps)
        parts += [f"[Note title] {self.title or 'Untitled'}",
                  f"[Task] {st.mode.task}"]
        if self.prompt.strip():
            parts.append(f"[User instruction] {self.prompt.strip()}")
        if self.selection.strip():
            parts.append('[Selected text to replace]\n'
                         + self.selection.strip()[:SELECTION_CHARS])
        if self.profile:
            parts.append('[User writing preferences]\n'
                         + "\n".join(f"- {p}" for p in self.profile))

        tray = list(st.bag.get("tray_lines") or [])
        if tray:
            parts.append(tray_block(tray))
            if self.from_tray:
                parts.append(
                    '[Scope] Write this block **only from the tray material above**. Do not add facts '
                    "absent from the tray. Use retrieved evidence only to verify the tray's claims."
                )
        if facts:
            parts.append('[Tool evidence]\n' + facts)


        parts.append('[Text before the cursor]\n' + (st.before[-BEFORE_CHARS:] or '(Start of note)'))
        if st.after.strip():
            parts.append('[Text after the cursor]\n' + st.after[:AFTER_CHARS])
        parts.append(

                '[Output]\nReturn only the block to insert at the cursor. Omit greetings and '
                'explanatory prefaces. Do not repeat the instructions or preceding document text.\n'
                '**This is a block within a note, not a standalone report.** Use headings '
                'sparingly, one level deeper than the nearest preceding heading. Do not add '
                'report-style sections such as data quality or next steps; the following text may '
                "already cover them.\nCopy chart tools' ```mermaid blocks **verbatim**. Never "
                'replace a chart with a textual placeholder such as [Bar chart: ...].'
            )
        return "\n\n".join(parts)


def _produced(trace: ToolTrace, groups: tuple[str, ...]) -> bool:
    """Did the focus groups actually yield something usable?

    Deliberately not "was a tool from those groups called". A charting tool
    that refused three times in a row -- too few data points, every value the
    same -- counts as called and drew nothing, and treating that as done is
    how the harness once shipped a chart-mode block with no chart in it.
    **Judge the output, not the behaviour.**
    """
    from ..tools import registry
    wanted = set(registry.names(list(groups)))
    return any(name in wanted and res and not is_tool_notice(res)
               for name, _args, res in trace.calls)
