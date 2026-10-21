"""Run parameters shared by the long-form harnesses.

These lived in ``routers/note_harness`` and were imported by
``routers/writing_plan`` -- the last case of one router reaching into
another.

``TOOL_GROUPS`` has already gone -- it is ``Mode.groups``. What is left is
here because it is genuinely not per-Mode: ``AGENT_TOOLS`` is an environment
switch for A/B measurement, and the two continuation budgets are safety nets
rather than configuration (see the comments below, which explain why).

The comments are the originals. They are worth keeping intact: each records
a number that was wrong once, and why.
"""

from __future__ import annotations

import os


AGENT_TOOLS = os.getenv("MEMOKET_AGENT_TOOLS", "1").lower() not in ("0", "false", "no")


LEDGER_IN_PROMPT = os.getenv("MEMOKET_LEDGER_PROMPT", "1").lower() not in (
    "0", "false", "no")


SECTION_INDEX = os.getenv("MEMOKET_SECTION_INDEX", "1").lower() not in (
    "0", "false", "no")


FACT_INDEX = os.getenv("MEMOKET_FACT_INDEX", "1").lower() not in (
    "0", "false", "no")


CONTINUE_MAX_TOKENS = 4000


CONTINUE_TAIL_TOKENS = 400


RUN_TOKEN_CAP = int(os.getenv("MEMOKET_RUN_TOKEN_CAP", "500000") or 0)


PROMPT_CHECKLIST = os.getenv("MEMOKET_PROMPT_CHECKLIST", "1").lower() not in (
    "0", "false", "no")


SUFFICIENT_CONTEXT = os.getenv("MEMOKET_SUFFICIENT_CONTEXT", "1").lower() not in (
    "0", "false", "no")


SECTION_SCORING = os.getenv("MEMOKET_SECTION_SCORING", "1").lower() not in (
    "0", "false", "no")


# |---|---:|---:|---:|---|---|---:|


RELEVANCE_FILTER = os.getenv("MEMOKET_RELEVANCE_FILTER", "1").lower() in ("1", "true", "yes")
