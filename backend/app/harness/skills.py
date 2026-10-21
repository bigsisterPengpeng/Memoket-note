"""Skills: standard SKILL.md directories on disk, our config in the database.

The format is Agent Skills' ``SKILL.md`` and we follow it exactly -- no extra
frontmatter keys. The spec allows two required fields and nothing else:

    name         <=64 chars, lowercase letters / digits / hyphens only
    description  non-empty, <=1024 chars, must say both what it does and
                 when to use it (this is what the model matches against)

Our own settings -- which scopes a skill applies to, whether it's enabled,
what sandbox level the user granted -- deliberately do **not** live in that
file. Two reasons:

1. The spec has no extension mechanism. Inventing keys makes a dialect, and
   then third-party skills don't drop in and ours don't travel.
2. They aren't properties of the skill anyway. Which scopes it applies to is
   how *we* use it -- one user may want it for drafting, another for
   polishing. Sandbox permission is something the user *grants*; an app
   doesn't get to declare it has camera access.

So: content on disk, untouched; configuration in ``skill_config``.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..util.config import get_settings

NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
MAX_DESCRIPTION = 1024

# Level 2 of progressive disclosure has a budget; a skill body that blows
# past it defeats the point of loading on demand.
MAX_BODY_CHARS = 20_000

# How many skills the model may pull in during one run. Without a ceiling it
# will happily load five and fill the window. Same reasoning as the chart
# tools refusing to draw uninformative charts: a tool that says no is more
# reliable than an instruction to show restraint.
MAX_LOADED_SKILLS = 3

# Which built-in applies where. **Deliberately not in SKILL.md**: a skill
# does not get to declare when our system uses it, any more than an app
# declares its own permissions. Same user, same skill, different opinion
# about when it should fire -- that is configuration, and configuration
# lives in the database (see harness-framework 10.1.2).
BUILTIN_SCOPES: dict[str, list[str]] = {
    "doc-coauthoring-sections": ['plan_generate'],
    "discernment-nudge-verify-triage": ['verify'],
    "brainstorming-confirm-scope": ['plan_generate'],
    "structured-reasoning-evidence-tiers": ['verify'],
    "source-check-top-edit-rewrite": ['rewrite', 'polish'],
    "llm-writing-avoid-defaults": ["magic_tap", "block_prompt"],
    "story-memory-term-consistency": ['section_write'],
    "discernment-nudge-more-sections-restraint": ['more_sections'],
    "story-planning-expand-consistency": ['expand'],
    "source-check-edit-evidence": ['edit'],
    "top-edit-structural-patterns": ['edit'],
    "doc-coauthoring-anticipate-questions": ['skeleton'],
    "highlight-deltas-digest": ['digest']
}


@dataclass(frozen=True)
class Skill:
    """A parsed SKILL.md plus the config we keep alongside it."""

    slug: str                       # directory name == frontmatter ``name``
    name: str
    description: str
    body: str
    path: Path
    # -- our config, from the database, not from the file --
    enabled: bool = True
    scopes: tuple[str, ...] = ()
    sandbox: str = "none"           # none | compute | files
    source: str = "user"            # builtin | user | imported
    idx: int = 0                    # stacking order in the prompt

    @property
    def title(self) -> str:
        """What a person calls it.

        ``name`` is an identifier -- lowercase, hyphens, so the directory
        copies straight into Claude Code. The readable name is the body's
        first heading, which is where the spec leaves room for it.
        """
        for line in self.body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return self.name


class SkillFormatError(ValueError):
    """SKILL.md violates the spec. Raised at import time, never at run time --
    a malformed skill must be rejected when the user adds it, not silently
    skipped later when they wonder why it never fires."""


def parse_skill_md(text: str) -> tuple[str, str, str]:
    """Split a SKILL.md into (name, description, body). Validates the spec.

    Only ``name`` and ``description`` are read. Any other frontmatter key is
    ignored rather than rejected -- a third-party skill carrying keys some
    other tool understands is still perfectly usable here.
    """
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text.strip(), re.S)
    if not match:
        raise SkillFormatError("SKILL.md must start with YAML frontmatter")
    front, body = match.group(1), match.group(2).strip()

    fields = _parse_frontmatter(front)
    name = fields.get("name", "").strip()
    description = fields.get("description", "").strip()

    if not NAME_RE.match(name):
        raise SkillFormatError(
            f"name {name!r} is invalid: at most 64 characters, lowercase "
            f"letters, digits and hyphens only")
    if "anthropic" in name or "claude" in name:
        raise SkillFormatError(f"name {name!r} may not contain reserved words")
    if not description:
        raise SkillFormatError("description is required")
    if len(description) > MAX_DESCRIPTION:
        raise SkillFormatError(
            f"description is {len(description)} characters, limit is {MAX_DESCRIPTION}")
    if "<" in name or "<" in description:
        raise SkillFormatError("name and description may not contain XML tags")

    return name, description, body


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal YAML: ``key: value`` plus folded/literal block scalars.

    Not a real YAML parser and doesn't need to be -- we read exactly two
    string fields. Block scalars *are* handled because real SKILL.md files
    routinely write ``description: >`` with the text on following lines, and
    a parser that misses that returns a lone ``>``, which is worse than
    returning nothing.
    """
    fields: dict[str, str] = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if re.fullmatch(r"[|>][+-]?", rest):
            folded = rest[0] == ">"
            parts: list[str] = []
            i += 1
            while i < len(lines) and (not lines[i].strip() or re.match(r"^\s+\S", lines[i])):
                parts.append(lines[i].strip())
                i += 1
            fields[key] = (" " if folded else "\n").join(p for p in parts if p)
            continue
        fields[key] = rest.strip("'\"")
        i += 1
    return fields


def skills_root(user: str) -> Path:
    return Path(get_settings().kite_data_dir) / user / "skills"


def load_all(user: str) -> list[Skill]:
    """Every installed skill, with config merged in.

    A directory that fails to parse is skipped rather than raised -- one bad
    skill must not stop the other twelve from working. Import-time validation
    is where malformed input gets rejected loudly.
    """
    from ..database import store

    root = skills_root(user)
    if not root.is_dir():


        seed(user)
        if not root.is_dir():
            return []
    config = store.skill_configs(user)
    out: list[Skill] = []
    for directory in sorted(root.iterdir()):
        md = directory / "SKILL.md"
        if not directory.is_dir() or not md.is_file():
            continue
        try:
            name, description, body = parse_skill_md(md.read_text(encoding="utf-8"))
        except (SkillFormatError, OSError, UnicodeDecodeError):
            continue
        cfg = config.get(directory.name, {})
        out.append(Skill(
            slug=directory.name, name=name, description=description,
            body=body[:MAX_BODY_CHARS], path=directory,
            enabled=bool(cfg.get("enabled", True)),
            scopes=tuple(cfg.get("scopes") or ()),
            sandbox=str(cfg.get("sandbox") or "none"),
            source=str(cfg.get("source") or "user"),
            idx=int(cfg.get("idx") or 0),
        ))
    # Stacking order is user configuration: two skills that disagree are
    # resolved by whichever the model reads last. Directory name is only the
    # tie-break.
    out.sort(key=lambda s: (s.idx, s.slug))
    return out


def for_scope(user: str, scope: str) -> tuple[list[Skill], list[Skill]]:
    """Split enabled skills into (inject directly, list in the menu).

    Reading of the rule: **having scopes configured means the user has said
    "I know when this applies"**. Those get injected when they match and
    stay out of the way when they don't. Skills with no scopes -- which is
    what a freshly installed third-party skill looks like -- go in the menu
    and the model decides.

    The two lists are disjoint on purpose: a skill already in the prompt must
    not also be offered for loading, or the model burns a tool call fetching
    what it has.
    """
    enabled = [s for s in load_all(user) if s.enabled]
    injected = [s for s in enabled if s.scopes and scope and scope in s.scopes]
    listed = [s for s in enabled if not s.scopes]
    return injected, listed


def read_body(user: str, slug: str) -> str | None:
    for skill in load_all(user):
        if skill.slug == slug or skill.name == slug:
            return skill.body
    return None


def read_reference(user: str, slug: str, relative: str) -> str | None:
    """Read one bundled file (level 3 of progressive disclosure).

    Path traversal is rejected: the model chooses this argument, and a skill
    body is untrusted text that could ask for ``../../../etc/passwd``.
    """
    root = skills_root(user) / slug
    try:
        target = (root / relative).resolve()
        target.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    if not target.is_file() or target.suffix.lower() not in {".md", ".txt", ".json", ".csv"}:
        return None
    try:
        return target.read_text(encoding="utf-8")[:MAX_BODY_CHARS]
    except (OSError, UnicodeDecodeError):
        return None


# --------------------------------------------------------------- install ---


# app/harness/skills.py → app/harness → app → backend
BUILTIN_ROOT = Path(__file__).resolve().parents[2] / "skills"


_PRE_SHA_LEDGER: dict[str, str] = {
    "brainstorming-confirm-scope": "7ef79abdfb5f62db",
    "discernment-nudge-more-sections-restraint": "813bcbd419a5d74c",
    "discernment-nudge-verify-triage": "d56029c843e38cad",
    "doc-coauthoring-anticipate-questions": "ccb25775afe001cd",
    "doc-coauthoring-sections": "174314833a7fd049",
    "llm-writing-avoid-defaults": "033d49aaa8dfa007",
    "source-check-edit-evidence": "3aac0abf6f821ec8",
    "source-check-top-edit-rewrite": "4ed3915164ff217a",
    "story-memory-term-consistency": "e253784e01bc79d3",
    "story-planning-expand-consistency": "32f0e500f2df2929",
    "top-edit-structural-patterns": "f59b9ba4dd10de1f",
}


def seed(user: str) -> int:
    from ..database import store

    root = skills_root(user)
    root.mkdir(parents=True, exist_ok=True)
    configs = store.skill_configs(user)
    added = 0
    for source in sorted(BUILTIN_ROOT.iterdir()) if BUILTIN_ROOT.is_dir() else []:
        md = source / "SKILL.md"
        if not source.is_dir() or not md.is_file():
            continue
        shipped = md.read_text(encoding="utf-8")
        sha = store.content_sha(shipped)
        target = root / source.name
        if target.exists():
            here = target / "SKILL.md"
            if not here.is_file():
                continue
            seeded = (configs.get(source.name) or {}).get("seeded_sha") or ""
            here_sha = store.content_sha(here.read_text(encoding="utf-8"))
            if not seeded:


                if here_sha == sha:
                    store.set_skill_config(user, source.name, seeded_sha=sha)
                elif here_sha == _PRE_SHA_LEDGER.get(source.name):
                    here.write_text(shipped, encoding="utf-8")
                    store.set_skill_config(user, source.name, seeded_sha=sha)
                continue
            if here_sha == seeded and seeded != sha:
                here.write_text(shipped, encoding="utf-8")
                store.set_skill_config(user, source.name, seeded_sha=sha)
            continue
        shutil.copytree(source, target)
        store.set_skill_config(user, source.name, enabled=True,
                               scopes=BUILTIN_SCOPES.get(source.name, []),
                               sandbox="none", source="builtin", seeded_sha=sha)
        added += 1
    return added


def install(user: str, directory_name: str, files: dict[str, str], *,
            source: str = "user", scopes: list[str] | None = None,
            enabled: bool | None = None) -> Skill:
    """Write one skill directory. ``files`` maps relative path -> text.

    ``enabled`` defaults to False for imported skills and True otherwise:
    **installing is not enabling**. Someone else's instructions go into the
    model's context, so there is a user confirmation between arriving and
    taking effect -- the official guidance is the same ("use Skills only from
    trusted sources", "audit thoroughly").
    """
    from ..database import store

    if "SKILL.md" not in files:
        raise SkillFormatError("a skill directory must contain SKILL.md")
    name, _description, _body = parse_skill_md(files["SKILL.md"])
    slug = directory_name.strip() or name
    if not NAME_RE.match(slug):
        raise SkillFormatError(
            f"directory name {slug!r} must be lowercase letters, digits and hyphens")

    target = skills_root(user) / slug
    target.mkdir(parents=True, exist_ok=True)
    for relative, text in files.items():
        path = (target / relative).resolve()
        try:
            path.relative_to(target.resolve())
        except ValueError:
            # An archive entry named ../../something. Rejected rather than
            # sanitised: a skill that needs to write outside its own
            # directory is not a skill this product can install.
            raise SkillFormatError(f"{relative!r} escapes the skill directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    store.set_skill_config(
        user, slug,
        enabled=(source != "imported") if enabled is None else enabled,
        scopes=scopes or [], sandbox="none", source=source)
    found = [s for s in load_all(user) if s.slug == slug]
    if not found:
        raise SkillFormatError("the skill was written but could not be read back")
    return found[0]


def uninstall(user: str, slug: str) -> bool:
    from ..database import store

    target = skills_root(user) / slug
    if not target.is_dir():
        return False
    shutil.rmtree(target)
    store.delete_skill_config(user, slug)
    return True


def menu_block(menu: list[tuple[str, str]]) -> str:
    """The always-resident skill list -- level 1 of progressive disclosure.

    Roughly 100 tokens per skill, which is why only name and description are
    here and the body waits for ``load_skill``. With 13 built-ins that all
    have scopes configured this block is usually empty, and costs nothing.
    """
    if not menu:
        return ""
    lines = "\n".join(f"- {name}: {description}" for name, description in menu)
    return ("[Available skills: call load_skill to read the full instructions when relevant]\n"
            + lines)


def slugify(text: str) -> str:
    """A spec-legal identifier from whatever the user typed.

    The name a person writes is usually Chinese, and the spec allows only
    lowercase letters, digits and hyphens. When nothing survives -- a purely
    Chinese name, which is the normal case here -- fall back to a stable hash
    so the directory still has a legal name and the readable name lives in
    the body's heading, where the spec leaves room for it.
    """
    import hashlib

    cleaned = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    if cleaned:
        return cleaned[:64]
    digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:10]
    return f"skill-{digest}"


def render_skill_md(slug: str, description: str, title: str, body: str) -> str:
    """Write a SKILL.md the spec accepts.

    The readable title goes in the body's first heading rather than the
    frontmatter, because ``name`` is an identifier. A skill written in this
    product's panel is therefore a file that Claude Code can also read.
    """
    description = " ".join((description or title or slug).split())[:MAX_DESCRIPTION]
    heading = (title or slug).strip()
    text = body.strip()
    if not text.startswith("# "):
        text = f"# {heading}\n\n{text}"
    return f"---\nname: {slug}\ndescription: {description}\n---\n\n{text}\n"
