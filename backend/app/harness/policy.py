"""Adapt per-round retrieval and revision budgets from explicit quality feedback."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


TOOL_ITERS_MIN, TOOL_ITERS_MAX = 1, 4
REVISIONS_MIN, REVISIONS_MAX = 4, 10
TEMP_MIN, TEMP_MAX = 0.3, 0.8


MATERIAL_DIMS = ("factual_grounding", "material_use",
                 "beat_coverage", "section_coverage")


@dataclass
class RoundFeedback:
    """Quality and tool-use signals from the preceding round."""

    scores: dict[str, int] = field(default_factory=dict)


    notes: dict[str, str] = field(default_factory=dict)
    weakest: str = ""
    status: str = "continue"
    tool_calls: int = 0
    tool_facts: int = 0
    tools_used: tuple[str, ...] = ()
    tool_truncated: bool = False


    tool_stopped_barren: bool = False


    kb_empty: bool = False
    revisions_applied: int = 0
    stall_rounds: int = 0

    def level(self, dim: str) -> int:
        """Return a dimension score, treating an unscored dimension as passing."""
        return self.scores.get(dim, 2)


@dataclass
class RuntimePolicy:
    """Bounded run settings and instructions for the next round."""

    tool_iters: int = 2
    # **Extra** groups for this round, not the whole list. Which groups a
    # feature gets is Mode configuration; a runtime policy that replaced it
    # silently dropped every group the Mode declared -- measured: the skill
    # tools were registered, listed in the prompt, and never reachable,
    # because this defaulted to ["memory"] and won.
    extra_tool_groups: list[str] = field(default_factory=list)


    steer: str = ""
    continue_temperature: float = 0.7
    max_revisions: int = 6

    require_verification: bool = False

    stuck_dims: dict[str, int] = field(default_factory=dict)

    def snapshot(self) -> dict:
        """Return serializable policy state for progress events and recovery."""
        return {
            "tool_iters": self.tool_iters,
            "continue_temperature": round(self.continue_temperature, 2),
            "max_revisions": self.max_revisions,
            "require_verification": self.require_verification,
            "steer": self.steer[:300],
            "stuck": {k: v for k, v in self.stuck_dims.items() if v >= 2},
        }


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _track_stuck(policy: RuntimePolicy, fb: RoundFeedback) -> dict[str, int]:
    """Count consecutive non-passing rounds for each dimension."""
    out = dict(policy.stuck_dims)
    for dim, level in fb.scores.items():
        if level < 2:
            out[dim] = out.get(dim, 0) + 1
        else:
            out.pop(dim, None)
    return out


def adjust(policy: RuntimePolicy, fb: RoundFeedback) -> tuple[RuntimePolicy, list[str]]:
    """Tune bounded budgets and evidence retrieval instructions for the next round."""
    reasons: list[str] = []
    stuck = _track_stuck(policy, fb)
    tool_iters = policy.tool_iters
    revisions = policy.max_revisions
    temperature = policy.continue_temperature
    verify = False
    steer_parts: list[str] = []


    if fb.level("factual_grounding") < 2:
        tool_iters += 1
        verify = True
        note = fb.notes.get("factual_grounding", "").strip()
        steer_parts.append(
            "The previous evaluation identified factual-grounding issues"
            + (f": {note}" if note else "")
            + (" The knowledge base is empty and cannot provide evidence. "
               "**Only for sentences introduced in this run**, remove or generalize unsupported names, dates and numbers. "
               "Do not preserve invented details. Leave pre-run user paragraphs unchanged."
               if fb.kb_empty else
               " First verify these points. Use original source wording when evidence is found. "
               "When evidence is unavailable, generalize unsupported names, dates and numbers **only in sentences introduced in this run**. "
               "Do not preserve invented details. Missing retrieved evidence does not prove pre-run user details are invented; leave those paragraphs unchanged.")
        )
        reasons.append(f"factual_grounding={fb.level('factual_grounding')}; tool budget +1; require source verification")


    if (fb.level("factual_grounding") < 2 and fb.tools_used and not fb.kb_empty
            and set(fb.tools_used) <= {"search_memory"}):
        steer_parts.append(
            "The previous round used only keyword-based search_memory. Long mixed-language queries can "
            "retrieve irrelevant material. Use filter_facts to retrieve by topic this round "
            "(the topic list is provided). Use keyword search only as a supplement."
        )
        reasons.append("Only search_memory used and grounding failed; switch to filter_facts")


    if fb.level("material_use") < 2:
        note = fb.notes.get("material_use", "").strip()
        steer_parts.append(
            (note or "The previous round retrieved evidence but did not use it in the draft.")
            + " This round **must** use concrete retrieved evidence in the text: the user's projects, "
              "numbers and decisions. General knowledge alone does not fulfill the task. Prefer two grounded sentences "
              "over a screen of unsupported generalities.")
        reasons.append("material_use failed; incorporate retrieved evidence into the draft")


    if fb.tool_calls and fb.tool_facts == 0 and not fb.kb_empty:
        steer_parts.append(
            "Keyword search returned no facts in the previous round. Change the retrieval path: "
            "use list_topics to inspect the actual topics, then filter_facts to retrieve by topic. "
            "Do not keep rephrasing the same search_memory query."
        )
        reasons.append("Tool queries returned no facts; use list_topics then filter_facts")


    if fb.kb_empty:
        steer_parts.append(
            "The user's knowledge base contains no facts. Stop calling retrieval tools. "
            "**Mention missing evidence only once in the whole draft.** Do not repeat missing-material placeholders in every section. "
            "Focus on clarifying the judgments, structure and tradeoffs in the user's existing text."
        )
        reasons.append("Knowledge base empty; stop retrieval and mention missing evidence once")


    if fb.level("coherence") < 2:
        temperature = round(_clamp(temperature - 0.2, TEMP_MIN, TEMP_MAX), 2)
        revisions += 2
        reasons.append(f"coherence={fb.level('coherence')}; continuation temperature reduced to {temperature:.1f}; revision budget +2")

    if fb.level("non_repetition") == 0:
        revisions += 2
        reasons.append("non_repetition=0; revision budget +2")


    escalating = [d for d, n in stuck.items() if n >= 2]
    if escalating:
        dim = next((d for d in escalating if d in MATERIAL_DIMS), escalating[0])
        reasons.append(f"{dim} failed for {stuck[dim]} consecutive rounds; escalate guidance")


        if dim in MATERIAL_DIMS:
            steer_parts.append(
                f"The dimension {dim} has failed for {stuck[dim]} consecutive rounds. The previous approach did not work. "
                "Try a different approach instead of repeating the preceding action."
            )


    if (fb.level("factual_grounding") == 2 and fb.tool_stopped_barren
            and tool_iters == policy.tool_iters):
        tool_iters -= 1
        reasons.append("Grounding passes and two consecutive tool iterations returned no new facts; tool budget -1")

    new = RuntimePolicy(
        tool_iters=_clamp(tool_iters, TOOL_ITERS_MIN, TOOL_ITERS_MAX),
        extra_tool_groups=list(policy.extra_tool_groups),
        steer="\n".join(steer_parts),
        continue_temperature=_clamp(temperature, TEMP_MIN, TEMP_MAX),
        max_revisions=_clamp(revisions, REVISIONS_MIN, REVISIONS_MAX),
        require_verification=verify,
        stuck_dims=stuck,
    )
    return new, reasons


def from_history(runs: list, base: RuntimePolicy | None = None) -> tuple[RuntimePolicy, list[str]]:
    """Seed the next run from dimensions repeatedly missed in recent runs."""
    policy = base or RuntimePolicy()
    if not runs:
        return policy, []

    counts: dict[str, int] = {}
    for run in runs:
        for dim in (getattr(run, "weak_dimensions", None) or []):
            counts[dim] = counts.get(dim, 0) + 1


    threshold = max(2, (len(runs) + 1) // 2)
    chronic = sorted(d for d, n in counts.items() if n >= threshold)
    if not chronic:
        return policy, []

    reasons = [f"Repeated failures in {', '.join(chronic)} across {len(runs)} recent runs; apply the corresponding strategy from round one"]
    fb = RoundFeedback(scores={d: 1 for d in chronic},
                       notes={}, weakest=chronic[0])
    tuned, more = adjust(policy, fb)


    tuned = replace(tuned, stuck_dims={})
    return tuned, reasons + more
