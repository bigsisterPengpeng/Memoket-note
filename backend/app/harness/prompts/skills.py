"""Compose scoped writing skills and generate reusable skill instructions."""

from __future__ import annotations

# Scope IDs correspond to actual generation call sites.
SKILL_SCOPES = {
    "magic_tap": "Continue writing",
    "section_write": "Writing plan: write a section",
    "plan_generate": "Writing plan: generate sections",
    "more_sections": "Writing plan: find remaining sections",
    "verify": "Verify selection",
    "rewrite": "Rewrite selection",
    "polish": "Polish selection",
    "expand": "Expand selection context",
    "edit": "Revise the note",
    "skeleton": "Generate a skeleton",
    "digest": "Review a period",
    "block_write": "Slash command: charts, tables and data analysis",
    "block_prompt": "Slash command or context menu: custom prompt",
}


def compose_system(base: str, scope: str, user: str = "",
                   menu: list[tuple[str, str]] | None = None,
                   bodies: list[str] | None = None) -> str:
    """Append scoped/loaded skills and a menu without replacing the base rules.

    Run state includes dynamically loaded bodies. Recomputing scope matches here
    would discard them and cause repeated load_skill calls.
    """
    from .. import skills as skills_store

    if bodies is None or menu is None:
        injected, listed = skills_store.for_scope(user, scope)
        bodies = [s.body for s in injected] if bodies is None else bodies
        menu = [(s.name, s.description) for s in listed] if menu is None else menu

    parts = [base]
    if bodies:
        parts.append("Apply these additional writing skills in order, without violating the base rules above:")
        parts.extend(bodies)
    block = skills_store.menu_block(menu)
    if block:
        parts.append(block)
    return "\n\n".join(parts)


def skill_generate_system() -> str:
    """Read built-in SKILL.md examples rather than maintaining a second copy."""
    from .. import skills as skills_store

    scope_lines = "\n".join(f"- {k}: {v}" for k, v in SKILL_SCOPES.items())
    examples = []
    root = skills_store.BUILTIN_ROOT
    for directory in sorted(root.iterdir())[:3] if root.is_dir() else []:
        md = directory / "SKILL.md"
        if not md.is_file():
            continue
        try:
            _name, _desc, body = skills_store.parse_skill_md(md.read_text(encoding="utf-8"))
        except skills_store.SkillFormatError:
            continue
        examples.append(f"Example: {body}")
    return f"""Turn the user's description of a desired writing behavior into a concrete,
executable writing skill.

Available scopes:
{scope_lines}

Requirements:
- name: a concise skill name, roughly 8-16 characters or a similarly short phrase.
- description: one sentence explaining what it does and when to use it. The model
  uses this description to decide whether to load the skill.
- scopes: select the 1-3 scopes that best match the user's intent. Omit unrelated scopes.
- content: actionable instructions and decision criteria. Specify what to do or avoid,
  rather than generic requests to improve quality. Follow the examples' level of detail.
- Match the language requested by the user; otherwise write the skill in English.
Return only JSON:
{{"name":"...","description":"...","scopes":["..."],"content":"..."}}

Style examples:
{chr(10).join(examples)}
"""


def skill_generate_user(goal: str, scope_hint: str = "") -> str:
    parts = [f"[Desired writing behavior]\n{goal}"]
    if scope_hint:
        parts.append(f"[User-specified scope hint]\n{scope_hint}")
    parts.append("Generate this skill.")
    return "\n\n".join(parts)
