"""Deterministic source-linked retrieval and query cleaning. Preserve fact identifiers and scope; use caller-provided planning only on explicit question paths."""

from __future__ import annotations

import re

from .who import is_speaker_tag

# How many candidates each channel contributes before ranking. Measured to
# saturate here: 400 gives 62% self-retrieval, 800 gives 63%, 1500 gives 63%.
POOL = 800

# Chinese n-grams promoted to fact-level greps. Four is where the measured
# gain lands; 8 and 12 change nothing and only cost query slots.
CJK_GREPS = 4

# English terms used the same way. Unchanged from the original.
WORD_GREPS = 3

# Total query slots handed to the plan executor.
MAX_QUERIES = 8


def plan(memory, query: str, vocab, *, pool: int = POOL, segment=None,
         common=None) -> list[dict]:
    topics, entities, _surfaces = memory._match_vocab(query, vocab)

    if entities and hasattr(memory, "_index"):
        try:
            from . import entities as entities_mod
            store, _ = memory._index()
            g = entities_mod.for_store(store, vocab)
            entities = list(dict.fromkeys(m for e in entities for m in g.members(e)))
        except Exception:      # noqa: BLE001
            pass
    queries: list[dict] = []
    if topics or entities:
        queries.append({
            "select": "facts",
            "where": {"topics": topics, "entities": entities},
            "pipe": [{"op": "sort", "key": "t", "desc": True},
                     {"op": "head", "n": pool}],
        })


    words = [t for t in memory._candidate_terms(query) if t.lower() not in _EN_STOP and not _is_speaker_word(t.lower())]
    for term in (words or memory._candidate_terms(query))[:WORD_GREPS]:
        queries.append({"select": "facts", "where": {"grep": term},
                        "pipe": [{"op": "head", "n": pool}]})
    # **The change that mattered most.** These n-grams were being computed
    # and then used only against raw lines when everything else had already
    # failed. Searching facts with them is what took same-topic recall from
    # 38% to 97%.
    for gram in _cjk_greps(memory, query, segment, common):
        queries.append({"select": "facts", "where": {"grep": gram},
                        "pipe": [{"op": "head", "n": pool}]})
    return queries[:MAX_QUERIES]


def _cjk_greps(memory, query: str, segment, common=None) -> list[str]:
    grams = memory._cjk_terms(query)[:CJK_GREPS]
    if segment is None:
        return grams
    plain: list[str] = []
    words: list[str] = []
    for t in segment(_WS.sub("", (query or "").lower())):
        if len(t) >= 2 and _ALL_CJK(t) and not _is_cn_filler(t) and t not in plain:
            plain.append(t)
            if common is None or not common(t):
                words.append(t)
    keep = words or plain
    if not keep:
        return grams
    keep.sort(key=lambda w: -len(w))
    return keep[:CJK_GREPS]


# |---|---:|---|---|---:|


_IMG_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_MD = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_CITE_MARK = re.compile(r"\[[A-Za-z][\w-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+\]")

_GARBAGE = re.compile(r"<\|[^|>]*\|>")


def clean_query(text: str) -> str:
    s = _IMG_MD.sub("", text or "")
    s = _LINK_MD.sub(r"\1", s)
    s = _CITE_MARK.sub("", s)
    s = _GARBAGE.sub(" ", s)
    return re.sub(r"[ \t]{2,}", " ", s)


def _terms(memory, query: str, weigh=None) -> list[str]:
    out: list[str] = []
    for t in memory._candidate_terms(query) + memory._cjk_terms(query, weigh) + _number_terms(query):
        t = (t or "").lower()
        if t and t not in out:
            out.append(t)


    kept = [t for t in out if t not in _EN_STOP and not _is_speaker_word(t)
            and not _is_cn_filler(t)]


    if kept:
        return kept
    return out if len(query.strip()) <= _SHORT_QUERY else []


# · **`don` `doesn` `didn` `isn` `wasn` `haven` `wouldn` `shouldn` `couldn` `aren` `re` `ve` `ll`


_EN_STOP = frozenset("""
a an the it its is are was were be been being can could will would shall should may might must
they them their he she his her we us our you your i me my this that these those there here
have has had having do does did done not no yes but and or so if then than too very really just
also about after before again against all any because both each few for from into of on off over
under to up down out with without at by as in what which who whom when where why how
say says said saying talk talks talking know knows knew think thinks like likes want wants
now later still already only ever never always some more most much many other another such
am doing him himself herself hers itself myself ourselves yourself yourselves themselves
ours yours theirs through between while until during once above below further nor same own yet
don doesn didn isn wasn haven wouldn shouldn couldn aren hadn hasn weren mightn mustn needn
shan ain re ve ll
""".split())


_CN_FILLER = frozenset('\n\u7684 \u4e86 \u5728 \u662f \u548c \u4e0e \u53ca \u6216 \u628a \u88ab \u5bf9 \u5230 \u4ece \u8fd9 \u90a3 \u5c31 \u4e5f \u90fd \u8fd8 \u53c8 \u5f88 \u4e0d \u6ca1 \u6709 \u4e2a \u7740 \u8fc7 \u4e3a \u4ee5 \u53ca\n\u6211 \u4f60 \u4ed6 \u5979 \u5b83 \u6211\u4eec \u4f60\u4eec \u4ed6\u4eec \u54b1\u4eec \u81ea\u5df1 \u4ec0\u4e48 \u600e\u4e48 \u600e\u6837 \u5982\u4f55 \u4e3a\u4ec0\u4e48 \u54ea\u4e9b \u54ea\u4e2a \u591a\u5c11\n\u5e2e\u6211 \u5e2e\u5fd9 \u8bf7 \u9ebb\u70e6 \u4e00\u4e0b \u4e00\u4e2a \u4e00\u4e9b \u8fd9\u4e2a \u90a3\u4e2a \u8fd9\u4e9b \u90a3\u4e9b \u73b0\u5728 \u7136\u540e \u6240\u4ee5 \u56e0\u4e3a \u4f46\u662f \u800c\u4e14\n\u5199 \u5199\u4e00 \u5199\u4e00\u4e2a \u751f\u6210 \u505a\u4e00 \u505a\u4e00\u4e2a \u6574\u7406 \u68b3\u7406 \u603b\u7ed3 \u6982\u62ec \u5f52\u7eb3 \u5217\u51fa \u7ed9\u51fa \u7ed9\u6211 \u770b\u770b \u8bf4\u8bf4\n\u4e00\u4e0b\u5b50 \u4e00\u70b9 \u53ef\u4ee5 \u80fd\u5426 \u662f\u5426 \u9700\u8981\u6ce8\u610f\n'.split())


_FILLER_CHARS = frozenset("".join(_CN_FILLER))


def _is_cn_filler(t: str) -> bool:
    if t in _CN_FILLER:
        return True
    return bool(t) and all('\u4e00' <= c <= '\u9fff' and c in _FILLER_CHARS for c in t)


_SHORT_QUERY = 4


def _is_speaker_word(t: str) -> bool:
    return t in ("speaker", '\u8bf4\u8bdd\u4eba', '\u53d1\u8a00\u4eba') or is_speaker_tag(t)


_NUM = re.compile('\\d+\u6708\\d+|\\d+(?:\\.\\d+)?[\u53f0\u5957\u4e2a\u4ef6\u4eba\u6b21\u8f6e\u7248\u5143\u4e07\u4ebf%]|\\d{3,}(?:\\.\\d+)?')


def _number_terms(query: str) -> list[str]:
    return _NUM.findall(_WS.sub("", query))


_WS = re.compile(r"\s+")


def _hits(terms: list[str], text: str) -> list[str]:
    low = (text or "").lower()
    squeezed = _WS.sub("", low)
    out = []
    for t in terms:
        if t.isascii() and t[0].isalpha():
            if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", low):
                out.append(t)
            elif len(t) >= 6 and t in squeezed:


                out.append(t)
        elif t in squeezed:
            out.append(t)
    return out


def _clusters(hits: list[str]) -> list[str]:
    hs = sorted(set(hits), key=lambda h: (-len(h), h))
    out: list[str] = []
    for h in hs:
        if not any(h in o for o in out):
            out.append(h)
    return out


LONG_QUERY = 100
LONG_QUERY_MIN_WORDS = 2


STRONG_CJK_MIN = 2


def _strong_enough(hits: list[str], query: str = "", segment=None, common=None) -> bool:
    cl = _clusters(hits)
    if len(cl) < LONG_QUERY_MIN_WORDS:
        return False
    weigh = _weigher(query, segment, common)
    for h in cl:
        n = weigh(h) if weigh is not None else None
        if n is None:
            if len(h) >= 3:
                return True
            continue
        if n >= STRONG_CJK_MIN:
            return True
    return False


EVIDENCE_CJK_MIN = 4
EVIDENCE_EN_MIN = 3


def evidence_runs(hits: list[str], query: str) -> list[str]:
    squeezed = squeeze(query)
    spans: list[list[int]] = []
    loose: list[str] = []
    for h in _clusters(hits):
        found = False
        start = 0
        while True:
            i = squeezed.find(h, start)
            if i < 0:
                break
            spans.append([i, i + len(h)])
            found = True
            start = i + 1


        if not found:
            loose.append(h)
    spans.sort()
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out: list[str] = []
    for r in [squeezed[a:b] for a, b in merged] + loose:
        if r not in out:
            out.append(r)

    return [r for r in out if not any(r != o and r in o for o in out)]


def _why(run: str, attested, weigh=None) -> str:
    if attested is not None and attested(run):
        return "vocab"
    if run.isascii():

        return "span" if run[:1].isalpha() and len(run) >= EVIDENCE_EN_MIN else "pair"
    n = weigh(run) if weigh is not None else None
    if n is None:
        n = len(run)
    return "span" if n >= EVIDENCE_CJK_MIN else "pair"


def _weigher(query: str, segment, common=None):
    if segment is None:
        return None
    from . import tokenize as _tok
    squeezed = squeeze(query)

    def useless(t: str) -> bool:
        return _is_cn_filler(t) or (common is not None and common(t))


    toks: list[str] | None = None

    def cut(s: str) -> list[str]:
        nonlocal toks
        if s != squeezed:
            return segment(s)
        if toks is None:
            toks = list(segment(s))
        return toks

    def weigh(run: str):
        if not _ALL_CJK(run):
            return None
        return _tok.content_chars(run, squeezed, cut, useless)

    return weigh


def _ALL_CJK(s: str) -> bool:
    return bool(s) and all('\u4e00' <= c <= '\u9fff' for c in s)


def squeeze(query: str) -> str:
    return _WS.sub("", (query or "").lower())


def squeezed_gaps(query: str) -> set[int]:
    out: set[int] = set()
    n = 0
    pending = False
    for ch in (query or "").lower():
        if _WS.match(ch):
            pending = True
            continue
        if pending:
            out.add(n)
            pending = False
        n += 1
    return out


def _token_spans(text: str, segment) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    pos = 0
    for t in segment(text):
        out.add((pos, pos + len(t)))
        pos += len(t)
    return out


def is_whole_token(run: str, squeezed: str, segment) -> bool:
    if segment is None or not run or run.isascii():
        return False
    spans = _token_spans(squeezed, segment)
    start = 0
    while True:
        i = squeezed.find(run, start)
        if i < 0:
            return False
        if (i, i + len(run)) in spans:
            return True
        start = i + 1


def is_merged_word(run: str, squeezed: str, segment) -> bool:
    if segment is None or not _ALL_CJK(run):
        return False
    from . import tokenize as _tok
    if run not in _tok.base_words():
        return False
    spans = _token_spans(squeezed, segment)
    start = 0
    while True:
        i = squeezed.find(run, start)
        if i < 0:
            return False
        j = i + len(run)
        for (a, b) in spans:
            if a <= i and j <= b and (a, b) != (i, j):
                return True
        start = i + 1


def evidence_label(run: str, squeezed: str | None = None, segment=None) -> str:
    if run.isascii():
        return run
    if squeezed is not None and segment is not None and is_whole_token(run, squeezed, segment):
        return run
    return run.strip(_EDGE_STOP)


def _word_bounds(text: str, segment) -> set[int]:
    out = {0}
    pos = 0
    for t in segment(text):
        pos += len(t)
        out.add(pos)
    return out


def _token_runs(text: str, segment) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    pos = 0
    for t in segment(text):
        out.append((pos, pos + len(t), t))
        pos += len(t)
    return out


def _word_window(a: int, b: int, squeezed: str, segment) -> str:
    toks = _token_runs(squeezed, segment)
    lo = next((s for s, e, _t in toks if s <= a < e), a)
    hi = next((e for s, e, _t in toks if s < b <= e), b)
    inner = [(s, e, t) for s, e, t in toks if s >= lo and e <= hi]
    while inner and all(c in _EDGE_STOP for c in inner[0][2]):
        inner.pop(0)
    while inner and all(c in _EDGE_STOP for c in inner[-1][2]):
        inner.pop()
    return squeezed[inner[0][0]:inner[-1][1]] if inner else ""


def _aligned(label: str, squeezed: str, segment) -> bool | None:
    if segment is None or not _ALL_CJK(label):
        return None
    bounds = _word_bounds(squeezed, segment)
    start = 0
    seen = False
    while True:
        i = squeezed.find(label, start)
        if i < 0:
            break
        seen = True
        if i in bounds and (i + len(label)) in bounds:
            return True
        start = i + 1
    return False if seen else None


def evidence(hits: list[str], query: str, *, common=None, attested=None,
             segment=None) -> list[dict]:
    runs = evidence_runs(hits, query)
    weigh = _weigher(query, segment, common)
    squeezed = squeeze(query)
    out: list[dict] = []
    for r in runs:
        if common is not None and common(r):
            continue


        label = evidence_label(r, squeezed, segment)
        al = _aligned(label, squeezed, segment)


        if al is False and is_merged_word(label, squeezed, segment):
            al = None
        out.append({"term": r, "why": _why(r, attested, weigh), "aligned": al})
    return out


def qualifies(hits: list[str], query: str, *, common=None, attested=None,
              segment=None) -> bool:
    if len((query or "").strip()) <= _SHORT_QUERY:
        return bool(hits)
    ev = evidence(hits, query, common=common, attested=attested, segment=segment)
    if not ev:
        return False
    if len(ev) >= 2:
        return True
    return ev[0]["why"] != "pair"


def display_terms(terms: list[str], query: str, *, segment=None) -> list[str]:
    squeezed = squeeze(query)
    plain: list[str] = []
    spans: list[tuple[int, int]] = []
    for t in terms:
        if not t or (t.isascii() and t[0].isalpha()) or t[0].isdigit():
            if t and t not in plain:
                plain.append(t)
            continue
        start = 0
        while True:
            i = squeezed.find(t, start)
            if i < 0:
                break
            spans.append((i, i + len(t)))
            start = i + 1
    spans.sort()


    gaps = squeezed_gaps(query)
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1] and not (a == merged[-1][1] and a in gaps):
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = list(plain)
    for a, b in merged:
        if segment is None:


            while b < len(squeezed) and b - a < 8 and _IS_CJK(squeezed[b]) and squeezed[b] not in _EDGE_STOP:
                b += 1
            w = squeezed[a:b].strip(_EDGE_STOP)
        else:

            w = _word_window(a, b, squeezed, segment)


        al = _aligned(w, squeezed, segment)
        if al is False and is_merged_word(w, squeezed, segment):
            al = None
        if al is False:
            continue

        if len(w) >= 2 and not any((w in o or o in w) for o in out if not o.isascii()):
            out.append(w)
    return out[:8]


def _IS_CJK(ch: str) -> bool:
    return '\u4e00' <= ch <= '\u9fff'


_EDGE_STOP = '\u7684\u4e86\u5728\u662f\u548c\u4e0e\u53ca\u6216\u628a\u88ab\u5bf9\u5230\u4ece\u8fd9\u90a3\u6211\u4eec\u4f60\u4ed6\u5979\u5b83\u5c31\u4e5f\u90fd\u8fd8\u53c8\u5f88\u4e0d\u6ca1\u6709\u4e2a\u4e00\u7740\u8fc7\u4e3a\u4ee5\u4e0a\u91cc\u5e76\u4e14\u800c\u4f46\u53f7\u65e5\u4e0a\u4e0b\u524d\u540e\u4e2d'


def matched_terms(rows: list[dict], query: str, memory, store,
                  *, common=None, segment=None) -> list[str]:
    terms = _terms(memory, query, _weigher(query, segment, common))
    texts = [(store.facts.get(r.get("id")).text if store.facts.get(r.get("id")) else "") or "" for r in rows]
    hit: set[str] = set()
    for x in texts:
        hit.update(_hits(terms, x))
    return [t for t in terms if t in hit][:8]


def rank(rows: list[dict], query: str, memory, store, *, limit: int,
         evidence: bool = False, common=None, attested=None, segment=None) -> list[dict]:
    """Order the pool by how much of the query each fact contains.

    Score is the total length of the query terms found in the fact's text.
    Length-weighted because a three-character n-gram matching is much
    stronger evidence than a two-character one; **not** normalised by fact
    length -- normalising was measured and made same-topic recall slightly
    worse, since a long fact covering more of the subject is usually the one
    wanted.
    """


    terms = _terms(memory, query, _weigher(query, segment, common))
    if not terms:


        return []


    group_codes: set[str] = set()
    if hasattr(memory, "_match_vocab") and hasattr(memory, "_index"):
        try:
            from . import entities as entities_mod
            _t, ents, _s = memory._match_vocab(query, getattr(memory, "_index")()[1])
            g = entities_mod.for_store(store, getattr(memory, "_index")()[1])
            group_codes = {m for e in ents for m in g.members(e)}
        except Exception:      # noqa: BLE001
            group_codes = set()
    ENTITY_BONUS = 4
    long_query = len((query or "").strip()) >= LONG_QUERY

    def score(row: dict) -> tuple[int, str]:
        fact = store.facts.get(row.get("id"))
        text = (fact.text if fact else "") or ""

        hits = _hits(terms, text)


        if long_query and not _strong_enough(hits, query, segment, common):
            return (0, row.get("date") or "")


        if evidence and not qualifies(hits, query, common=common, attested=attested,
                                      segment=segment):
            return (0, row.get("date") or "")
        s = sum(len(t) + (2 if t[0].isdigit() else 0) for t in hits)


        low = text.lower()
        s += sum(min(2, max(0, low.count(t) - 1)) for t in hits)
        if group_codes and fact is not None and group_codes & set(getattr(fact, "entities", ()) or ()):
            s += ENTITY_BONUS
        return (s, row.get("date") or "")


    scored = [(sc, r) for r in rows if (sc := score(r))[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)


    if len(scored) > 2:
        lead: set[str] = set()
        for (_s, r) in scored[:1]:
            f = store.facts.get(r.get("id"))
            lead |= set(getattr(f, "topics", ()) or ()) if f is not None else set()
        if lead:
            def bump(item):
                (sc, d), r = item
                f = store.facts.get(r.get("id"))
                return ((sc + (1 if f is not None and lead & set(getattr(f, "topics", ()) or ()) else 0), d), r)
            scored = sorted((bump(x) for x in scored), key=lambda x: x[0], reverse=True)
    return [r for _s, r in scored][:limit]
