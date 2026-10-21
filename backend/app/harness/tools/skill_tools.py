"""Skill tools: how the model reaches level 2 and 3 of progressive disclosure.

The system prompt carries every skill's name and description (~100 tokens
each). When the model judges one relevant it calls ``load_skill``; if that
body points at a bundled file it calls ``read_skill_ref``. Nothing else is in
context until it asks.

Putting these behind tools rather than a bespoke code path is deliberate:
they then inherit authorisation (``group="skill"``), provenance (results land
in ToolTrace, so TapProvenance can show what was consulted), per-round call
caps, and error isolation -- all of it for free.
"""

from __future__ import annotations

from .. import skills
from .registry import ToolContext, register


@register(
    name="load_skill",
    group="skill",
    description="Load a skill's full instructions. The system prompt lists "
                "which skills exist and when each applies; call this when one "
                "of them fits what you're doing now.",
    params={"name": {"type": "string", "description": "the skill's name, as listed"}},
    required=["name"],
    max_calls_per_round=3,
)
def load_skill(ctx: ToolContext, name: str) -> str:
    """Pull one skill's body into context, and keep it for later rounds.

    Kept across rounds because a run can go eight rounds; re-loading the same
    skill each time would be eight wasted calls for one piece of unchanging
    text.
    """
    # The harness puts its own ``skill_bodies`` list in here, so appending
    # writes through to the run's state; a caller that doesn't provide one
    # simply gets no accumulation, and the tool still works.
    loaded = ctx.scratch.get("skill_bodies")


    by_model = ctx.scratch.setdefault("loaded_by_model", [])

    if len(by_model) >= skills.MAX_LOADED_SKILLS:
        # A ceiling, because the model will otherwise load five and fill the
        # window. Same principle as the chart tools refusing uninformative
        # charts: a tool that says no beats an instruction to show restraint.
        return (f"(Already loaded {skills.MAX_LOADED_SKILLS} skills, which is "
                f"enough for one piece of work. If a different one is needed, "
                f"say which and why.)")

    body = skills.read_body(ctx.user, name.strip())
    if body is None:
        available = ", ".join(s.name for s in skills.load_all(ctx.user) if s.enabled)
        return f"(No skill named {name!r}. Available: {available or 'none'})"

    if name.strip() not in by_model:
        by_model.append(name.strip())
    if loaded is not None and body not in loaded:
        loaded.append(body)
    return body


@register(
    name="read_skill_ref",
    group="skill",
    description="Read a reference file bundled with a skill (a template, a "
                "worked example, a checklist). Only call this when a skill's "
                "instructions point at a specific file.",
    params={
        "skill": {"type": "string", "description": "which skill the file belongs to"},
        "path": {"type": "string", "description": "the file name as written in the "
                                                  "skill's instructions"},
    },
    required=["skill", "path"],
    max_calls_per_round=3,
)
def read_skill_ref(ctx: ToolContext, skill: str, path: str) -> str:
    """Read one bundled file. Level 3 -- costs nothing until asked for.

    ``skills.read_reference`` rejects traversal and non-text files. That
    matters here because the argument comes from the model, which took it
    from a skill body -- untrusted text that may well have been written by
    someone else.
    """
    text = skills.read_reference(ctx.user, skill.strip(), path.strip())
    if text is None:
        return (f"(Can't read {path!r} from skill {skill!r}. It must be a text "
                f"file inside that skill's own directory.)")
    return text
