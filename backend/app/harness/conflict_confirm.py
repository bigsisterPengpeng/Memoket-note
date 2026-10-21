"""Confirm candidate memory conflicts through a caller-supplied model; storage code does not own model orchestration."""

from __future__ import annotations

import asyncio
import concurrent.futures as _f

from . import prompts
from ..util import llm


SAY_MAX = 160


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with _f.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


def confirm_conflicts(passage: str, cands: list[dict], by_id: dict[str, dict]) -> list[dict]:
    if not cands:
        return cands
    try:
        verdict = _run(llm.complete_json(
            [{"role": "system", "content": prompts.RELATIONS_SYSTEM},
             {"role": "user", "content": prompts.relations_user(passage, cands, by_id)}],
            max_tokens=600, temperature=0.1))
    except Exception as exc:      # noqa: BLE001
        print(f'[inbox] Conflict confirmation skipped because the model is unavailable: {type(exc).__name__}: {exc}')
        return cands
    if not isinstance(verdict, list):
        return cands
    keep = {v["index"]: v for v in verdict
            if isinstance(v, dict) and isinstance(v.get("index"), int)}
    out = []
    for i, c in enumerate(cands):
        v = keep.get(i)
        if v is not None and not v.get("keep", True):
            continue

        out.append(dict(c, say=" ".join(str((v or {}).get("say") or c["say"]).split())[:SAY_MAX]))
    return out
