"""Public prompt interface, organized internally by writing task.

Keep shared fragments independent of individual workflows. Re-exports preserve
the flat prompts.X interface used by routes, hooks and middleware.
"""

from .fragments import (
    FOCUS_LABELS,
    content_block,
    facts_block,
    facts_index_block,
    tray_block,
    heading_format_reminder,
    profile_block,
    spine_beats_block,
)
from .writing import (
    EDIT_SYSTEM,
    FINISH_THE_SENTENCE,
    MAGIC_TAP_SYSTEM,
    MAGIC_TAP_SYSTEM_LEAN,
    MAGIC_TAP_SYSTEM_LEAN_NOCHART,
    MAGIC_TAP_SYSTEM_NOCHART,
    SKELETON_SYSTEM,
    edit_user,
    join_round_text,
    magic_tap_user,
    skeleton_user,
)
from .slides import SLIDES_SYSTEM, SLIDES_TALK_EXTRA, slides_user
from .selection import (
    DIGEST_SYSTEM,
    EXPAND_SYSTEM,
    RELATIONS_SYSTEM,
    POLISH_SYSTEM,
    REWRITE_SYSTEM,
    VERIFY_SYSTEM,
    digest_user,
    expand_user,
    rewrite_user,
    verify_user,
    relations_user,
)
from .note import (
    REPLAN_SYSTEM,
    RETRIEVAL_PLAN_SYSTEM,
    folder_context_block,
    note_harness_continue_user,
    replan_user,
    retrieval_plan_user,
)
from .plan import (
    MORE_SECTIONS_SYSTEM,
    PLAN_SYSTEM,
    more_sections_user,
    plan_user,
    render_tracking_doc,
    section_write_user,
)
from .skills import (
    SKILL_SCOPES,
    compose_system,
    skill_generate_system,
    skill_generate_user,
)
from .block import (
    BLOCK_SYSTEM,
)

__all__ = [
    "content_block",
    "relations_user",
    "facts_block",
    "facts_index_block",
    "tray_block",
    "BLOCK_SYSTEM",
    "DIGEST_SYSTEM",
    "SLIDES_SYSTEM",
    "SLIDES_TALK_EXTRA",
    "slides_user",
    "EDIT_SYSTEM",
    "EXPAND_SYSTEM",
    "FINISH_THE_SENTENCE",
    "FOCUS_LABELS",
    "MAGIC_TAP_SYSTEM",
    "MAGIC_TAP_SYSTEM_LEAN",
    "MAGIC_TAP_SYSTEM_LEAN_NOCHART",
    "MAGIC_TAP_SYSTEM_NOCHART",
    "MORE_SECTIONS_SYSTEM",
    "PLAN_SYSTEM",
    "POLISH_SYSTEM",
    "RELATIONS_SYSTEM",
    "REPLAN_SYSTEM",
    "RETRIEVAL_PLAN_SYSTEM",
    "REWRITE_SYSTEM",
    "SKELETON_SYSTEM",
    "SKILL_SCOPES",
    "VERIFY_SYSTEM",
    "compose_system",
    "digest_user",
    "edit_user",
    "expand_user",
    "folder_context_block",
    "heading_format_reminder",
    "join_round_text",
    "magic_tap_user",
    "more_sections_user",
    "note_harness_continue_user",
    "plan_user",
    "profile_block",
    "render_tracking_doc",
    "replan_user",
    "retrieval_plan_user",
    "rewrite_user",
    "section_write_user",
    "skeleton_user",
    "skill_generate_system",
    "skill_generate_user",
    "spine_beats_block",
    "verify_user",
]
