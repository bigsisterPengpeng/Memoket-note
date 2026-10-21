"""Collect supported entity candidates without promoting ungrounded speaker labels."""

from __future__ import annotations

import warnings

import memoket_kite
import memoket_kite.pipeline.extract as _extract

_VERIFIED_AGAINST = "0.1.0"

_MIN_SURFACE_LEN_FOR_OVERLAP = 3


def _bigrams(s: str) -> set[str]:
    s = s.lower()
    if len(s) < 2:
        return set()
    return {s[i : i + 2] for i in range(len(s) - 1)}


def _coarse_entity_candidates(vocabulary, text: str, cap: int = 80) -> list[str]:
    """Rank vocabulary.entities by relevance to `text`, return up to `cap`
    codes: an exact substring hit ranks first, then descending character-
    bigram overlap. Approximate on purpose -- see module docstring."""
    if not vocabulary.entities:
        return []
    text_lower = text.lower()
    text_bigrams = _bigrams(text)
    scored: list[tuple[float, str]] = []
    for code, entity in vocabulary.entities.items():
        best = 0.0
        for surface in (code, entity.name, *entity.aliases):
            surface = str(surface or "").strip()
            if len(surface) < _MIN_SURFACE_LEN_FOR_OVERLAP:
                # A 1-2 char surface (junk codes like "a", "m" that leaked
                # into the vocab from earlier bad extractions) matches almost
                # any text as an exact substring, drowning out real
                # candidates -- same length floor applies to both branches.
                continue
            if surface.lower() in text_lower:
                best = 1.0
                break
            sb = _bigrams(surface)
            if not sb:
                continue
            overlap = len(sb & text_bigrams) / len(sb)
            if overlap > best:
                best = overlap
        if best > 0:
            scored.append((best, code))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [code for _, code in scored[:cap]]


def _extract_facts_with_cache(vocabulary, profile, session, model, cache_dir, log, include_facets):
    """Verbatim copy of memoket_kite.pipeline.extract._extract_facts_with_cache
    (memoket_kite==0.1.0) except the entities= line. Delegates every helper
    call to the real module so caching/fingerprinting/logging stay identical
    to upstream -- only the KNOWN ENTITIES hint computation changes."""
    template = (
        profile.EXTRACT_PROMPT
        if include_facets
        else getattr(profile, "EXTRACT_PROMPT_NO_FACETS", profile.EXTRACT_PROMPT)
    )
    utterance_groups = session.get("utterance_groups") or [session["utterances"]]
    prompts = []
    for utterance_group in utterance_groups:
        conversation_text = "\n".join(
            f"{utterance_id}|{speaker}|{time_mark}|{content}"
            for utterance_id, speaker, time_mark, content in utterance_group
        )
        candidates = _coarse_entity_candidates(vocabulary, conversation_text, cap=80)
        prompts.append(
            template.format(
                tree=vocabulary.render_tree(max_lines=150),
                entities=", ".join(candidates) or "(none)",
                kinds="|".join(profile.KINDS),
                events="|".join(getattr(profile, "EVENTS", ()) or ()) or "(none; use [])",
                date=session["date"],
                weekday=session.get("weekday", "?"),
                time=session.get("time", "?"),
                title=session.get("title", ""),
                speakers=", ".join(session.get("speakers", [])),
                dialog=conversation_text,
            )
        )
    cache_path = None
    if cache_dir:
        import os

        os.makedirs(cache_dir, exist_ok=True)
        supports_facet_ablation = hasattr(profile, "EXTRACT_PROMPT_NO_FACETS")
        variant = (".facets" if include_facets else ".no-facets") if supports_facet_ablation else ""
        fingerprint = _extract.hashlib.sha256(
            "\x1f".join((model, _extract._provider_cache_identity(), *prompts)).encode("utf-8")
        ).hexdigest()[:12]
        cache_path = os.path.join(cache_dir, f"{session['id']}{variant}.{fingerprint}.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as stream:
                    cached = _extract.json.load(stream)
            except (OSError, _extract.json.JSONDecodeError):
                cached = None
            if (
                isinstance(cached, dict)
                and isinstance(cached.get("facts"), list)
                and isinstance(cached.get("proposals"), list)
                and isinstance(cached.get("entity_types"), dict)
            ):
                return cached
    extraction_response = {"facts": [], "proposals": [], "entity_types": {}}
    for prompt in prompts:
        response = _extract.llm_json(prompt, model=model)
        extraction_response["facts"].extend(_extract._model_array(response.get("facts")))
        extraction_response["proposals"].extend(_extract._model_array(response.get("proposals")))
        raw_types = response.get("entity_types")
        if isinstance(raw_types, dict):
            extraction_response["entity_types"].update(raw_types)
    log(
        f"  extract {session['id']} ({session['date']}): "
        f"{sum(len(group) for group in utterance_groups)} utterances -> "
        f"{len(extraction_response['facts'])} facts, "
        f"{len(extraction_response['proposals'])} topic proposals"
    )
    if cache_path:
        import os
        import tempfile

        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".extract-", suffix=".tmp", dir=os.path.dirname(cache_path), text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                _extract.json.dump(extraction_response, stream, ensure_ascii=False)
            os.replace(temporary_path, cache_path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
    return extraction_response


def install() -> None:
    """Point extract_facts() at the session-relevant candidate hint instead
    of the alphabetical-80 slice. Idempotent."""
    installed_version = getattr(memoket_kite, "__version__", None)
    if installed_version != _VERIFIED_AGAINST:
        warnings.warn(
            f"kite_entity_candidates: installed memoket_kite=={installed_version} "
            f"has not been re-diffed against this patch (verified against "
            f"{_VERIFIED_AGAINST}); _extract_facts_with_cache may have changed "
            "shape upstream. Not installing the patch -- KNOWN ENTITIES falls "
            "back to KITE's own alphabetical-80 slice until this is re-checked.",
            stacklevel=2,
        )
        return
    _extract._extract_facts_with_cache = _extract_facts_with_cache
