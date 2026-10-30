"""Expose source-backed memory retrieval and browsing tools to writing agents."""

from __future__ import annotations

from ...database.kite.kite_memory import UserMemory
from .registry import ToolContext, register


FACT_CHARS = 200
SOURCE_CHARS = 300


def kb_is_empty(user: str) -> bool:
    """Distinguish an empty knowledge base from a query with no matches."""
    return UserMemory(user).is_empty()


EMPTY_KB = (
    '(The knowledge base is empty; this user has not imported any material. **Do not '
    'rephrase searches or switch retrieval tools**: no evidence is available this '
    'round. Write only what the existing user text supports. Identify genuinely missing'
    ' material once and let the user supply it; do not repeat missing-material '
    'reminders.)'
)


def _fmt_facts(rows: list[dict], *, with_id: bool = True, user: str = "") -> str:
    if not rows:
        return EMPTY_KB if user and kb_is_empty(user) else '(No matching facts)'
    out = []
    mem = UserMemory(user) if user else None
    for r in rows:


        if mem is not None and r.get("id") and not r.get("entities"):
            r = {**r, **(mem.fact_by_id(r["id"]) or {})}
        head = f"[{r.get('id','')}] " if with_id and r.get("id") else ""


        when = r.get("when") or r.get("date") or 'No date'
        who = r.get("who") or ""
        entities = [str(x) for x in (r.get("entities") or []) if str(x).strip()]
        subject = f"Subjects: {', '.join(entities[:3])}" if entities else ""
        meta = " · ".join(x for x in (when, subject, who, r.get("kind") or "") if x)
        out.append(f"{head}{r.get('text','')[:FACT_CHARS]}\n    ({meta})")
    return "\n".join(out)


@register(
    name="search_memory",
    description=(

            "Search the user's knowledge base by keyword and return relevant facts with "
            'identifiers. Use this to check a specific detail in past records. If no match is '
            'found, try another formulation or inspect list_topics before choosing a different '
            'retrieval path.'

    ),
    params={
        "query": {"type": "string", "description": 'Search sentence or keywords'},
        "limit": {"type": "integer", "description": 'Maximum facts to return; default 8'},
    },
    required=["query"],
)
def search_memory(ctx: ToolContext, query: str, limit: int = 8) -> str:
    rows, _terms, _took = UserMemory(ctx.user).recall(
        query, limit=max(1, min(int(limit or 8), 20)),
        scope=ctx.scope, evidence=True)
    hits = [r for r in rows if r.get("text")]
    return _fmt_facts(hits, user=ctx.user)


@register(
    name="list_topics",
    description=(

            'List knowledge-base topics and their fact counts. Use this when the subject is '
            'unclear or keyword search fails, then choose a topic actually covered by the '
            'records. Pass a returned code to filter_facts as its topic parameter.'

    ),
    params={
        "limit": {"type": "integer", "description": 'Maximum topics; default 40, ordered by descending fact count'},
    },
)
def list_topics(ctx: ToolContext, limit: int = 40) -> str:
    rows = UserMemory(ctx.user).topics(scope=ctx.scope)
    rows = [t for t in rows if t.get("fact_count")]
    rows.sort(key=lambda t: t["fact_count"], reverse=True)
    rows = rows[: max(1, min(int(limit or 40), 200))]
    if not rows:


        return EMPTY_KB if kb_is_empty(ctx.user) else '(The knowledge base has no topics yet)'
    return "\n".join(
        f"- {t['code']} ({t['fact_count']} facts"
        + (f", aliases: {', '.join(t['aliases'][:3])}" if t.get("aliases") else "")
        + ")"
        for t in rows
    )


@register(
    name="list_entities",
    description=(

            'List entities such as people, organizations and products with their fact counts. '
            'Use this to find how the records identify a subject. Pass a returned code to '
            'filter_facts as its entity parameter.'

    ),
    params={
        "type": {"type": "string", "description": 'Optional entity type, such as person, org or product; empty returns all types'},
        "limit": {"type": "integer", "description": 'Maximum entities; default 40, ordered by descending fact count'},
    },
)
def list_entities(ctx: ToolContext, type: str = "", limit: int = 40) -> str:  # noqa: A002
    rows = UserMemory(ctx.user).entities(scope=ctx.scope)
    if type:
        rows = [e for e in rows if (e.get("type") or "").lower() == type.lower()]
    rows = [e for e in rows if e.get("fact_count")]
    rows.sort(key=lambda e: e["fact_count"], reverse=True)
    rows = rows[: max(1, min(int(limit or 40), 200))]
    if not rows:
        return '(No matching entities)'
    return "\n".join(
        f"- {e['code']} | {e.get('name') or e['code']}"
        + (f" ({e['type']})" if e.get("type") else "")
        + f" — {e['fact_count']} facts"
        for e in rows
    )


@register(
    name="filter_facts",
    description=(

            'Filter facts by topic, entity, kind or speaker without keyword matching. Use exact'
            ' codes returned by list_topics or list_entities. Topic filters include descendant '
            'topics.'

    ),
    params={
        "topic": {"type": "string", "description": 'Topic code, including descendant topics'},
        "entity": {"type": "string", "description": 'Entity code'},
        "kind": {"type": "string", "description": 'Fact kind'},
        "who": {"type": "string", "description": 'Speaker'},
        "limit": {"type": "integer", "description": 'Maximum facts; default 15'},
    },
)
def filter_facts(ctx: ToolContext, topic: str = "", entity: str = "",
                 kind: str = "", who: str = "", limit: int = 15) -> str:
    if not any((topic, entity, kind, who)):
        return '(filter_facts requires at least one filter: topic, entity, kind or who)'
    rows, total = UserMemory(ctx.user).facts_page(
        topic=topic, entity=entity, kind=kind, who=who,
        limit=max(1, min(int(limit or 15), 50)), scope=ctx.scope)
    head = f"{total} facts total; returning {len(rows)}:\n" if total else ""
    return head + _fmt_facts(rows, user=ctx.user)


@register(
    name="facts_in_range",
    description=(

            'Return facts within a date range in chronological order. Use this for reviews, '
            'weekly reports and questions about a specific period. Dates use YYYY-MM-DD.'

    ),
    params={
        "date_from": {"type": "string", "description": 'Start date, YYYY-MM-DD'},
        "date_to": {"type": "string", "description": 'End date, YYYY-MM-DD'},
        "limit": {"type": "integer", "description": 'Maximum facts; default 30'},
    },
    required=["date_from", "date_to"],
)
def facts_in_range(ctx: ToolContext, date_from: str, date_to: str, limit: int = 30) -> str:
    rows = UserMemory(ctx.user).facts_between(date_from, date_to,
                                              limit=max(1, min(int(limit or 30), 100)), scope=ctx.scope)
    return _fmt_facts(rows, user=ctx.user)


@register(
    name="fact_sources",
    description=(

            'Trace a fact to its original conversation lines, including speaker, date and '
            'wording. Use this to clarify a compressed fact or quote it precisely. Obtain '
            'fact_id from the bracketed identifiers in search_memory or filter_facts results.'

    ),
    params={
        "fact_id": {"type": "string", "description": 'Fact identifier'},
    },
    required=["fact_id"],
)
def fact_sources(ctx: ToolContext, fact_id: str) -> str:
    rows = UserMemory(ctx.user).fact_sources(fact_id)
    if not rows:
        return f"(No source found for fact {fact_id}; check the identifier)"
    return "\n".join(
        f"- {r.get('date') or 'No date'} | {r.get('who') or 'Unknown'}: {(r.get('text') or '')[:SOURCE_CHARS]}"
        for r in rows
    )


@register(
    name="search_session_context",
    description=(

            'Find a conversation by its content, then retrieve other material from that same '
            'conversation. Use this for questions such as what else was decided in the meeting '
            'that discussed X. It requires a model-based query compilation and can be slower. '
            'For ordinary fact lookup, use search_memory or filter_facts instead.'

    ),
    params={
        "question": {"type": "string",
                     "description": 'A complete question identifying the conversation to find and the information to retrieve from it'},
        "limit": {"type": "integer", "description": 'Maximum facts; default 10'},
    },
    required=["question"],
    group="memory",

    max_calls_per_round=1,
)
def search_session_context(ctx: ToolContext, question: str, limit: int = 10) -> str:
    """Compile a session-scoped query when a question requires multiple retrieval steps."""
    rows, multihop, took = UserMemory(ctx.user).recall_multihop(
        question, limit=max(1, min(int(limit or 10), 20)), scope=ctx.scope)
    head = (f"({'Multi-step session retrieval' if multihop else 'The compiled plan used ordinary retrieval; no multi-step session lookup was required'}"
            f"; {took / 1000:.1f}s)\n")
    return head + _fmt_facts(rows, user=ctx.user)


@register(
    name="gather_subject",
    description=(

            'Gather broader evidence for a subject: locate topics by keyword and retrieve '
            'related facts from their cluster. Use this to prepare a full section or understand'
            " a subject's development. For a specific detail, use search_memory. This tool "
            'returns a wider selection of facts.'

    ),
    params={
        "query": {"type": "string", "description": 'The subject of the section, stated in one sentence'},
        "limit": {"type": "integer", "description": 'Maximum facts; default 14'},
    },
    required=["query"],
)
def gather_subject(ctx: ToolContext, query: str, limit: int = 14) -> str:
    """Gather related section material while preserving the selected source scope."""
    from ...database.kb.recall import recall_clustered

    rows, _terms, _took = recall_clustered(
        UserMemory(ctx.user), query,
        limit=max(1, min(int(limit or 14), 30)), scope=ctx.scope,
        evidence=True, entity_guard=True)
    return _fmt_facts([r for r in rows if r.get("text")], user=ctx.user)
