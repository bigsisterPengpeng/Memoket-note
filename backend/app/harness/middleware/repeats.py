"""Mechanical near-duplicate detection, fed to scoring as evidence.

Asking the model to re-read the whole piece each round looking for repetition
doesn't work -- it stalls on that dimension for rounds at a time. Handing it
concrete candidate pairs does. The pairs are cheap (difflib, no model call)
and capped, so this is close to free.
"""

from __future__ import annotations


from difflib import SequenceMatcher
from ...editor import outline
from ..types import DupHint
from ..state import State


class Repeats:
    """Put candidate duplicate pairs in the bag for the scoring call.

    Writes to ``bag`` rather than calling anything: two different consumers
    want this (the revision prompt and the scoring call), and a middleware
    that reached into either would be coupling itself to both.
    """

    name = "repeats"
    # Twice per round, not once. Revise reads it before producing; the
    # scoring call reads it after. Between those two points ``st.content``
    # changes, and handing the scorer the pairs found in last round's text
    # would be reporting duplicates that may already be gone.
    hooks = ("before_produce", "before_judge")
    after: tuple[str, ...] = ()

    async def before_produce(self, st: State) -> None:
        st.bag["dup_hints"] = find_repeats(st.content)

    async def before_judge(self, st: State) -> None:
        st.bag["dup_hints"] = find_repeats(st.content)


# Deterministic, non-LLM near-duplicate detection.
# The mechanical-signal counterpart to evaluate(): cheap enough to run every
# round, and gives the model concrete candidate pairs to judge instead of
# asking it to re-read the whole document looking for repeats on its own --
# the same "rank, dedup, limit before injection" shape as a static analyzer's
# diagnostics, applied to prose instead of code.

DEFAULT_THRESHOLD = 0.6
DEFAULT_MAX_HINTS = 5
MIN_PARAGRAPH_LEN = 20  # shorter paragraphs (a lone heading, a short list
                        # item) produce noisy high-similarity matches that
                        # aren't meaningful repeats


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if len(p.strip()) >= MIN_PARAGRAPH_LEN]


MIN_SENTENCE_LEN = outline.MIN_SENTENCE_LEN
_sentences = outline.sentences
_strip_fences = outline.strip_fences
_blocks = outline.sentence_blocks


def _judgeable(content: str, para: str) -> list[str]:
    template = outline.template_rows(content)
    return [s for s in _sentences(para) if s not in template]


def find_restated(content: str, *, threshold: float = DEFAULT_THRESHOLD,
                  max_hints: int = DEFAULT_MAX_HINTS) -> list[DupHint]:
    scored: list[DupHint] = []
    for para in _blocks(content):
        ss = _judgeable(content, para)
        for i, a in enumerate(ss):
            for b in ss[i + 1:]:
                ratio = SequenceMatcher(None, a, b).ratio()
                if ratio >= threshold:
                    scored.append(DupHint(a=a, b=b, similarity=ratio))
    scored.sort(key=lambda h: h.similarity, reverse=True)
    seen: set[str] = set()
    out: list[DupHint] = []
    for h in scored:
        if h.a in seen or h.b in seen:
            continue
        out.append(h)
        seen.add(h.a)
        seen.add(h.b)
        if len(out) >= max_hints:
            break
    return out


def restated_ratio(content: str, *, threshold: float = DEFAULT_THRESHOLD) -> float:
    total = dup = 0
    for para in _blocks(content):
        ss = _judgeable(content, para)
        seen: list[str] = []
        for s in ss:
            total += len(s)
            if any(SequenceMatcher(None, s, t).ratio() >= threshold for t in seen):
                dup += len(s)
            seen.append(s)
    return (dup / total) if total else 0.0


def find_repeats(
    content: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    max_hints: int = DEFAULT_MAX_HINTS,
) -> list[DupHint]:
    """Pairwise-compare paragraphs in ``content``, return the highest-
    similarity pairs above ``threshold``, ranked descending and capped at
    ``max_hints``. A paragraph appears in at most one returned pair (the
    one it matched best) so the same repeated passage doesn't crowd out
    every other hint."""
    paragraphs = _paragraphs(content)
    scored: list[DupHint] = []
    for i, a in enumerate(paragraphs):
        for b in paragraphs[i + 1 :]:
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio >= threshold:
                scored.append(DupHint(a=a, b=b, similarity=ratio))
    scored.sort(key=lambda hint: hint.similarity, reverse=True)

    seen: set[str] = set()
    deduped: list[DupHint] = []
    for hint in scored:
        if hint.a in seen or hint.b in seen:
            continue
        deduped.append(hint)
        seen.add(hint.a)
        seen.add(hint.b)
        if len(deduped) >= max_hints:
            break


    if len(deduped) < max_hints:
        have = {h.a for h in deduped} | {h.b for h in deduped}
        for h in find_restated(content, threshold=threshold, max_hints=max_hints):
            if h.a in have or h.b in have:
                continue
            deduped.append(h)
            have.add(h.a)
            have.add(h.b)
            if len(deduped) >= max_hints:
                break
    return deduped
