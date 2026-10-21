"""When the user chose a template, attach the scenario dimension and the deterministic floor to this run."""

from __future__ import annotations

import dataclasses

from .. import workflows
from ..checks.workflow import workflow_quality
from ..state import State


class WorkflowCriteria:
    name = "workflow_criteria"
    hooks = ("before_run",)
    after: tuple[str, ...] = ()

    async def before_run(self, st: State) -> None:
        recipe = workflows.recipe_of(st.ctx.intent)
        dim = workflows.dimension(st.ctx.intent)
        if not dim:
            return
        if recipe and recipe.completion_policy == "open":
            st.bag["completion_policy"] = "open"
            st.bag["handoff_rounds"] = max(1, recipe.handoff_rounds)
        dims = st.mode.dims
        if all(existing.name != dim.name for existing in dims):
            dims = dims + (dim,)
        checks = st.mode.checks
        if workflow_quality not in checks:
            names = [getattr(check, "__name__", "") for check in checks]
            pos = names.index("material_used") + 1 if "material_used" in names else len(checks)
            checks = checks[:pos] + (workflow_quality,) + checks[pos:]
        st.mode = dataclasses.replace(st.mode, dims=dims, checks=checks)
