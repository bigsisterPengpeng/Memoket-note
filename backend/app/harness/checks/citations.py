"""Deterministic, non-LLM citation verification.

The gap this closes: a model can be asked to self-report which source
material a claim rests on (the same "cite your sources" instruction already
used elsewhere in this package's host application), but that self-report is
itself just more model output -- nothing stops it from citing something
that sounds like a real source but was never actually shown to it. That
failure mode is different from "ungrounded" (no citation at all): it's a
*fabricated* citation, which reads as more trustworthy than no citation,
not less.

check_citations() answers a narrower, mechanically-verifiable question:
does each claimed source string actually match something in the pool of
material the model was given? A low match means the citation doesn't
correspond to real input -- evidence to feed into evaluate() (see
CitationCheck usage in rubric.py's citation_hints parameter), not a
verdict on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

DEFAULT_MATCH_THRESHOLD = 0.7


@dataclass(frozen=True)
class CitationCheck:
    """One claimed source's best match against the available material.
    ``best_match`` is already None whenever the best similarity found fell
    below whatever threshold check_citations() was called with -- ``verified``
    just reflects that, it does not re-derive against a fixed constant (an
    earlier version did, and disagreed with the threshold actually used)."""

    claimed: str
    best_match: str | None
    similarity: float

    @property
    def verified(self) -> bool:
        return self.best_match is not None


def check_citations(
    claimed_sources: list[str],
    available_facts: list[str],
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> list[CitationCheck]:
    """For each string in ``claimed_sources``, find its best fuzzy match in
    ``available_facts`` and report the similarity. A claimed source with no
    match above ``threshold`` was not actually among the material the model
    was shown -- it's citing something that doesn't exist in its own input,
    not just paraphrasing loosely."""
    checks: list[CitationCheck] = []
    for claimed in claimed_sources:
        if not claimed.strip():
            continue
        best_match, best_ratio = None, 0.0
        for fact in available_facts:
            ratio = SequenceMatcher(None, claimed, fact).ratio()
            if ratio > best_ratio:
                best_match, best_ratio = fact, ratio
        checks.append(CitationCheck(
            claimed=claimed,
            best_match=best_match if best_ratio >= threshold else None,
            similarity=round(best_ratio, 3),
        ))
    return checks


import re as _re

CITE = _re.compile(r"\[([A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+)\]")
_HEAD_ID = _re.compile(r"^\[([A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+)\]")


def cited_ids(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in CITE.finditer(text or ""):
        seen.setdefault(m.group(1), None)
    return list(seen)


def supplied_ids(facts: list[str]) -> set[str]:
    out = set()
    for f in facts:
        m = _HEAD_ID.match(f or "")
        if m:
            out.add(m.group(1))
    return out


def dangling_citations(text: str, facts: list[str], exists) -> list[str]:
    have = supplied_ids(facts)
    return [fid for fid in cited_ids(text) if fid not in have and not exists(fid)]


_LOOSE = _re.compile(r"(?<!\[)\[([A-Za-z][A-Za-z0-9_]*(?:-[0-9A-Za-z]+){2,})\](?!\()")


def malformed_citations(text: str) -> list[str]:
    valid = set(cited_ids(text))
    out: dict[str, None] = {}
    for m in _LOOSE.finditer(text or ""):
        if m.group(1) not in valid:
            out.setdefault(m.group(1), None)
    return list(out)


def fake_citations(text: str, facts: list[str], exists) -> list[str]:
    return dangling_citations(text, facts, exists) + malformed_citations(text)


_ID_LIKE = _re.compile(r"(?<!\[)\[([A-Za-z][A-Za-z0-9_]*(?:-[0-9A-Za-z]+)+)\](?!\()")


def id_prefixes(ids) -> set[str]:
    return {str(i).split("-")[0] for i in ids if str(i).split("-")[0]}


def truncated_citations(text: str, facts: list[str], exists) -> list[str]:
    valid = cited_ids(text)
    ns = id_prefixes(valid) | id_prefixes(supplied_ids(facts))
    if not ns:
        return []
    good = set(valid)
    out: dict[str, None] = {}
    for m in _ID_LIKE.finditer(text or ""):
        fid = m.group(1)
        if fid in good or fid.split("-")[0] not in ns:
            continue
        if exists(fid):
            continue
        out.setdefault(fid, None)
    return list(out)


NOTE_LINK = _re.compile(r"\[([^\]\n]*)\]\(note://([0-9a-f]{12})\)")


def note_link_ids(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in NOTE_LINK.finditer(text or ""):
        seen.setdefault(m.group(2), None)
    return list(seen)


def has_citation(text: str) -> bool:
    return bool(cited_ids(text) or note_link_ids(text))


_SENT_BREAK = _re.compile(r"[。！？；\n]")
MIN_NOTE_SENTENCE = 6


MIN_NOTE_SHARED = 3


def _sentence_before(text: str, at: int) -> str:
    head = text[:at]
    m = None
    for m in _SENT_BREAK.finditer(head):
        pass
    sent = head[m.end():] if m else head
    sent = CITE.sub("", NOTE_LINK.sub("", sent)).strip(" \t-*•>0123456789.、")
    if len(sent) < MIN_NOTE_SENTENCE:
        line_start = head.rfind("\n") + 1
        line_end = text.find("\n", at)
        line = text[line_start:line_end if line_end >= 0 else len(text)]
        sent = CITE.sub("", NOTE_LINK.sub("", line)).strip(" \t-*•>0123456789.、")
    return sent


def note_citations_unsupported(text: str, get_note, *, min_shared: int = MIN_NOTE_SHARED) -> list[dict]:
    from .grounding_rules import _terms
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    body_terms: dict[str, set[str] | None] = {}
    for m in NOTE_LINK.finditer(text or ""):
        title, nid = m.group(1), m.group(2)
        sent = _sentence_before(text, m.start())
        if (nid, sent) in seen:
            continue
        seen.add((nid, sent))
        if nid not in body_terms:
            body = get_note(nid)
            body_terms[nid] = _terms(body) if isinstance(body, str) else None
        terms = body_terms[nid]
        if terms is None:
            out.append({"id": nid, "title": title, "sentence": sent, "why": "missing", "shared": 0})
            continue
        shared = len(_terms(sent) & terms)
        if shared < min_shared:
            out.append({"id": nid, "title": title, "sentence": sent, "why": "unsupported", "shared": shared})
    return out


def strip_citations(text: str, ids: list[str]) -> str:
    for fid in ids:
        text = _re.sub(r"\s*\[" + _re.escape(fid) + r"\]", "", text)
    return text


MIN_SHARED_CITES = 2


def same_sources_twice(text: str, before: str = "", limit: int = 2) -> list[tuple[str, str]]:
    paras = [p.strip() for p in (text or "").split("\n\n") if len(p.strip()) >= 60]
    sets = [(p, set(cited_ids(p))) for p in paras]
    out: list[tuple[str, str]] = []
    for i, (pa, sa) in enumerate(sets):
        if len(sa) < MIN_SHARED_CITES:
            continue
        for pb, sb in sets[i + 1:]:
            if pa in before and pb in before:
                continue
            if len(sa & sb) >= MIN_SHARED_CITES:
                out.append((pa, pb))
                if len(out) >= limit:
                    return out
    return out


_ANCHOR = _re.compile(
    '\\d+\\s*[\u5e74\u6708\u65e5\u53f7\u70b9\u5206]|\\d+(?:\\.\\d+)?\\s*(?:%|\uff05|\u53f0|\u5957|\u4e2a|\u4eba|\u5929|\u5468|\u5c0f\u65f6|\u5206\u949f|\u79d2|\u5143|\u4e07|\u4ebf|kw|kwh|gb|tb|pb)',
    _re.I)
_SENT = _re.compile(r"[^。！？!?\n]+")
_CJK_RUN = _re.compile('[\u4e00-\u9fff]+')
_EN_WORD = _re.compile(r"[A-Za-z][A-Za-z'-]*")

MIN_VERBATIM_CJK = 6


MIN_VERBATIM_EN = 4


def _flat(text: str) -> str:
    return _re.sub(r"\s+", "", text or "")


def _anchors(text: str) -> set[str]:
    return {_flat(x).lower() for x in _ANCHOR.findall(text or "")}


def _shares_verbatim(sentence: str, fact: str, n: int = MIN_VERBATIM_CJK) -> bool:
    flat_fact = _flat(fact)
    for run in _CJK_RUN.findall(_flat(sentence)):
        for i in range(len(run) - n + 1):
            if run[i:i + n] in flat_fact:
                return True
    return _shares_verbatim_en(sentence, fact)


def _word_runs(text: str, n: int) -> set[str]:
    w = [x.lower() for x in _EN_WORD.findall(text or "")]
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def _shares_verbatim_en(sentence: str, fact: str, n: int = MIN_VERBATIM_EN) -> bool:
    runs = _word_runs(sentence, n)
    return bool(runs and (runs & _word_runs(fact, n)))


MIN_SENTENCE_CHARS = 15


def _indexed(facts: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for f in facts or []:
        m = _HEAD_ID.match((f or "").strip())
        if m:
            out.append((m.group(1), (f or "").strip()[m.end():]))
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.findall(text or "")
            if len(_flat(s.strip())) >= MIN_SENTENCE_CHARS]


def _hits(sent: str, indexed: list[tuple[str, str]]) -> set[str]:
    sa = _anchors(sent)
    return {fid for fid, body in indexed
            if (sa & _anchors(body)) or _shares_verbatim(sent, body)}


def locate_sources(text: str, facts: list[str]) -> list[tuple[str, str]]:
    indexed = _indexed(facts)
    if not indexed:
        return []
    out: list[tuple[str, str]] = []
    for sent in _sentences(text):
        if has_citation(sent):
            continue
        hits = _hits(sent, indexed)
        if len(hits) == 1:
            out.append((sent, hits.pop()))
    return out


@dataclass(frozen=True)
class CiteCoverage:
    sentences: int
    located: int
    marked: int
    matched: int

    @property
    def ratio(self) -> float | None:
        if not self.located:
            return None
        return round(self.marked / self.located, 3)


def citation_coverage(text: str, facts: list[str]) -> CiteCoverage:
    indexed = _indexed(facts)
    sents = _sentences(text)
    if not indexed:
        return CiteCoverage(len(sents), 0, 0, 0)
    located = marked = matched = 0
    for sent in sents:
        hits = _hits(sent, indexed)
        if not hits:
            continue
        located += 1
        cited = set(cited_ids(sent))
        if cited or note_link_ids(sent):
            marked += 1
            if cited & hits:
                matched += 1
    return CiteCoverage(len(sents), located, marked, matched)
