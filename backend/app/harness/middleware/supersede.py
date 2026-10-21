"""Annotate superseded facts and unresolved conflicts before generation."""

from __future__ import annotations

from .ledger import LINE_CHARS, ledger_of
from ..score_context import NOTICE_MARK
from ..state import State


MAX_ADDED = 6


def replacement_line(new_id: str, text: str, when: str, old_id: str) -> str:
    """Include the replacement fact and identify the superseded source."""
    head = f"[{new_id}] " if new_id else ""
    date = f" ({when})" if when else ""


    return (f"{head}{text}{date}{NOTICE_MARK}"
            f"This supersedes [{old_id}]; use this version when writing.")


def conflict_line(fid: str, other_id: str, say: str) -> str:
    """Flag an unresolved conflict without deciding which source is correct."""
    tail = f": {say}" if say else ""
    return (f"{NOTICE_MARK}[{fid}] conflicts with [{other_id}]. **This knowledge-base conflict "
            f"is unresolved; treat neither claim as established.**{tail}")


def _pairs(conflicts: list[dict]) -> dict[str, tuple[str, str]]:
    """Index each conflict from either participating fact identifier."""
    out: dict[str, tuple[str, str]] = {}
    for row in conflicts or []:
        new_id, old_id = row.get("new_fact_id") or "", row.get("old_fact_id") or ""
        say = row.get("say") or ""
        if new_id and old_id:
            out.setdefault(old_id, (new_id, say))
            out.setdefault(new_id, (old_id, say))
    return out


def apply(led: dict, facts: list[str], *, superseded: dict[str, str],
          conflicts: dict[str, tuple[str, str]],
          lookup) -> tuple[list[str], int]:
    """Add bounded correction notices using an injected fact lookup."""
    added: list[str] = []
    hits = 0
    for fid, row in list(led.get("facts", {}).items()):
        if len(added) >= MAX_ADDED:
            break
        new_id = superseded.get(fid)
        if new_id:
            if row.get("superseded_by") != new_id:
                row["superseded_by"] = new_id
            hits += 1
            fresh = lookup(new_id) or {}
            text = (fresh.get("text") or "").strip()
            if not text:


                line = (f"{NOTICE_MARK}[{fid}] has been superseded by [{new_id}], "
                        f"but that replacement cannot currently be retrieved. Do not treat this fact as established.")
            else:
                when = fresh.get("when") or fresh.get("date") or ""
                line = replacement_line(new_id, text, when, fid)
                if new_id not in led["facts"]:

                    led["facts"][new_id] = {"line": text[:LINE_CHARS],
                                            "state": "taken", "tool": "supersede",
                                            "when": when}
            if line not in facts and line not in added:
                added.append(line)
            continue
        pair = conflicts.get(fid)
        if pair:
            other, say = pair
            row["conflict_with"] = other
            line = conflict_line(fid, other, say)
            if line not in facts and line not in added:
                added.append(line)
    return added, hits


class Supersede:
    """Attach correction notices after evidence collection and ledger updates."""

    name = "supersede"
    hooks = ("after_prepare",)


    after: tuple[str, ...] = ("facts", "ledger")

    async def after_prepare(self, st: State) -> None:
        st.bag["superseded_round"] = 0
        led = ledger_of(st)
        if not led.get("facts") or not st.ctx.user:
            return
        try:
            from ...database import store
            from ...database.kite.kite_memory import UserMemory

            mem = UserMemory(st.ctx.user)
            attrs = mem.fact_attrs("superseded_by")
            open_rows = store.list_conflicts(st.ctx.user, status="open")
            added, hits = apply(
                led, st.facts,
                superseded={k: v for k, v in attrs.items() if k in led["facts"]},
                conflicts=_pairs(open_rows),
                lookup=mem.fact_by_id)
        except Exception:                                   # noqa: BLE001


            return
        st.bag["superseded_round"] = hits


        st.facts = st.facts + added
