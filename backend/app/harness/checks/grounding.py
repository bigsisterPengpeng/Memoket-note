"""Grounding checks: is the text actually standing on the material.

These three used to be **silent rewrites** -- ``scrub_meta_sentences`` simply
deleted the offending sentences and the user never knew. Two harnesses did
that, a third reported the problem back and let the model fix it. Same defect,
opposite handling, decided by which was written first.

They are checks now. The user sees why the round was rejected, and can
disagree; a deletion nobody was told about offers neither.
"""

from __future__ import annotations

from .citations import check_citations

from . import grounding_rules as grounding_check
from ..state import State
from ..types import Verdict
from .pick import pick_dimension


def _kb_empty(st: State) -> bool:
    try:
        from ..tools.memory_tools import kb_is_empty
        return kb_is_empty(st.ctx.user)
    except Exception:      # noqa: BLE001
        return False


def no_placeholder(st: State) -> Verdict | None:
    """Text that promises content instead of containing it.

    "(details to be added later)" in a finished draft is worse than a shorter
    draft: it reads as done and isn't.
    """
    lines = grounding_check.placeholder_lines(st.content)


    from .. import workflows
    if (recipe := workflows.recipe_of(getattr(st.ctx, "intent", ""))) and recipe.id == "meeting":
        lines = [line for line in lines if '\u5f85\u786e\u8ba4' not in line and "pending confirmation" not in line.casefold()]
    if not lines:
        return None


    if not st.facts and _kb_empty(st):
        return None
    return Verdict(
        pick_dimension(st, "factual_grounding", "no_fabrication", "data_grounding"),
        'Placeholders replace substantive content: '
        + "；".join(lines[:3])
        + '. Replace the placeholder with supported content or remove it.',
    )


def no_audit_voice(st: State) -> Verdict | None:
    """Prose about whether the evidence is sufficient, instead of prose about
    the subject.

    "It should be noted that the available records do not fully support..."
    is a sentence about the knowledge base, not about the user's project.
    """


    lines = grounding_check.audit_voice_lines(
        st.content, before=str(st.bag.get("content_at_start") or ""))
    if not lines:
        return None
    return Verdict(
        pick_dimension(st, "style_fit", "fits_context"),
        'These sentences discuss evidence sufficiency instead of the subject: '
        + "；".join(lines[:3])
        + '. Omit unsupported assertions instead of adding commentary about insufficient evidence.',
    )


def citations_hold(st: State) -> Verdict | None:
    """Every cited fact marker must correspond to material actually supplied.

    ``check_citations`` has existed, with tests, since the package was written
    -- and was never wired into anything. Wiring it is most of the value:
    citing a fact that wasn't in the input is a different and more serious
    failure than paraphrasing loosely, and until now nothing looked for it.
    """


    from .citations import note_citations_unsupported, note_link_ids
    fresh = st.fresh or ""
    if note_link_ids(fresh):
        bad = note_citations_unsupported(fresh, _note_body_reader(st))
        if bad:
            return Verdict(
                pick_dimension(st, "factual_grounding", "no_fabrication", "data_grounding"),
                _note_citation_message(bad),
            )
    claimed = st.bag.get("claimed_sources") or []
    if not claimed or not st.facts:
        return None
    results = check_citations(list(claimed), st.facts)
    missing = [c.claimed for c in results if not c.verified]
    if not missing:
        return None
    return Verdict(
        pick_dimension(st, "factual_grounding", "no_fabrication", "data_grounding"),
        f"Found {len(missing)} citations that do not match the supplied material ({'; '.join((m[:40] for m in missing[:2]))}). Cite only retrieved sources.",
    )


def _note_body_reader(st: State):
    bodies = st.bag.get("note_bodies")
    if isinstance(bodies, dict):
        return lambda nid: bodies.get(nid)
    user = getattr(st.ctx, "user", "") or ""

    def read(nid: str):
        try:
            from ...database import store
            note = store.get_note(user, nid) if user else None
        except Exception:      # noqa: BLE001
            return None
        return (note or {}).get("content") if note else None
    return read


def _note_citation_message(bad: list[dict]) -> str:
    missing = [b for b in bad if b["why"] == "missing"]
    weak = [b for b in bad if b["why"] != "missing"]
    parts = []
    if missing:
        parts.append('Links to nonexistent notes: ' + "、".join(f"[{b['title'] or b['id']}](note://{b['id']})" for b in missing[:2]))
    if weak:
        parts.append('These sentences link to notes that do not support the claim: '
                     + "；".join(f"「{b['sentence'][:40]}…」→ [{b['title'] or b['id']}](note://{b['id']})" for b in weak[:2]))
    return ('Found ' + str(len(bad)) + ' invalid note citations: ' + "。".join(parts)
            + '. A linked note must actually support the stated date, decision or number. Do not attach its link to invented conclusions or claims absent from that note.')


def citations_exist(st: State) -> Verdict | None:
    from ...database.kite.kite_memory import UserMemory
    from .citations import (cited_ids, dangling_citations, strip_citations,
                            truncated_citations)
    before = str(st.bag.get("content_at_start") or "")
    user = getattr(st.ctx, "user", "")
    mem = UserMemory(user) if user else None
    exists = (lambda fid: mem.fact_by_id(fid) is not None) if mem else (lambda _fid: False)
    cut = [fid for fid in truncated_citations(st.content, st.facts, exists)
           if f"[{fid}]" not in before]
    if not cited_ids(st.content):
        return _truncated_verdict(st, cut) if cut else None
    bad = dangling_citations(st.content, st.facts, exists)
    if cut and not bad:
        return _truncated_verdict(st, cut)
    if not bad:
        return None
    bad = bad + cut
    return Verdict(
        pick_dimension(st, "factual_grounding", "no_fabrication", "data_grounding"),
        f"The body cites {len(bad)} nonexistent facts ({', '.join(bad[:3])}). Copy only identifiers listed in the material; never invent them.",
        fix=lambda text: strip_citations(text, bad),


        fix_note=f"Removed citation identifiers absent from the database: {', '.join(bad[:3])}",
    )


def _truncated_verdict(st: State, cut: list[str]) -> Verdict:
    from .citations import strip_citations
    return Verdict(
        pick_dimension(st, "factual_grounding", "no_fabrication", "data_grounding"),
        f"Found {len(cut)} unknown identifiers ({', '.join(cut[:3])}). These may be incomplete copies of real identifiers. Removed them. Copy identifiers in full, exactly as supplied.",
        fix=lambda text: strip_citations(text, cut),

        fix_note=f"The previous round removed unknown citation identifiers: {', '.join(cut[:3])}。",
    )


MIN_CITED_ROUND_CHARS = 300


def citations_present(st: State) -> Verdict | None:
    if st.bag.get("outline_mode") or not st.facts:
        return None


    from .citations import citation_coverage, has_citation, locate_sources
    fresh = (st.fresh or "").strip()
    if len(fresh) < MIN_CITED_ROUND_CHARS or has_citation(fresh):
        return None
    said_before = int((st.bag.get("check_name_streak_prev") or {}).get("citations_present", 0))
    if said_before:
        located = locate_sources(fresh, list(st.facts or []))
        if located:
            lines = "；".join(f"「…{s[-24:]}」→ [{fid}]" for s, fid in located[:3])
            return Verdict(
                pick_dimension(st, "factual_grounding", "material_use", "no_fabrication"),
                f'Round {said_before + 1} still has no citations. These sentences match the material verbatim; copy their identifiers at the sentence endings: {lines}. Do not force citations onto unmatched sentences.',
            )
        return Verdict(
            pick_dimension(st, "factual_grounding", "material_use", "no_fabrication"),
            f"Round {said_before + 1} still has no citations. None of this round's {len(fresh)} characters has a verbatim source match in dates, quantities or wording. Do not invent citations. Rewrite the passage using statements actually in the material, together with their identifiers. Do not keep expanding unsupported judgments.",
            advisory=True,
        )


    head = (f'This round wrote {len(fresh)} characters using {len(st.facts)} available records, but the body has no [fact-id] citations. A source-note link in the form [title](note://id) also counts.')
    cov = citation_coverage(fresh, list(st.facts or []))
    if cov.located <= 0:


        return Verdict(
            pick_dimension(st, "factual_grounding", "material_use", "no_fabrication"),
            head + f'None of these {len(fresh)} characters has a verbatim source match in dates, quantities or wording. Do not invent citations. Rewrite using statements actually present in the material and copy their identifiers exactly. Stop expanding unsupported judgments.',


            advisory=True,
        )
    pairs = locate_sources(fresh, list(st.facts or []))
    cover = f'This round has {cov.located} sentences located verbatim in the material and {cov.marked} with citation identifiers.'
    if not pairs:


        return Verdict(
            pick_dimension(st, "factual_grounding", "material_use", "no_fabrication"),
            head + cover + 'Each of these sentences matches multiple records. Narrow each sentence using a date, quantity or quotation from one record, then cite that record. Do not invent citations for other sentences without a source match.',
        )
    lines = "；".join(f"「…{s[-24:]}」→ [{fid}]" for s, fid in pairs[:3])
    return Verdict(
        pick_dimension(st, "factual_grounding", "material_use", "no_fabrication"),
        head + cover + f'Copy the identifiers to the corresponding sentence endings: {lines}. Do not attach identifiers to unmatched sentences or invent identifiers. Each assertion should link back to supporting evidence.',
    )


def material_used(st: State) -> Verdict | None:
    """Facts were retrieved and none of them made it into the text.

    A deterministic backstop for a judgement the scorer gets wrong in one
    direction: it will happily rate ``material_use`` as met while the round
    used nothing. Whether a fact's characteristic terms appear in the text is
    countable, so it is counted -- same class of thing as the mechanical
    duplicate check.

    **Off in outline mode.** The user's own sections ("design", "market") may
    have nothing at all behind them in the knowledge base; forcing "you must
    use the material" leaves the model no move except to write "the available
    material cannot establish..." -- which is exactly where the audit-report
    voice came from. What that section needs is one line saying the record is
    missing, and then to move on.
    """
    if st.bag.get("outline_mode"):
        return None
    gap = grounding_check.grounding_gap(st.content, st.facts)
    if not gap:
        return None
    return Verdict(pick_dimension(st, "material_use", "factual_grounding"), gap)


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------


MIN_THIN_CHARS = 200


def barren_axes(st: State) -> list[str]:
    out: list[str] = []
    for key, slot in ((st.bag.get("ledger") or {}).get("axes") or {}).items():
        if int((slot or {}).get("total") or 0) > 0:
            continue
        if int((slot or {}).get("taken") or 0) > 0:
            continue
        out.append(key.split(":", 1)[1] if ":" in key else key)
    return out


def _asked(st: State) -> int:
    queries = (st.bag.get("ledger") or {}).get("queries") or []
    if queries:
        return len(queries)
    return len(st.trace.calls) if st.trace is not None else 0


def _abstain_hint(what: str) -> str:
    subject = f"「{what}」" if what else 'this point'
    return (f'Skip {subject} and write only what the existing user text and available material directly support. Do not put missing-material commentary or placeholders in the body. Add no text if nothing else is supported.')


def material_thin(st: State) -> Verdict | None:
    from .. import params
    if not params.SUFFICIENT_CONTEXT:
        return None
    if st.bag.get("outline_mode"):


        return None
    if st.bag.get("polish"):


        return None
    fresh = (st.fresh or "").strip()
    if len(fresh) < MIN_THIN_CHARS:
        return None
    asked = _asked(st)
    barren = barren_axes(st)
    if not st.facts:
        where = "、".join(barren[:3])
        if asked:
            about = f"（{where}）" if where else ""
            why = (f'This run queried {asked} times without finding a related record{about}. Rephrasing the same request will not create evidence.')
        elif _kb_empty(st):
            why = "This account's knowledge base is empty."
        else:
            why = ('No knowledge-base search was made this round and no material is available. First call filter_facts by topic or search_memory by keyword. If no evidence exists after searching, follow the instruction below.')
        return Verdict(
            pick_dimension(st, "factual_grounding", "material_use", "no_fabrication"),
            f"This round wrote {len(fresh)} characters. {why}Do not substitute generic content for missing user records; it cannot be checked against the user's evidence."
            + _abstain_hint(where[:20]),
            advisory=True,
        )
    if barren and not st.facts_new:
        from .citations import has_citation
        if not has_citation(fresh):
            where = "、".join(barren[:3])
            return Verdict(
                pick_dimension(st, "factual_grounding", "material_use", "no_fabrication"),
                f'「{where}" was searched without finding any records. This round nevertheless wrote {len(fresh)} characters with no [fact-id] citations. This section has no evidence to support it.'
                + _abstain_hint(where[:20])
                + ' This is about a topic with no supporting material, rather than the proportion of retrieved records used.',
                advisory=True,
            )
    return None
