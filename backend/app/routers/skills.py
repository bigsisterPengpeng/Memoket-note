"""Skills: install, configure, remove.

**A skill is a directory, not a database row.** ``data/<user>/skills/<slug>/``
holds a standard ``SKILL.md`` plus whatever it bundles, exactly as the Agent
Skills format defines it -- so a skill downloaded from anywhere installs by
being copied in, and one written here can be copied out. That is the whole
reason for using the standard format rather than a schema of our own.

What is *not* in the file is our configuration: which scopes it applies to,
whether it is enabled, what sandbox level its scripts may have. Those are not
properties of the skill (a skill declaring its own permissions makes as much
sense as an app declaring it has the camera) -- they are the user's decisions,
and they live in ``skill_config``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..harness import prompts
from ..database import store
from ..harness import skills as skills_store
from ..util import llm
from .schemas import Skill, SkillGenerateIn, SkillIn, SkillReorderIn, SkillScope
from .deps import current_user

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _out(skill: skills_store.Skill) -> dict:
    return {
        "id": skill.slug, "name": skill.title, "slug": skill.slug,
        "description": skill.description, "scopes": list(skill.scopes),
        "content": skill.body, "enabled": skill.enabled, "idx": skill.idx,
        "builtin": skill.source == "builtin", "source": skill.source,
        "sandbox": skill.sandbox,
    }


def _find(user: str, slug: str) -> skills_store.Skill:
    for skill in skills_store.load_all(user):
        if skill.slug == slug:
            return skill
    raise HTTPException(404, "skill not found")


@router.get("/scopes", response_model=list[SkillScope])
def list_scopes():
    return [{"value": k, "label": v} for k, v in prompts.SKILL_SCOPES.items()]


@router.get("", response_model=list[Skill])
def list_skills(user: str = Depends(current_user)):
    # Seeding here rather than at startup: a user who has never opened the
    # panel has no directory yet, and this is the first place that matters.
    skills_store.seed(user)
    return [_out(s) for s in skills_store.load_all(user)]


@router.post("/generate", response_model=SkillIn)
async def generate_skill(body: SkillGenerateIn, user: str = Depends(current_user)):
    """Draft a skill from a sentence. **Returns a draft, saves nothing.**

    The user reads it, edits it, picks the scopes, then POSTs it -- the same
    preview-before-save path a third-party import takes, for the same reason:
    text nobody has read should not reach the model's context.
    """
    goal = body.goal.strip()
    if not goal:
        raise HTTPException(400, "goal required")
    parsed = await llm.complete_json(
        [{"role": "system", "content": prompts.skill_generate_system()},
         {"role": "user", "content": prompts.skill_generate_user(goal, body.scope_hint)}],
        max_tokens=500, temperature=0.5)
    if not isinstance(parsed, dict):
        raise HTTPException(502, 'The model did not return valid skill content. Try another description.')
    content = str(parsed.get("content") or "").strip()
    if not content:
        raise HTTPException(502, 'The model did not return valid skill content. Try another description.')
    return SkillIn(
        name=str(parsed.get("name") or "").strip() or 'Untitled skill',
        slug=skills_store.slugify(str(parsed.get("slug") or parsed.get("name") or "")),
        description=str(parsed.get("description") or "").strip(),
        scopes=[s for s in (parsed.get("scopes") or []) if s in prompts.SKILL_SCOPES],
        content=content,
        enabled=True,
    )


MAX_CONTENT_CHARS = 20000


def _validate(body: SkillIn) -> None:
    if not body.name.strip():
        raise HTTPException(400, 'A skill name is required')
    if not body.content.strip():
        raise HTTPException(400, "skill content required")
    if len(body.content) > MAX_CONTENT_CHARS:
        raise HTTPException(400, f'Skill content must not exceed {MAX_CONTENT_CHARS} characters. Split longer skills into smaller ones.')
    bad = [s for s in body.scopes if s not in prompts.SKILL_SCOPES]
    if bad:
        raise HTTPException(400, f"Unknown scopes: {'、'.join(bad)} (available: {'、'.join(prompts.SKILL_SCOPES)}）")


@router.post("", response_model=Skill)
def create_skill(body: SkillIn, user: str = Depends(current_user)):
    _validate(body)
    slug = skills_store.slugify(body.slug or body.name)
    if not slug:
        raise HTTPException(400, "skill name must yield a usable identifier")
    try:
        skill = skills_store.install(
            user, slug, {"SKILL.md": skills_store.render_skill_md(
                slug, body.description, body.name, body.content)},
            source="user", scopes=body.scopes, enabled=body.enabled)
    except skills_store.SkillFormatError as exc:
        raise HTTPException(400, str(exc))
    return _out(skill)


@router.put("/{slug}", response_model=Skill)
def update_skill(slug: str, body: SkillIn, user: str = Depends(current_user)):
    _validate(body)
    existing = _find(user, slug)
    try:
        skill = skills_store.install(
            user, slug, {"SKILL.md": skills_store.render_skill_md(
                slug, body.description, body.name, body.content)},
            source=existing.source, scopes=body.scopes, enabled=body.enabled)
    except skills_store.SkillFormatError as exc:
        raise HTTPException(400, str(exc))
    return _out(skill)


@router.post("/{slug}/toggle", response_model=Skill)
def toggle_skill(slug: str, user: str = Depends(current_user)):
    skill = _find(user, slug)
    store.set_skill_config(user, slug, enabled=not skill.enabled)
    return _out(_find(user, slug))


@router.delete("/{slug}")
def delete_skill(slug: str, user: str = Depends(current_user)):
    if not skills_store.uninstall(user, slug):
        raise HTTPException(404, "skill not found")
    return {"deleted": slug}


@router.post("/reorder")
def reorder_skills(body: SkillReorderIn, user: str = Depends(current_user)):
    """Stacking order. It is configuration, not presentation: two skills that
    disagree are resolved by whichever the model reads last."""
    for position, slug in enumerate(body.ordered_ids):
        store.set_skill_config(user, slug, idx=position)
    return {"ok": True}
