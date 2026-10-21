"""Build a request-specific acceptance checklist while retaining deterministic checks and fallback judge dimensions."""

from __future__ import annotations

import dataclasses

from .. import checklist as synth
from .. import params
from ..checks.instructions import Constraint, extract, instruction_constraints
from ..state import State


STEP = "checklist"


class Checklist:
    name = "checklist"
    hooks = ("before_run",)
    after: tuple[str, ...] = ()

    async def before_run(self, st: State) -> None:
        if not params.PROMPT_CHECKLIST:
            return
        instruction = (st.bag.get("prompt") or "").strip()
        if not instruction:


            return

        constraints = st.bag.get("prompt_constraints")
        if constraints is None:
            constraints = list(extract(instruction))
            st.bag["prompt_constraints"] = constraints
        constraints = tuple(c for c in constraints if isinstance(c, Constraint))

        items = st.bag.get("checklist")
        if items is None:
            items = list(await self._synthesize(st, instruction, constraints))
            st.bag["checklist"] = items


        items = tuple(x for x in items if isinstance(x, synth.Item))

        self._attach(st, items, constraints)

    # ------------------------------------------------------------------
    async def _synthesize(self, st: State, instruction: str,
                          constraints: tuple[Constraint, ...]) -> tuple[synth.Item, ...]:
        from .. import adapter
        try:
            with _step():
                return await synth.synthesize(
                    adapter.AppLLMClient(), instruction,
                    selection=(st.bag.get("selection") or ""),
                    constraints=constraints)
        except Exception:                                  # noqa: BLE001
            return ()

    def _attach(self, st: State, items: tuple[synth.Item, ...],
                constraints: tuple[Constraint, ...]) -> None:
        dims = st.mode.dims + synth.to_dimensions(items)
        checks = st.mode.checks
        if constraints and instruction_constraints not in checks:
            checks = checks + (instruction_constraints,)
        if dims != st.mode.dims or checks != st.mode.checks:
            st.mode = dataclasses.replace(st.mode, dims=dims, checks=checks)


class _step:
    def __enter__(self):
        from .. import loop
        self._cm = loop._step(STEP)
        return self._cm.__enter__()

    def __exit__(self, *exc):
        return self._cm.__exit__(*exc)
