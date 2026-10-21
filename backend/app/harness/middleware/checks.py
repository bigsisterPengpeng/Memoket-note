"""Run the Mode's deterministic checks, before paying for a scoring call.

Ordering matters here and it used to be backwards: scoring ran first, then
the checks, so whenever a check fired the scoring call had been wasted. A
scoring call is tens of seconds against a local model.

(PydanticAI does the same thing for the same reason: schema validation is
free and runs first, semantic validation costs I/O and runs second.)
"""

from __future__ import annotations

from typing import AsyncIterator

import dataclasses

from ..types import DimensionScore, Evaluation

from ..checks import claims
from ..events import CUSTOM_CHECK_HIT, Event
from ..state import State


STUCK_ROUNDS = 2


JUDGE_FLOOR = 2


#   |---|---|---|---|---|


JUDGE_FLOOR_AFTER_FIRST = 3


CHECK_WINDOW = 4


class Checks:
    """First failing check wins; the rest don't run.

    Why stop at the first: the model gets one clear instruction for the next
    round. Handing it five complaints at once produces a round that addresses
    none of them properly.
    """

    name = "checks"
    hooks = ("before_judge", "after_judge", "after_run")
    # Repeats fills dup_hints for the scoring call. Checks may
    # short-circuit scoring entirely, so it has to run second --
    # otherwise a fired check means dup_hints never gets computed,
    # and the next round wants it.
    after: tuple[str, ...] = ("repeats",)

    async def after_run(self, st: State) -> AsyncIterator[Event]:
        from ..modes import check_stuck_detail
        if st.stopped != "check_stuck":
            return
        name, n = check_stuck_detail(st)
        yield Event.custom(CUSTOM_CHECK_HIT, {
            "round": st.round,
            "check": name,
            "ran": 0,
            "dimension": "",
            "note": f'「{name}" fired in {CHECK_WINDOW} recent rounds, on {n} occasions without resolution. Stop and return the best round.',
            "stuck_rounds": n,
            "stopped": True,
        })

    @staticmethod
    def _fix_events(st: State, fired: str, ran: int, verdict) -> list[Event]:
        note = (verdict.fix_note or "").strip()
        if not note:
            return []
        st.bag.setdefault("auto_fixes", []).append(note)
        return [Event.custom(CUSTOM_CHECK_HIT, {
            "round": st.round,
            "check": fired,
            "ran": ran,
            "dimension": verdict.dimension,
            "note": note,


            "auto_fixed": True,
        })]

    async def after_judge(self, st: State) -> None:
        if not st.bag.pop("check_released", False):
            return
        if st.ev is not None and st.ev.status == "complete":
            st.ev = dataclasses.replace(st.ev, status="continue")

    async def before_judge(self, st: State) -> AsyncIterator[Event]:
        prev: dict[str, int] = st.bag.get("check_streak") or {}
        cur: dict[str, int] = {}
        st.bag["check_streak"] = cur


        prev_name: dict[str, int] = st.bag.get("check_name_streak") or {}
        cur_name: dict[str, int] = {}
        st.bag["check_name_streak"] = cur_name


        st.bag["check_name_streak_prev"] = prev_name


        window: list[dict[str, int]] = st.bag.get("check_name_rounds") or []
        window.append(cur_name)
        st.bag["check_name_rounds"] = window[-CHECK_WINDOW:]

        sc_streak = int(st.bag.get("short_circuit_streak", 0) or 0)


        floor = (JUDGE_FLOOR_AFTER_FIRST if st.bag.get("had_real_judge")
                 else JUDGE_FLOOR)


        st.bag.pop("check_released", None)


        st.bag["auto_fixes"] = []


        st.bag["advisories"] = []


        if claims.unsupported_specifics in st.mode.checks:
            cands, why = claims.probe(st)
            st.bag["claim_atoms"] = len(cands)
            st.bag["claim_abstained"] = why
        else:


            st.bag["claim_atoms"] = -1
            st.bag["claim_abstained"] = claims.NOT_IN_MODE


        from ..checks.citations import citation_coverage
        cov = citation_coverage(st.fresh or "", list(st.facts or []))
        st.bag["cite_cover"] = (cov.located, cov.marked, cov.matched)


        run = st.bag.setdefault("cite_cover_run", [0, 0, 0])
        run[0] += cov.located
        run[1] += cov.marked
        run[2] += cov.matched


        fired_all: list[str] = []
        st.bag["fired_checks"] = fired_all


        st.bag["short_circuit"] = ""

        for ran, check in enumerate(st.mode.checks, start=1):
            verdict = check(st)
            if not verdict:
                continue

            # `no_placeholder` / `citations_hold` / `citations_exist` /


            fired = getattr(check, "__name__", "") or str(check)

            if verdict.fix:
                # **Fixes are atomic**: apply to a copy, keep it only if the
                # check now passes. Without the copy, a fix that doesn't
                # actually fix anything still mutates the content -- and the
                # next round then builds on something that was edited and is
                # still wrong. (Found by running the prototype; three passes
                # of reading the design on paper had missed it.)
                probe = dataclasses.replace(st, content=verdict.fix(st.content))
                again = check(probe)
                if again is None:
                    st.content = probe.content


                    for ev in self._fix_events(st, fired, ran, verdict):
                        yield ev
                    continue


                if verdict.fix_done is not None and verdict.fix_done(probe.content):
                    st.content = probe.content


                    for ev in self._fix_events(st, fired, ran, verdict):
                        yield ev
                    verdict = again


            fired_all.append(fired)

            if verdict.advisory:


                st.bag["check_released"] = True
                st.bag.setdefault("advisories", []).append(verdict.message)
                yield Event.custom(CUSTOM_CHECK_HIT, {
                    "round": st.round,
                    "check": fired,
                    "ran": ran,
                    "dimension": verdict.dimension,
                    "note": verdict.message,
                    "advisory": True,
                })
                continue

            cur_name[fired] = prev_name.get(fired, 0) + 1
            key = f"{verdict.dimension}\u0000{verdict.message}"
            streak = cur[key] = prev.get(key, 0) + 1
            if streak > STUCK_ROUNDS:


                yield Event.custom(CUSTOM_CHECK_HIT, {
                    "round": st.round,
                    "check": fired,
                    "ran": ran,
                    "dimension": verdict.dimension,
                    "note": verdict.message,
                    "stuck_rounds": streak,
                })
                continue

            if sc_streak >= floor:


                st.bag["check_released"] = True
                yield Event.custom(CUSTOM_CHECK_HIT, {
                    "round": st.round,
                    "check": fired,
                    "ran": ran,
                    "dimension": verdict.dimension,
                    "note": verdict.message,
                    "judge_floor": sc_streak,


                    "judge_floor_bar": floor,
                })
                continue

            st.ev = Evaluation(
                scores={verdict.dimension: DimensionScore(level=0, note=verdict.message)},
                status="continue",
                weakest=verdict.dimension,
            )
            st.skip_judge = True        # explicit, not "ev happens to be set"
            st.bag["short_circuit"] = fired
            st.bag["short_circuit_streak"] = sc_streak + 1
            yield Event.custom(CUSTOM_CHECK_HIT, {
                "round": st.round,
                "check": fired,
                "ran": ran,
                "dimension": verdict.dimension,
                "note": verdict.message,
            })
            return


        st.bag["short_circuit_streak"] = 0
        st.bag["had_real_judge"] = True
