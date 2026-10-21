"""Generate instruction-specific acceptance checks.

Retain only checks grounded by verbatim instruction quotes, omit requirements
already judged by code, and fall back to existing dimensions if synthesis fails."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .checks.instructions import Constraint
from .types import Dimension, LLMClient


MAX_ITEMS = 4

MAX_ITEM_CHARS = 60


MAX_INSTRUCTION_CHARS = 1200

SYNTH_SYSTEM = """Prepare an acceptance checklist for the user's current writing instruction.
Extract only explicit requirements, not generic standards such as fluent language
or clear structure. Each item must test one thing with a yes/no answer based on
the output alone.
For every item provide quote: a short verbatim excerpt from the instruction that
justifies it. Code will discard items whose quotations do not match.
Use at most 4 items; fewer is fine. Do not invent requirements.
Write concise English checks within 60 characters; retain original wording in quote.
Return only JSON: {"items":[{"check":"...","quote":"..."}]}."""

_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Item:
    text: str
    quote: str


def _norm(text: str) -> str:
    return _SPACE.sub("", (text or "")).lower()


def _grounded(item: Item, instruction: str) -> bool:
    q = _norm(item.quote)
    return len(q) >= 2 and q in _norm(instruction)


def _already_code_judged(item: Item, constraints: tuple[Constraint, ...]) -> bool:
    q = _norm(item.quote)
    return any(q and (q in _norm(c.source) or _norm(c.source) in q)
               for c in constraints)


def parse_items(raw: str) -> tuple[Item, ...]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.startswith("json"):
            text = text[4:]
    start, depth = text.find("{"), 0
    if start < 0:
        return ()
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return ()
                break
    else:
        return ()
    rows = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        return ()
    out: list[Item] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text_ = str(row.get("check") or "").strip()[:MAX_ITEM_CHARS]
        quote = str(row.get("quote") or "").strip()
        if text_ and quote:
            out.append(Item(text=text_, quote=quote))
    return tuple(out)


def keep(items: tuple[Item, ...], instruction: str,
         constraints: tuple[Constraint, ...] = ()) -> tuple[Item, ...]:
    out: list[Item] = []
    seen: set[str] = set()
    for item in items:
        key = _norm(item.text)
        if not key or key in seen:
            continue
        if not _grounded(item, instruction):
            continue
        if _already_code_judged(item, constraints):
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= MAX_ITEMS:
            break
    return tuple(out)


def to_dimensions(items: tuple[Item, ...]) -> tuple[Dimension, ...]:
    return tuple(
        Dimension(
            name=f"checklist_{i}",
            guidance=(f'The user requires: {item.text} (original instruction: "{item.quote}"). Pass only if the output fully satisfies this item; partial compliance fails.'),
            binary=True)
        for i, item in enumerate(items, 1))


async def synthesize(llm: LLMClient, instruction: str, *,
                     selection: str = "",
                     constraints: tuple[Constraint, ...] = (),
                     max_tokens: int = 400,
                     temperature: float = 0.1) -> tuple[Item, ...]:
    instruction = (instruction or "").strip()
    if not instruction or len(instruction) > MAX_INSTRUCTION_CHARS:
        return ()
    parts = [f"[User instruction]\n{instruction}"]
    if selection.strip():
        parts.append("[Original selection to replace: context for interpreting the instruction]\n"
                     + selection.strip()[:800])
    if constraints:

        parts.append("[Already checked by code: omit these from the checklist]\n"
                     + "\n".join(f"- {c.source}" for c in constraints))
    raw = await llm.complete(
        [{"role": "system", "content": SYNTH_SYSTEM},
         {"role": "user", "content": "\n\n".join(parts)}],
        max_tokens=max_tokens, temperature=temperature)
    return keep(parse_items(raw), instruction, constraints)
