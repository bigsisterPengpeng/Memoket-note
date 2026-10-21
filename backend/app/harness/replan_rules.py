"""Deterministic validation of proposed plan changes before accepting a replacement skeleton."""

from __future__ import annotations


MAX_REPLANS = 2


MAX_BEATS = 6


def should_replan(
    scores: dict[str, int],
    stuck_dims: dict[str, int],
    tool_facts: int,
    replans_used: int,
    max_replans: int = MAX_REPLANS,
) -> tuple[bool, str]:
    if replans_used >= max_replans:
        return False, ""

    beat = scores.get("beat_coverage", 2)
    spine = scores.get("spine_fidelity", 2)


    if beat < 2 and spine == 2 and stuck_dims.get("beat_coverage", 0) >= 2:
        return True, (
            "The body follows the core tension, but beat coverage has failed for two rounds. The beats may describe generic rhetorical roles that the body cannot cover, or demand content unrelated to this note. Reassess the plan against the note's purpose."
        )


    if tool_facts > 0 and beat < 2:
        return True, (
            f'This round retrieved {tool_facts} concrete knowledge-base records but beat coverage still fails. The skeleton was planned with less text and evidence. Check whether the retrieved material warrants relevant content absent from the current beats.'
        )

    return False, ""


def apply_beat_ops(beats: list[str], ops: list[dict]) -> tuple[list[str], list[str]]:
    out = list(beats)
    log: list[str] = []


    drops: list[int] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op", "")).lower()
        if kind == "rewrite":
            i = op.get("index")
            text = str(op.get("text") or "").strip()
            if isinstance(i, int) and 0 <= i < len(out) and text and text != out[i]:
                log.append(f'Rewrote beat {i + 1}: {out[i]} → {text}')
                out[i] = text
        elif kind == "drop":
            i = op.get("index")
            if isinstance(i, int) and 0 <= i < len(out):
                drops.append(i)


    drops = sorted(set(drops), reverse=True)
    for i in drops:
        if len(out) <= 1:
            break
        log.append(f'Removed beat {i + 1} because it does not serve this note: {out[i]}')
        out.pop(i)

    removed = len(beats) - len(out)
    adds = [str(op.get("text") or "").strip()
            for op in ops
            if isinstance(op, dict) and str(op.get("op", "")).lower() == "add"
            and str(op.get("text") or "").strip()]

    room = min(removed, MAX_BEATS - len(out))
    for text in adds[:max(0, room)]:
        if text in out:
            continue
        log.append(f'Added: {text}')
        out.append(text)
    if len(adds) > max(0, room):
        log.append(f'Discarded {len(adds) - max(0, room)} additions because replanning must not increase the beat count and prevent completion.')

    return out, log
