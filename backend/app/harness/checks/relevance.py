"""Deterministic evidence relevance filtering with explicit retrieval injection and a bounded fallback floor."""

from __future__ import annotations

import re

MIN_SHARED_TERMS = 1
BROAD_TOPIC_FACTS = 1000

_EN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_NUM = re.compile(r"\d{2,}(?:[.,]\d+)?%?")


_MONTH = re.compile('(?<!\\d)(\\d{1,2})\\s*\u6708')
_CJK = re.compile('[\u4e00-\u9fff]+')

_HEAD = re.compile('^\\[([A-Za-z0-9_\\-]+)(?P<src> \u7684\u539f\u8bdd| original quote)?\\]\\s*(?:-\\s*[\\d-]+\uff5c[^\uff1a:]{0,12}[\uff1a:]\\s*)?')
_SUFFIX = re.compile(r"（[^）]{0,60}）\s*$")

_META_LINE = re.compile(r"^[（(][^）)]{0,160}[）)]$")
_BATCH_HEAD = re.compile('^(?:\u5171 )?(\\d+)(?: \u6761\uff0c\u8fd4\u56de | facts total; returning )(\\d+)(?: \u6761|:)')


_CITE_IN_TEXT = re.compile(r"\[[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+){2,}\]")
_FACT_ID_IN_RESULT = re.compile(r"^\[([A-Za-z0-9_\-]+)\]", re.M)
_QUERY_KEYS = ("query", "question", "keyword", "keywords", "text")


_STOP_CHARS = set('\u7684\u4e86\u5728\u662f\u548c\u4e0e\u53ca\u6216\u628a\u88ab\u5bf9\u5230\u4ece\u8fd9\u90a3\u5c31\u4e5f\u90fd\u8fd8\u53c8\u5f88\u4e0d\u6ca1\u6709\u4e2a\u4e00\u7740\u8fc7\u4e3a\u4ee5\u5e76\u5c06\u5176\u5b83\u4ed6\u5979\u6211\u4f60\u4eec')

_STOP_BIGRAMS = set('\u6211\u4eec \u4f60\u4eec \u4ed6\u4eec \u8fd9\u4e2a \u90a3\u4e2a \u53ef\u4ee5 \u9700\u8981 \u4ec0\u4e48 \u600e\u4e48 \u4ee5\u53ca \u4e00\u4e2a \u8fdb\u884c \u95ee\u9898 \u65f6\u95f4 \u65b9\u5f0f \u65b9\u6cd5 \u5185\u5bb9 \u60c5\u51b5 \u5730\u65b9 \u4e1c\u897f \u90e8\u5206 \u5f00\u59cb \u7ed3\u675f \u73b0\u5728 \u5df2\u7ecf \u8fd8\u6709 \u5c31\u662f \u4e0d\u662f \u7136\u540e \u56e0\u4e3a \u6240\u4ee5 \u4f46\u662f \u5982\u679c \u90a3\u4e48 \u8fd9\u6837 \u8fd9\u4e9b \u90a3\u4e9b \u6216\u8005 \u6bd4\u5982 \u53ef\u80fd \u5e94\u8be5 \u89c9\u5f97 \u77e5\u9053 \u5176\u5b9e \u4e00\u4e0b \u4e00\u4e9b \u8fd9\u91cc \u90a3\u91cc \u4e4b\u540e \u4e4b\u524d \u65f6\u5019 \u5bf9\u5427 \u53cd\u6b63 \u5927\u6982 \u6bd4\u65b9 \u80af\u5b9a \u53ea\u662f \u76f4\u63a5 \u81ea\u5df1 \u51fa\u6765 \u57fa\u672c \u8fd9\u4e48 \u90a3\u4e48 \u4e00\u76f4 \u5176\u4ed6 \u6240\u6709 \u6574\u4e2a \u76f8\u5bf9 \u6bd4\u8f83'.split())

_STOP_EN = {
    "speaker", "says", "said", "say", "the", "and", "that", "with", "this", "they", "will",
    "are", "was", "were", "have", "has", "had", "from", "for", "not", "but", "about", "into",
    "than", "then", "also", "what", "when", "where", "which", "would", "could", "should",
    "there", "their", "them", "been", "being", "more", "some", "very", "just", "like", "can",
    "you", "your", "our", "its", "user", "people", "thing", "things", "going", "want", "wants",
    "need", "needs", "think", "make", "made", "get", "got", "one", "two", "all", "any",
    "because", "between", "does", "did", "how", "who", "why", "yes", "now", "here", "out",
    "over", "only", "much", "many", "most", "other", "same", "such", "take", "see", "use",
    "used", "using", "way", "well", "still", "even", "back", "good", "new", "first", "last",
    "next", "time", "really", "something", "someone", "let", "lets", "okay", "right",
    "mentions", "mentioned", "asks", "asked", "tells", "told", "thinks", "doing", "before",
    "after", "quickly", "going", "able", "last", "more",
}


def terms(text: str, *, normalize=None) -> set[str]:
    if normalize is not None:
        text = normalize(text or "")
    out = {w.lower() for w in _EN.findall(text or "")} - _STOP_EN
    out |= set(_NUM.findall(text or ""))
    for m in _MONTH.finditer(text or ""):
        n = int(m.group(1))
        if 1 <= n <= 12:
            out.add(f'{n}\u6708')
    for run in _CJK.findall(text or ""):
        for i in range(len(run) - 1):
            g = run[i:i + 2]
            if g[0] in _STOP_CHARS or g[1] in _STOP_CHARS or g in _STOP_BIGRAMS:
                continue
            out.add(g)
    return out


def fact_body(fact: str) -> str:
    return _SUFFIX.sub("", _HEAD.sub("", (fact or "").strip())).strip()


def strip_ids(text: str) -> str:
    return _CITE_IN_TEXT.sub(" ", text or "")


def fact_key(fact: str) -> tuple[str, bool]:
    m = _HEAD.match((fact or "").strip())
    if not m:
        return "", False
    return m.group(1), bool(m.group("src"))


def shared_terms(fact: str, context_terms: set[str], *, normalize=None) -> int:
    return len(terms(fact_body(fact), normalize=normalize) & context_terms)


def sampled_ids(calls) -> set[str]:
    out: set[str] = set()
    for name, _args, result in calls or ():
        if name != "filter_facts":
            continue
        m = _BATCH_HEAD.match((result or "").lstrip())
        if m and int(m.group(1)) > BROAD_TOPIC_FACTS:
            out |= set(_FACT_ID_IN_RESULT.findall(result or ""))
    return out


_QUERY_TOOLS = ("search_memory", "gather_subject")


def _query_text(args) -> str:
    return " ".join(str((args or {}).get(k) or "") for k in _QUERY_KEYS
                    if isinstance((args or {}).get(k), str)).strip()


def queried_ids(calls, *, normalize=None) -> set[str]:
    hit: set[str] = set()
    miss: set[str] = set()
    for name, args, result in calls or ():
        if name not in _QUERY_TOOLS:
            continue
        qterms = terms(_query_text(args), normalize=normalize)
        for line in (result or "").splitlines():
            fid, is_src = fact_key(line.strip())
            if not fid or is_src:
                continue
            if qterms and shared_terms(line, qterms, normalize=normalize) >= MIN_SHARED_TERMS:
                hit.add(fid)
            else:
                miss.add(fid)
    return miss - hit


def queries_of(calls) -> str:
    parts: list[str] = []
    for _name, args, _result in calls or ():
        for k in _QUERY_KEYS:
            v = (args or {}).get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
    return "\n".join(parts)


MIN_KEPT = 3


def gate(facts: list[str], calls, context: str, *,
         min_shared: int = MIN_SHARED_TERMS, min_kept: int | None = None,
         apply: bool = True,
         refill=None, normalize=None) -> tuple[list[str], list[tuple[str, int]]]:
    ctx = terms(strip_ids(context or ""), normalize=normalize)

    sampled = sampled_ids(calls) | queried_ids(calls, normalize=normalize)
    if not ctx or not sampled:
        return list(facts), []
    facts = list(facts)
    scored: dict[str, int] = {}
    for f in facts:
        fid, is_src = fact_key(f)
        if fid and not is_src and fid in sampled:
            scored[fid] = shared_terms(f, ctx, normalize=normalize)
    drop_ids = {fid for fid, n in scored.items() if n < min_shared}

    if min_kept is None:
        min_kept = MIN_KEPT

    def _is_item(f: str) -> bool:
        return not _META_LINE.match((f or "").strip())

    if apply and drop_ids:

        total = sum(1 for f in facts if _is_item(f))

        gone_items = sum(1 for f in facts if _is_item(f) and fact_key(f)[0] in drop_ids)
        if total - gone_items < min_kept and refill is not None:


            have = set(facts)
            fresh = [f for f in (refill() or []) if f and f not in have]
            facts += fresh
            total += sum(1 for f in fresh if _is_item(f))


        order = {}
        for i, f in enumerate(facts):
            fid = fact_key(f)[0]
            if fid and fid not in order:
                order[fid] = i
        for fid in sorted(drop_ids, key=lambda i: (-scored[i], order.get(i, 1 << 30), i)):
            if total - gone_items >= min_kept:
                break
            drop_ids.discard(fid)
            gone_items -= sum(1 for f in facts if _is_item(f) and fact_key(f)[0] == fid)
    kept: list[str] = []
    dropped: list[tuple[str, int]] = []
    last_fid = ""
    for f in facts:
        fid, is_src = fact_key(f)
        if fid:
            last_fid = fid
            ok = fid not in drop_ids
        elif _META_LINE.match((f or "").strip()):
            ok = last_fid not in drop_ids
        else:
            ok = True
        if not ok:
            dropped.append((f, shared_terms(f, ctx, normalize=normalize)))
        if ok or not apply:
            kept.append(f)
    return kept, dropped
