"""User profile storage, evidence validation and bounded writing-preference retrieval."""

from __future__ import annotations

import re

COMPILE_PROMPT = """Translate the question into a KITE retrieval plan. Return JSON only.

TOPICS: {tree}
ENTITIES: {entities}
KINDS: {kinds}
TODAY: {today}
COVERAGE: __COVERAGE__
QUESTION: {question}

RULES
- `grep` is matched as a literal regex against fact text. Use ONE short
  distinctive stem: 2-4 characters for Chinese, a single word for English.
  A long mixed-language phrase often matches nothing. Prefer `topics` and
  `entities` filters; add `grep` only to narrow further.
- Never invent unit ids. To scope a query to the session where something was
  discussed, use shape 2 below and let the first stage find the units.
- Speaker labels (speaker_a, speaker_b, ...) are per-session diarization
  labels, not stable identities: the same label refers to different people in
  different sessions. Do not filter by them unless the question is explicitly
  about a labelled speaker.
- Only use a `time` filter when the question is actually about a period.

SHAPE 1 — single hop. Independent lookups, pooled and ranked together:
{{"queries":[{{"select":"facts","where":{{"grep":str,"who":[str],
"topics":[{{"code":str,"closure":true}}],"entities":[str],"kind":[str],
"time":[str,str]}},"pipe":[{{"op":"head","n":10}}]}}],"intent":"factual"}}

SHAPE 2 — multi hop. Use this whenever the question is scoped to the context
of something else: "in the meeting where X came up, what else was decided",
"after we agreed on X, what changed", "the person who raised X, what else did
they say". The first stage locates an anchor; later stages reference it with
"$name.units" / "$name.unit" / "$name.date". Reference resolution is
deterministic — you only write the template:
{{"stages":[
 {{"name":"anchor","select":"facts","where":{{"grep":str,
   "topics":[{{"code":str,"closure":true}}]}},"pipe":[{{"op":"head","n":3}}]}},
 {{"name":"rest","select":"facts","where":{{"units":"$anchor.units"}},
   "pipe":[{{"op":"head","n":12}}]}}],"intent":"factual"}}

Pick shape 2 if the question depends on first finding something; otherwise
shape 1 with one to three queries."""


_JUNK_ENTITY = re.compile(r"^(\d[\w\-]*|[a-z0-9_]{1,3})$")


_SPEAKER_LABEL = re.compile(r"^speaker[_ ]?[a-z0-9]$", re.I)

ENTITY_LIMIT = 80


def curated_entities(store, vocab, limit: int = ENTITY_LIMIT) -> str:
    counts: dict[str, int] = {}
    for f in store.facts.values():
        for code in f.entities:
            counts[code] = counts.get(code, 0) + 1
    picked = []
    for code, _n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if _SPEAKER_LABEL.match(code) or _JUNK_ENTITY.match(code):
            continue
        ent = vocab.entities.get(code)
        aliases = sorted(getattr(ent, "aliases", None) or []) if ent else []
        picked.append(code + (f" (aka {', '.join(aliases[:2])})" if aliases else ""))
        if len(picked) >= limit:
            break
    return ", ".join(picked) or "(none)"


def time_context(store) -> str:
    dates = sorted(u.date for u in store.units.values() if (u.date or "").strip())
    if not dates:
        return "(no dated sessions)"
    months: dict[str, int] = {}
    for d in dates:
        months[d[:7]] = months.get(d[:7], 0) + 1
    hist = " ".join(f"{k}:{v}" for k, v in sorted(months.items()))
    return (f"{dates[0]}..{dates[-1]} ({len(dates)} sessions) — by month: {hist}. "
            "Never invent session ids; use SHAPE 2 to find them.")


class WritingProfile:
    def __init__(self, base, store=None, vocab=None):
        self._base = base
        self._store = store
        self._vocab = vocab

    @property
    def COMPILE_PROMPT(self) -> str:  # noqa: N802
        if self._store is None or self._vocab is None:


            return COMPILE_PROMPT.replace("COVERAGE: __COVERAGE__\n", "")


        return COMPILE_PROMPT.replace(
            "ENTITIES: {entities}",
            "ENTITIES: " + curated_entities(self._store, self._vocab)
        ).replace("__COVERAGE__", time_context(self._store))

    @property
    def EXTRACT_PROMPT(self) -> str:  # noqa: N802
        return _writing_extract_prompt(self._base.EXTRACT_PROMPT)

    @property
    def EXTRACT_PROMPT_NO_FACETS(self) -> str:  # noqa: N802
        return _writing_extract_prompt(self._base.EXTRACT_PROMPT_NO_FACETS)

    def __getattr__(self, name):
        return getattr(self._base, name)


EXTRACT_RULES = """Extract facts that can be **written into the user's own notes later**.
SESSION DATE: {date}
SPEAKERS: {speakers}
KNOWN TOPICS: {tree}
KNOWN ENTITIES: {entities}
CONVERSATION (id|speaker|time|text):
{dialog}

This memory feeds a writing assistant, not a question-answering system. A fact
is useful only if it can be paraphrased into prose months later by someone who
was not in the room.

Rules:
- **Self-contained and load-bearing.** Each fact must carry its own context:
  what was decided or observed, the constraint or consequence attached to it,
  and the concrete numbers, dates, amounts, model names or part names involved.
  Write "the Aurora test fixture costs 120 USD per set, which
  must be included in the budget for the first 40 units", not "the fixture costs 120".
- **No relative time, no bare pronouns.** Write the date the session
  establishes, not the words the speaker used: "in June 2026", not "next
  month" / "later" / "currently" / "this year". Name the thing, not a pointer
  to it: "the wristband prototype", not "this plan" / "that project". A fact that says "starting this year" is unusable once it is read outside
  the conversation it came from.
- **Merge, do not atomise.** If one thing is discussed several times in this
  conversation — a number that changes, a decision that gets revised — emit ONE
  fact that carries the progression, not one fact per mention.
- **Keep real names; drop only the diarization labels.** Speaker A/B/C are
  per-session tags — the same label is a different person in another session —
  so never write "Speaker B said X" into the content. But when the transcript
  names an actual person, product, supplier or project, **keep that name in the
  fact**: "Morgan is preparing for the Aurora interview", not "a student is
  preparing for an interview". Generalising a named person into "someone" or
  "a student" destroys exactly what makes the fact worth writing about later.
  Attribution of who *said* it goes in the `who` field, not in the content.
- **Skip the noise.** Do not emit: filler and disfluency ("well, well", "he, he, he"),
  ASR garbage, greetings and scheduling chatter, bare questions with no answer,
  acknowledgements, or anything under about 15 characters. An empty facts list
  is a correct answer for a conversation that carried no durable content.
- Prefer fewer, richer facts over many thin ones. Ten usable facts beat fifty
  fragments.
- "kind": one of {kinds}. "who": the person or role the fact is about.
- "t": event time as YYYY-MM-DD or YYYY-MM when stated or safely resolvable;
  otherwise null. "conf": high, med, or low.
- "topics": reuse the most specific known codes. If none fits, propose one
  specific child under a known root. "entities": named people, places,
  organizations, products, works, or other concrete named things — **never
  Speaker A/B/C style labels**.
- "src": one or more message IDs that directly support the fact.
"""


class ExtractPromptDrift(RuntimeError):
    pass


SCHEMA_MARKER = "Return JSON only"
FACETS_MARKER = "Add retrieval facets"


def _writing_extract_prompt(base_prompt: str) -> str:
    i = base_prompt.find(SCHEMA_MARKER)
    if i < 0:
        raise ExtractPromptDrift(
            f'The KITE extraction prompt does not contain {SCHEMA_MARKER!r}. The writing adapter cannot preserve its JSON schema. Refuse to generate a schema-free prompt that could silently extract no facts.')
    schema = base_prompt[i:]

    j = base_prompt.find(FACETS_MARKER)
    facets = base_prompt[j:i] if 0 <= j < i else ""
    return EXTRACT_RULES + "\n" + facets + schema
