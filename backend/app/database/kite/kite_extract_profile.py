"""Generate bounded profile candidates from source-linked facts and explicit user preferences."""

from __future__ import annotations

import warnings

import memoket_kite.remember as _kite_remember
from memoket_kite.defaults import DefaultMemoryProfile
from memoket_kite.prompts.extract import (
    DEFAULT_EXTRACT_PROMPT,
    DEFAULT_EXTRACT_PROMPT_NO_FACETS,
)

_ORIGINAL_CAPTURE_RULE = (
    '- Capture durable information that may matter in a later conversation. Write\n'
    '  one self-contained claim per fact; do not infer information not stated.'
)

_STRONGER_CAPTURE_RULE = (
    '- Capture durable information that may matter in a later conversation. Write\n'
    '  one self-contained claim per fact; do not infer information not stated.\n'
    '- Write "content" in the SAME language as the utterance(s) it is drawn\n'
    '  from. Never translate. If the conversation mixes languages, each fact\n'
    '  follows the language of its own supporting text, not the session as a\n'
    '  whole.'
)

_ORIGINAL_TOPICS_RULE = (
    '- "topics": reuse the most specific known codes. If none fits, propose one\n'
    '  specific child under a known root. "entities": named people, places,\n'
    '  organizations, products, works, or other concrete named things.'
)

_STRONGER_TOPICS_RULE = (
    '- "topics": do not settle for a broad root when a more specific label\n'
    '  fits. A root code (e.g. "work") is a category, not a proper topic -- it\n'
    '  is only correct when the fact is genuinely too general to specialize.\n'
    '  If the fact concerns a specific recurring subject (a named activity, a\n'
    '  project, a hiring round, a medical condition, a course, a budget line),\n'
    '  propose ONE new specific child topic under the closest known root and\n'
    '  use that child code instead of the root. Example: a fact about job\n'
    '  candidates and a hiring budget should propose a child like "hiring"\n'
    '  under "work", giving topics ["hiring"], not just ["work"]. "entities":\n'
    '  named people, places, organizations, products, works, or other\n'
    '  concrete named things.'
)


_ORIGINAL_ENTITY_RULE = (
    '"entities":\n'
    '  named people, places, organizations, products, works, or other\n'
    '  concrete named things.'
)

_STRONGER_ENTITY_RULE = (
    '"entities":\n'
    '  named people, places, organizations, products, works, or other\n'
    '  concrete named things. The conversation is machine-transcribed speech,\n'
    '  so an unusual-looking name or term is sometimes an ASR mishearing\n'
    '  rather than a new entity. This only ever ADDS a substitution -- it\n'
    '  never removes an entity you would otherwise write. Every entity you\n'
    '  would otherwise write still belongs in the output. Check each one\n'
    '  against KNOWN ENTITIES: only if it is a close phonetic or spelling\n'
    '  match AND nothing in the surrounding text marks it as a genuinely\n'
    '  different thing, write the known entity code in its place. In every\n'
    '  other case -- including when you are unsure, or it has no close match\n'
    '  in KNOWN ENTITIES -- write it as-is; a term with no close match is not\n'
    '  a reason to drop it. This is a code-resolution decision, not a\n'
    '  transcription correction -- it does not change what was said, only\n'
    '  which existing entity a mention refers to.'
)


_ORIGINAL_CONF_RULE = (
    '- "t": event time as YYYY-MM-DD or YYYY-MM when stated or safely resolvable;\n'
    '  otherwise null. "conf": high, med, or low.'
)

_STRONGER_CONF_RULE = (
    '- "t": event time as YYYY-MM-DD or YYYY-MM when stated or safely resolvable;\n'
    '  otherwise null. "conf": high, med, or low -- your confidence that this\n'
    '  fact is correct. This conversation is machine-transcribed speech, so the\n'
    '  text itself can be wrong independent of how clear the fact reads. If the\n'
    '  fact depends on a name, term, or number that sounds like it could be a\n'
    '  mishearing or a garbled fragment of the audio, mark "conf" as "low" even\n'
    '  when everything else about the fact is clear -- do not raise "conf" just\n'
    '  because the sentence around it is well-formed. Do not try to guess or\n'
    '  substitute what the "correct" word should be; write it exactly as\n'
    '  transcribed and let "conf" carry the uncertainty instead.'
)


_PATCHES = (
    ("capture/language rule", _ORIGINAL_CAPTURE_RULE, _STRONGER_CAPTURE_RULE),
    ("topics rule", _ORIGINAL_TOPICS_RULE, _STRONGER_TOPICS_RULE),
    # must run after the topics patch: this rule's anchor is the "entities"
    # tail left behind by _STRONGER_TOPICS_RULE's substitution, not the
    # original stock wording.
    ("entity grounding rule", _ORIGINAL_ENTITY_RULE, _STRONGER_ENTITY_RULE),
    ("ASR confidence rule", _ORIGINAL_CONF_RULE, _STRONGER_CONF_RULE),
)


def _patch(prompt: str) -> str:
    for name, anchor, replacement in _PATCHES:
        if anchor not in prompt:
            # KITE's prompt wording moved upstream -- fall back to the stock
            # text for this rule instead of silently shipping a patch that no
            # longer applies.
            warnings.warn(
                f"kite_extract_profile: anchor text for the {name} not found "
                "in KITE's extraction prompt; that patch is a no-op until "
                "this is updated for the new wording.",
                stacklevel=2,
            )
            continue
        prompt = prompt.replace(anchor, replacement)
    return prompt


class _PatchedProfile(DefaultMemoryProfile):
    EXTRACT_PROMPT = _patch(DEFAULT_EXTRACT_PROMPT)
    EXTRACT_PROMPT_NO_FACETS = _patch(DEFAULT_EXTRACT_PROMPT_NO_FACETS)


def install() -> None:
    """Point Memory.remember()'s extraction at the strengthened profile.

    Idempotent -- safe to call more than once / from more than one import path.
    """
    _kite_remember.DEFAULT_MEMORY_PROFILE = _PatchedProfile
