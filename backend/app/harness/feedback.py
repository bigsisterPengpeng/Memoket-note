"""Use accepted and reverted edits as note-specific writing preferences."""

from __future__ import annotations

import re

from .types import Dimension, Verdict

MAX_EXAMPLES = 8
MAX_TEXT = 180


def _clip(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"


def examples(data: dict | None) -> list[dict]:
    rows = [r for r in ((data or {}).get("items") or [])
            if r.get("decision") in ("accepted", "reverted")]
    return rows[:MAX_EXAMPLES]


def context_block(data: dict | None) -> str:
    """Render shared preference evidence for generation and scoring."""
    lines: list[str] = []
    for row in examples(data):
        before, after = _clip(str(row.get("del_text") or "")), _clip(str(row.get("ins_text") or ""))
        decision = "Accepted by user" if row.get("decision") == "accepted" else "Reverted by user"
        change = f"Original: [{before or '(empty)'}]; AI proposal: [{after or '(deleted)'}]"
        lines.append(f"- {decision}: {change}")
    calibration = (data or {}).get("calibration") or {}
    signals = calibration.get("signals") or []
    if signals:
        lines.append(f"- {calibration.get('samples', 0)} full-draft edit outcomes recorded. "
                     "Retention gap compares the rate of retained edits when a dimension passes versus fails:")
        for signal in signals[:6]:
            gap = int(signal.get("retention_gap") or 0)
            lines.append(f"  - {signal.get('dimension')}: {gap:+d} percentage points"
                         f" (pass {signal.get('pass_n')} / fail {signal.get('weak_n')} samples)")
        lines.append(
            '  Larger positive gaps better reflect user choices. Near-zero or negative gaps '
            'must not independently trigger rewriting.'
        )
    return "\n".join(lines)


def system_block(data: dict | None) -> str:
    block = context_block(data)
    if not block:
        return ""
    return (
        (
            '\n[Past user decisions for this note]\nThe following accepted and reverted AI edits '
            'are the highest-priority preference evidence for this note. Use accepted edits to '
            'understand the preferred treatment. Reverted edits are counterexamples: do not '
            'reintroduce them or repeat the same treatment with synonyms. These examples are '
            'preference evidence, not factual sources. Do not copy them into the note.\n'
        ) + block + "\n"
    )


USER_ALIGNMENT = Dimension(
    "user_alignment",
    (
        'Judge this round against past user decisions. Pass when it avoids reverted content'
        ' or treatments, and respects tone, information boundaries and structure reflected '
        'in accepted edits. Fail when it reintroduces reverted paragraphs, claims or '
        'patterns, or overrides accepted treatment. Feedback examples are preference '
        'evidence, not facts to copy into the text.'
    ),
)


def _squash(text: str) -> str:
    """Normalize whitespace without treating paraphrases as exact matches."""
    return re.sub(r"\s+", "", text or "")


def repeats_reverted_change(st) -> Verdict | None:
    """Reject exact replay of a substantial reverted edit in newly generated text."""
    fresh = _squash(st.fresh or "")
    if not fresh:
        return None
    for row in examples(st.bag.get("writing_feedback")):
        if row.get("decision") != "reverted":
            continue
        rejected = _squash(str(row.get("ins_text") or ""))
        if len(rejected) >= 24 and rejected in fresh:
            sample = _clip(str(row.get("ins_text") or ""))
            return Verdict(
                dimension="user_alignment",
                message=(f"This round repeated content the user previously reverted: \"{sample}\". "
                         "Remove it. Do not repeat the same addition using synonyms."),
            )
    return None
