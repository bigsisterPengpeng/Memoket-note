"""User-scoped KITE adapter for structured facts, vocabulary, source evidence and retrieval. Keep engine data outside the application bundle."""

from __future__ import annotations

import copy
import functools
import os
from contextlib import contextmanager
from types import SimpleNamespace
import re

from ..kb.who import norm_who
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path


from memoket_kite import Memory
from memoket_kite.core.algebra import CONF_ORDER, Store, execute_plan
from memoket_kite.core.vocab import Topic, norm_code
from memoket_kite.pipeline.extract import _consolidation_round_votes
from memoket_kite.providers.llm import llm_json
from memoket_kite.storage import _verify_loadable

from .. import store
from . import kite_entity_candidates, kite_extract_profile, kite_tokens, kite_topic_promotion
from ..kb import search
from ..kb.who import is_speaker_tag
from ...util.config import get_settings
from .kite_writer import write_lock

kite_extract_profile.install()
kite_entity_candidates.install()


kite_topic_promotion.install()


kite_tokens.install()

# Root topics seeded into every new codebook. KITE's extraction prompt only
# lets the model propose a topic as a child of an already-known root
# (prompts/extract.py: "propose one specific child under a known root"), and
# core/vocab.py's propose_topic() rejects any proposal whose parent doesn't
# already resolve ("orphan proposals are rejected"). A brand-new vocab has no
# roots at all, so topics can never bootstrap themselves from zero — this
# fixes that from the very first ingest.
# Aliases are extra surface forms recall()/ask() can match against non-English
# input; the app already treats English + Chinese as first-class elsewhere
# (see STOPWORDS / _cjk_terms below), so both are seeded here too.
ROOT_TOPICS: dict[str, tuple[str, ...]] = {
    "work": ('\u5de5\u4f5c',),
    "project": ('\u9879\u76ee',),
    "personal": ('\u4e2a\u4eba',),
    "learning": ('\u5b66\u4e60',),
    "health": ('\u5065\u5eb7',),
    "finance": ('\u8d22\u52a1', '\u7406\u8d22'),
}


def _root_topics_xml() -> str:
    parts = []
    for code, aliases in ROOT_TOPICS.items():
        alias_xml = "".join(f"<alias>{a}</alias>" for a in aliases)
        parts.append(f'    <topic code="{code}" status="canonical" parents="" born="">{alias_xml}</topic>')
    return "\n".join(parts)


EMPTY_CODEBOOK = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<codebook id="{uid}" speakers="user">\n'
    "  <vocab>\n"
    f"{_root_topics_xml()}\n"
    "  </vocab>\n"
    "  <timeline/>\n"
    "</codebook>\n"
)


STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "was", "were", "be", "what", "which", "who", "when", "where", "how", "why",
    "i", "my", "me", "we", "our", "you", "your", "it", "this", "that", "with",
    "about", "did", "do", "does", '\u6709', '\u7684', '\u4e86', '\u662f', '\u5728', '\u6211', '\u4f60', '\u4ed6',
    '\u4ec0\u4e48', '\u600e\u4e48', '\u54ea\u4e9b', '\u8fd9\u4e2a', '\u90a3\u4e2a',
}


def _export_provider_env() -> None:
    cfg = store.get_active_llm_config()
    os.environ["OPENAI_API_KEY"] = cfg["api_key"]
    os.environ["OPENAI_BASE_URL"] = cfg["base_url"]


class ProviderFailed(RuntimeError):
    pass


@contextmanager
def _watch_provider():
    from memoket_kite.providers import llm as kite_llm
    failures: list[str] = []
    real_http = kite_llm._http_llm
    real_time = kite_llm.time
    real_sleep = real_time.sleep

    def http(*a, **kw):
        if failures:
            raise RuntimeError(failures[0])
        try:
            return real_http(*a, **kw)
        except Exception as exc:      # noqa: BLE001
            failures.append(_describe(exc))
            raise

    def sleep(sec):
        if not failures:
            real_sleep(sec)

    kite_llm._http_llm = http
    kite_llm.time = SimpleNamespace(sleep=sleep)
    try:
        yield failures
    finally:
        kite_llm._http_llm = real_http
        kite_llm.time = real_time


def _describe(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return f'The model service returned {code}'
    reason = getattr(exc, "reason", None)
    if reason is not None:
        return f'Could not connect to the model ({reason}）'
    return f'Model request failed ({type(exc).__name__}: {exc})'


_CJK_RE = re.compile('[\u4e00-\u9fff]')


def _is_cjk_pair(a: str, b: str) -> bool:
    return bool(_CJK_RE.search(a) or _CJK_RE.search(b))


_PHONETIC_MERGE_PROMPT = """For each pair of short Chinese text codes below
(extracted as named entities from noisy speech-to-text transcripts), judge
ONLY by how they would SOUND if spoken aloud in Mandarin — could a speech
recognizer plausibly have transcribed the same spoken word as these two
different strings, due to identical or very close pronunciation (homophones or near-homophones)? This is purely about pronunciation, not meaning or spelling —
ignore what each string might refer to.

PAIRS:
{pairs}

Return JSON only:
{{"decisions": [{{"i": 0, "merge": true, "winner": str}}]}}"""

_SPELLING_VARIANT_MERGE_PROMPT = """For each pair of short text codes below
(extracted as named entities from hastily typed or transcribed notes), judge
whether they are plausibly the SAME underlying word/name, differing only
because of a typo, a missing/extra letter, a singular/plural form, an
abbreviation, or a near-miss spelling variant — the kind of accidental
duplication that happens when the same entity gets written slightly
differently on different occasions. Do NOT merge pairs that are simply two
different real words/names that happen to be similar length or share some
letters (e.g. "mba" and "nba" are two different real acronyms, not a typo
of each other).

PAIRS:
{pairs}

Return JSON only:
{{"decisions": [{{"i": 0, "merge": true, "winner": str}}]}}"""


def _vote_entity_merges(vocabulary, candidates: list[tuple[str, str]], model: str,
                        batch_size: int = 60) -> dict[str, str]:
    cjk_candidates = [(a, b) for a, b in candidates if _is_cjk_pair(a, b)]
    latin_candidates = [(a, b) for a, b in candidates if not _is_cjk_pair(a, b)]

    entity_rewrites: dict[str, str] = {}
    merged_codes: set[str] = set()
    for candidate_group, prompt_template in (
        (cjk_candidates, _PHONETIC_MERGE_PROMPT),
        (latin_candidates, _SPELLING_VARIANT_MERGE_PROMPT),
    ):
        for start in range(0, len(candidate_group), batch_size):
            batch = candidate_group[start:start + batch_size]
            votes: dict[int, list] = {i: [] for i in range(len(batch))}
            prompt = prompt_template.format(
                pairs="\n".join(f"{i}: {a!r} | {b!r}" for i, (a, b) in enumerate(batch)))
            for _ in range(3):
                try:
                    data = llm_json(prompt, model=model)
                    round_votes = _consolidation_round_votes(data, batch)
                    for i in votes:
                        votes[i].append(round_votes.get(i))
                except RuntimeError:
                    continue
            for i, (first_code, second_code) in enumerate(batch):
                winners = [w for w in votes[i] if w]
                if len(winners) >= 2 and len(set(winners)) == 1:
                    winner = winners[0]
                    loser = second_code if winner == first_code else first_code
                    if loser in merged_codes or winner in merged_codes:
                        continue
                    if loser in vocabulary.entities and winner in vocabulary.entities:
                        entity_rewrites.update(vocabulary.merge_entities([loser], winner))
                        merged_codes.add(loser)
                        merged_codes.add(winner)
    return entity_rewrites


def _fact_seq(fact_id: str) -> int:
    m = re.search(r"F(\d+)$", fact_id)
    return int(m.group(1)) if m else 0


def _surface_in(sl: str, lowered: str) -> bool:
    if sl.isascii():
        if sl not in lowered:
            return False
        return _word_pattern(sl).search(lowered) is not None
    return sl in lowered


@functools.lru_cache(maxsize=4096)
def _word_pattern(sl: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![a-z0-9])" + re.escape(sl) + r"(?![a-z0-9])")


_PLAIN_GREP = re.compile("^[\\w'\\-\u4e00-\u9fff]{2,}$")

_ASCII_TERM = re.compile(r"^[0-9A-Za-z'\-]+$")
_MISSING = object()

_UNITS_CAP = 8


WORD_DF_MIN = 5


def _corpus_word(idx):
    from ..kb.search import _FILLER_CHARS

    def is_word(w: str) -> bool:
        if any(c in _FILLER_CHARS for c in w):
            return False
        n = idx.unit_df(w, floor=WORD_DF_MIN)
        return n is not None and n >= WORD_DF_MIN

    return is_word

_NO_UNIT = "__memoket_no_unit__"


class _GrepIndex:
    __slots__ = ("_blob", "_grams", "_line_blob", "_line_grams", "_memo", "_line_memo", "_df_memo")

    def __init__(self, store) -> None:
        self._blob, self._grams = self._build(
            (f.unit, f.text) for f in getattr(store, "facts", {}).values())
        self._line_blob, self._line_grams = self._build(
            (ln.unit, ln.text) for ln in getattr(store, "lines", {}).values())
        self._memo: dict[str, frozenset | None] = {}
        self._line_memo: dict[str, frozenset | None] = {}
        self._df_memo: dict[str, int | None] = {}

    @property
    def unit_count(self) -> int:
        return len(self._blob)

    def unit_df(self, term: str, *, floor: int = 0) -> int | None:
        hit = self._df_memo.get(term, _MISSING)
        if hit is not _MISSING:
            return hit
        units = self.units_for(term)
        if units is None or len(units) < floor or not _ASCII_TERM.match(term):
            out = None if units is None else len(units)
        else:
            rx = re.compile(rf"(?<![0-9A-Za-z]){re.escape(term)}(?![0-9A-Za-z])", re.I)
            out = sum(1 for u in units if rx.search(self._blob[u]))
        if len(self._df_memo) >= 4096:
            self._df_memo.clear()
        self._df_memo[term] = out
        return out

    @staticmethod
    def _build(pairs) -> tuple[dict[str, str], dict[str, set[str]]]:
        per_unit: dict[str, list[str]] = {}
        for unit, text in pairs:
            if unit and text:
                per_unit.setdefault(unit, []).append(text)
        blob = {u: "\n".join(t) for u, t in per_unit.items()}
        grams: dict[str, set[str]] = {}
        for u, b in blob.items():
            f = b.casefold()
            for g in {f[i:i + 2] for i in range(len(f) - 1)}:
                grams.setdefault(g, set()).add(u)
        return blob, grams

    def units_for(self, term: str, *, lines: bool = False) -> frozenset | None:
        memo = self._line_memo if lines else self._memo
        if term in memo:
            return memo[term]
        out = self._units_uncached(term, lines=lines)
        if len(memo) >= 4096:
            memo.clear()
        memo[term] = out
        return out

    def _units_uncached(self, term: str, *, lines: bool) -> frozenset | None:
        if not _PLAIN_GREP.match(term or ""):
            return None
        blob, grams = (self._line_blob, self._line_grams) if lines else (self._blob, self._grams)
        folded = term.casefold()
        if len(folded) < 2:
            return None
        cand: set[str] | None = None
        for i in range(len(folded) - 1):
            ids = grams.get(folded[i:i + 2])
            if not ids:
                return frozenset()
            cand = set(ids) if cand is None else cand & ids
            if not cand:
                return frozenset()
        try:
            rx = re.compile(term, re.I)
        except re.error:
            return None
        return frozenset(u for u in (cand or ()) if rx.search(blob[u]))


def _narrow_grep_query(q: dict, units: frozenset | None) -> dict:
    if units is None or len(units) > _UNITS_CAP:
        return q
    where = dict(q.get("where") or {})
    where["units"] = sorted(units) if units else [_NO_UNIT]
    return {**q, "where": where}


def _rotate(per_run: list[list[str]], out: list[str], cap: int) -> list[str]:
    depth = 0
    while len(out) < cap and any(depth < len(g) for g in per_run):
        for grams in per_run:
            if depth < len(grams) and grams[depth] not in out:
                out.append(grams[depth])
                if len(out) >= cap:
                    break
        depth += 1
    return out


class UserMemory:
    _cache: dict[str, tuple[float, object, object]] = {}

    def __init__(self, user_id: str):
        self.user_id = re.sub(r"[^A-Za-z0-9_.-]", "_", user_id) or "default"
        s = get_settings()
        self.dir = Path(s.kite_data_dir) / self.user_id
        self.path = self.dir / "codebook.xml"


    def ensure(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(EMPTY_CODEBOOK.format(uid=self.user_id),
                                 encoding="utf-8")
        return self.path


    _last_used: dict[str, float] = {}
    IDLE_TTL_S = 300

    def _grep_index(self, store) -> "_GrepIndex | None":
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return None
        key = f"{self.path}#grepidx"
        hit = self._cache.get(key)
        if hit and hit[0] == mtime and hit[2] is store:
            return hit[1]
        try:
            idx = _GrepIndex(store)
        except Exception:      # noqa: BLE001
            return None
        self._cache[key] = (mtime, idx, store)
        return idx

    def _topic_face(self, store, idx):
        from ..kb.topic_face import TopicFace

        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return None
        key = f"{self.path}#topicface"
        hit = self._cache.get(key)
        if hit and hit[0] == mtime and hit[2] is store:
            return hit[1]
        try:
            face = TopicFace(store.facts.values(),
                             units_for=(idx.units_for if idx is not None else None))
        except Exception:      # noqa: BLE001
            return None
        self._cache[key] = (mtime, face, store)
        return face

    def _who_face(self, store, idx):
        from ..kb.topic_face import WhoFace

        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return None
        key = f"{self.path}#whoface"
        hit = self._cache.get(key)
        if hit and hit[0] == mtime and hit[2] is store:
            return hit[1]
        try:
            face = WhoFace(store.facts.values(),
                           units_for=(idx.units_for if idx is not None else None))
        except Exception:      # noqa: BLE001
            return None
        self._cache[key] = (mtime, face, store)
        return face

    def common_term(self):
        from ..kb import relations as R
        from ..kb import topic_face as TF

        store, _vocab = self._index()
        idx = self._grep_index(store)
        if idx is None or not idx.unit_count:
            return None
        total = idx.unit_count


        ask_face = total * R.COMMON_DF_RATIO < R.COMMON_DF_MIN

        def is_common(term: str) -> bool:
            n = idx.unit_df(term, floor=R.COMMON_DF_MIN)
            if not (n is not None and n >= R.COMMON_DF_MIN
                    and n / total >= R.COMMON_DF_RATIO):
                return False
            if not (ask_face and TF.has_cjk(term)):
                return True
            face = self._topic_face(store, idx)
            if face is None:
                return True

            if face.generic(term) is not False:
                return True


            who = self._who_face(store, idx)
            if who is None:
                return False
            return who.generic(term) is not False

        return is_common

    def vocab_term(self):
        try:
            _store, vocab = self._index()
        except Exception:      # noqa: BLE001
            return None


        key = f"{self.path}#vocabterm"
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = None
        hit = self._cache.get(key)
        if mtime is not None and hit and hit[0] == mtime and hit[2] is vocab:
            return hit[1]
        surfaces: set[str] = set()
        for code, topic in getattr(vocab, "topics", {}).items():
            if getattr(topic, "status", "") == "deprecated":
                continue
            for s in {code, *(getattr(topic, "aliases", set()) or set())}:
                sl = str(s).replace("_", " ").lower()
                if len(sl) >= 2:
                    surfaces.add(sl)
        for code, ent in getattr(vocab, "entities", {}).items():
            if is_speaker_tag(code) or is_speaker_tag(getattr(ent, "name", "")):
                continue
            for s in {code, getattr(ent, "name", ""), *(getattr(ent, "aliases", set()) or set())}:
                sl = str(s).replace("_", " ").lower()
                if len(sl) >= 2:
                    surfaces.add(sl)
        if not surfaces:
            return None

        def attested(term: str) -> bool:
            return term in surfaces

        if mtime is not None:
            self._cache[key] = (mtime, attested, vocab)
        return attested

    def segment(self):
        from ..kb import tokenize as tok

        try:
            store, vocab = self._index()
        except Exception:      # noqa: BLE001
            return None
        path = getattr(self, "path", None)
        key = f"{path}#segment"
        try:
            mtime = path.stat().st_mtime
        except (OSError, AttributeError):
            mtime = None
        hit = self._cache.get(key)
        if mtime is not None and hit and hit[0] == mtime and hit[2] is vocab:
            return hit[1]
        extra: set[str] = set()
        for code, topic in getattr(vocab, "topics", {}).items():
            for s in {code, *(getattr(topic, "aliases", set()) or set())}:
                extra.add(str(s).replace("_", " ").lower())
        for code, ent in getattr(vocab, "entities", {}).items():
            for s in {code, getattr(ent, "name", ""), *(getattr(ent, "aliases", set()) or set())}:
                extra.add(str(s).replace("_", " ").lower())


        try:
            idx = self._grep_index(store)
        except Exception:      # noqa: BLE001
            idx = None
        attest = _corpus_word(idx) if (idx is not None and idx.unit_count) else None

        try:
            t = tok.Tokenizer(extra, attest=attest)
        except Exception:      # noqa: BLE001
            return None
        if not t.enabled():
            return None
        if mtime is not None:
            self._cache[key] = (mtime, t.cut, vocab)
        return t.cut

    def _prescreen(self, store, queries: list[dict]) -> list[dict]:
        idx = self._grep_index(store)
        if idx is None:
            return queries
        out: list[dict] = []
        for q in queries:
            where = q.get("where") or {}
            term = where.get("grep") if isinstance(where, dict) else None
            if not term or len(where) != 1 or q.get("select", "facts") != "facts":
                out.append(q)
                continue
            out.append(_narrow_grep_query(q, idx.units_for(str(term))))
        return out

    def _index(self):
        self.ensure()
        mtime = self.path.stat().st_mtime
        key = str(self.path)
        self._last_used[key] = time.time()
        hit = self._cache.get(key)
        if hit and hit[0] == mtime:
            return hit[1], hit[2]
        store, vocab = Store.load([key])


        try:
            store._memoket_user = self.user_id
        except Exception:      # noqa: BLE001
            pass
        self._cache[key] = (mtime, store, vocab)
        return store, vocab

    def is_empty(self) -> bool:
        try:
            store, _vocab = self._index()
            return not getattr(store, "facts", None)
        except Exception:      # noqa: BLE001
            return False

    def invalidate(self) -> None:
        self._cache.pop(str(self.path), None)

    @classmethod
    def evict_idle(cls, ttl_s: float | None = None, now: float | None = None) -> int:
        ttl = cls.IDLE_TTL_S if ttl_s is None else ttl_s
        now = time.time() if now is None else now
        gone = 0
        for key in list(cls._cache):
            base = key.split("#", 1)[0]
            last = cls._last_used.get(base, 0.0)
            if now - last > ttl:
                cls._cache.pop(key, None)
                gone += 1
        if gone:
            import gc
            gc.collect()
        return gone

    @classmethod
    def cache_info(cls) -> dict:
        return {"entries": len(cls._cache), "users": sorted({k.split("#", 1)[0].rsplit("/", 2)[-2] for k in cls._cache})}


    @staticmethod
    def _candidate_terms(text: str) -> list[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text.lower())
        return [w for w in words if w not in STOPWORDS][:12]

    @staticmethod
    def _cjk_terms(text: str, weigh=None) -> list[str]:
        runs = [r for r in re.findall('[\u4e00-\u9fff]{2,}', text)
                if r not in STOPWORDS]
        runs.reverse()

        per_run: list[list[str]] = []
        for run in runs:
            grams: list[str] = []
            for size in (3, 2):
                for i in range(len(run) - size + 1):
                    g = run[i:i + size]
                    if g not in STOPWORDS and g not in grams:
                        grams.append(g)
            if grams:
                per_run.append(grams)


        first, second = per_run, []
        if weigh is not None:
            from ..kb.search import STRONG_CJK_MIN
            solid: dict[str, bool] = {}
            for grams in per_run:
                for g in grams:
                    if g not in solid:
                        n = weigh(g)
                        solid[g] = n is not None and n >= STRONG_CJK_MIN
            first = [[g for g in grams if solid[g]] for grams in per_run]
            second = [[g for g in grams if not solid[g]] for grams in per_run]

        return _rotate(second, _rotate(first, [], 16), 16)

    @staticmethod
    def _surface_in(sl: str, lowered: str) -> bool:
        return _surface_in(sl, lowered)


    _MV_MEMO_MAX = 256

    def _match_vocab(self, text: str, vocab) -> tuple[list[dict], list[str], list[str]]:
        memo = self.__dict__.setdefault("_mv_memo", {})
        hit = memo.get(text)
        if hit is not None and hit[0] is vocab:
            t, e, s = hit[1]
            return [dict(x) for x in t], list(e), list(s)
        out = self._match_vocab_uncached(text, vocab)
        if len(memo) >= self._MV_MEMO_MAX:
            memo.clear()
        memo[text] = (vocab, ([dict(x) for x in out[0]], list(out[1]), list(out[2])))
        return out

    def _match_vocab_uncached(self, text: str, vocab) -> tuple[list[dict], list[str], list[str]]:
        topics: list[dict] = []
        entities: list[str] = []
        hit_surfaces: list[str] = []
        lowered = text.lower()

        for term in self._candidate_terms(text):
            code = vocab.resolve_topic(term)
            if code and not any(t["code"] == code for t in topics):
                topics.append({"code": code, "closure": True})
                hit_surfaces.append(term)
            code = vocab.resolve_entity(term)


            if code and code not in entities and not is_speaker_tag(term) and not is_speaker_tag(code):
                entities.append(code)
                hit_surfaces.append(term)

        for code, topic in vocab.topics.items():
            if getattr(topic, "status", "") == "deprecated":
                continue
            for surface in {code, *getattr(topic, "aliases", set())}:
                sl = str(surface).replace("_", " ").lower()
                if len(sl) >= 2 and _surface_in(sl, lowered):
                    if not any(t["code"] == code for t in topics):
                        topics.append({"code": code, "closure": True})
                        hit_surfaces.append(sl)
                    break

        for code, ent in vocab.entities.items():
            if is_speaker_tag(code) or is_speaker_tag(getattr(ent, "name", "")):
                continue
            surfaces = {code, getattr(ent, "name", ""), *getattr(ent, "aliases", set())}
            for surface in surfaces:
                sl = str(surface).replace("_", " ").lower()
                if len(sl) >= 2 and _surface_in(sl, lowered):
                    if code not in entities:
                        entities.append(code)
                        hit_surfaces.append(sl)
                    break

        return topics[:4], entities[:4], hit_surfaces

    def recall(self, query: str, limit: int = 8, scope: str = "all", *,
               evidence: bool = False) -> tuple[list[dict], list[str], float]:
        t0 = time.perf_counter()


        query = search.clean_query(query)
        store, vocab = self._index()
        _topics, _entities, surfaces = self._match_vocab(query, vocab)


        surfaces = [x for x in surfaces if not is_speaker_tag(x)]


        common, attested = ((self.common_term(), self.vocab_term()) if evidence
                            else (None, None))


        segment = self.segment() if evidence else None


        queries = search.plan(self, query, vocab, segment=segment, common=common)
        facts: list[dict] = []
        if queries:
            rows, _trace = execute_plan(store, vocab, {"queries": self._prescreen(store, queries)},
                                        budget=search.POOL * 2)
            facts = [r for r in rows if r.get("type") == "fact"]


        facts = search.rank(facts, query, self, store, limit=limit * 4,
                            evidence=evidence, common=common, attested=attested,
                            segment=segment)

        if not facts:


            facts = search.rank(self._recall_via_lines(store, vocab, query, limit * 2),
                                query, self, store, limit=limit,
                                evidence=evidence, common=common, attested=attested,
                                segment=segment)


            surfaces = surfaces + self._cjk_terms(query)[:3]
        else:


            surfaces = surfaces + [t for t in search.matched_terms(
                facts, query, self, store, common=common, segment=segment)
                if t not in surfaces]

        from ..kb.scope import filter_rows
        facts = filter_rows(facts, scope)
        return facts[:limit], surfaces, (time.perf_counter() - t0) * 1000

    def recall_evidence(self, query: str, rows: list[dict]) -> list[dict]:
        store, _vocab = self._index()
        q = search.clean_query(query)
        common, attested, segment = self.common_term(), self.vocab_term(), self.segment()


        terms = search._terms(self, q, search._weigher(q, segment, common))
        squeezed = search.squeeze(q)
        idx = self._grep_index(store)
        seen: set[str] = set()
        out: list[dict] = []
        for r in rows:
            f = store.facts.get(r.get("id"))
            text = (f.text if f else "") or ""
            for e in search.evidence(search._hits(terms, text), q,
                                     common=common, attested=attested, segment=segment):
                term = e["term"]
                if e.get("aligned") is False:
                    continue


                label = search.evidence_label(term, squeezed, segment)
                if not term.isascii() and len(label) < 2:
                    continue
                if label in seen:
                    continue
                seen.add(label)
                out.append({"term": label, "why": e["why"],
                            "units": (idx.unit_df(term) if idx else None) or 0})
        return out[:6]

    def recall_multihop(self, question: str, limit: int = 8) -> tuple[list[dict], bool, float]:
        from memoket_kite.core.algebra import execute_plan
        from memoket_kite.pipeline.compile_plan import compile_plan

        from .kite_profile import WritingProfile

        t0 = time.perf_counter()
        _export_provider_env()
        kb, vocab = self._index()
        profile = WritingProfile(
            Memory.load([str(self.path)])._reasoner()._profile, kb, vocab)


        model = os.environ.get("KITE_MODEL") or store.get_active_llm_config()["model"]


        plan = compile_plan(question, vocab, kb, profile, model,
                            scorer=None, n_candidates=1)
        rows, _trace = execute_plan(kb, vocab, plan, speakers=kb.speakers,
                                    budget=limit)
        facts = [r for r in rows if r.get("type") == "fact"]
        return facts[:limit], bool(plan.get("stages")), (time.perf_counter() - t0) * 1000


    def _recall_via_lines(self, store, vocab, query: str, limit: int) -> list[dict]:
        terms = self._cjk_terms(query) + self._candidate_terms(query)
        if not terms:
            return []


        probe = [t for t in terms[:12]]
        hits: dict[str, int] = {}
        idx = self._grep_index(store)
        for term in probe:


            units = idx.units_for(term, lines=True) if idx is not None else None
            if units is not None and not units:
                continue
            rows, _t = execute_plan(
                store, vocab,
                {"queries": [_narrow_grep_query(
                    {"select": "lines", "where": {"grep": term},
                     "pipe": [{"op": "head", "n": limit}]}, units)]},
                budget=limit)
            for r in rows:
                unit = r.get("unit")
                text = (r.get("text") or "").lower()
                n = sum(1 for t in probe if t.lower() in text)
                if unit and n >= 2:
                    hits[unit] = max(hits.get(unit, 0), n)
        units = [u for u, n in sorted(hits.items(), key=lambda kv: -kv[1])][:4]

        if not units:
            return []

        rows, _t = execute_plan(
            store, vocab,
            {"queries": [{"select": "facts", "where": {"units": units[:8]},
                          "pipe": [{"op": "sort", "key": "t", "desc": True},
                                   {"op": "head", "n": limit}]}]},
            budget=limit)
        return [r for r in rows if r.get("type") == "fact"]

    def source_lines(self, fact_row: dict) -> list[str]:
        store, _vocab = self._index()
        out = []
        for line_id in (fact_row.get("src") or "").split():
            line = getattr(store, "lines", {}).get(line_id)
            if line is not None:
                out.append(getattr(line, "text", ""))
        return [t for t in out if t]


    def topics(self) -> list[dict]:
        store, vocab = self._index()
        counts: dict[str, int] = {}
        for f in store.facts.values():
            for code in f.topics:
                counts[code] = counts.get(code, 0) + 1
        return [
            {"code": t.code, "parents": sorted(t.parents), "status": t.status,
             "aliases": sorted(t.aliases), "fact_count": counts.get(t.code, 0)}
            for t in sorted(vocab.topics.values(), key=lambda t: t.code)
        ]

    def entities(self) -> list[dict]:
        store, vocab = self._index()
        counts: dict[str, int] = {}
        for f in store.facts.values():
            for code in f.entities:
                counts[code] = counts.get(code, 0) + 1
        return [
            {"code": e.code, "name": e.name, "type": e.etype,
             "aliases": sorted(e.aliases), "relations": sorted(e.rels),
             "fact_count": counts.get(e.code, 0)}
            for e in sorted(vocab.entities.values(), key=lambda e: e.code)
            if not is_speaker_tag(e.code) and not is_speaker_tag(e.name or "")
        ]

    def topic_entity_links(self) -> list[dict]:
        store, _vocab = self._index()
        counts: dict[tuple[str, str], int] = {}
        spk = {c for c, e in _vocab.entities.items() if is_speaker_tag(c) or is_speaker_tag(getattr(e, "name", "") or "")}
        for f in store.facts.values():
            for t in f.topics:
                for e in f.entities:
                    if e in spk:
                        continue
                    key = (t, e)
                    counts[key] = counts.get(key, 0) + 1
        return [{"topic": t, "entity": e, "weight": w}
                for (t, e), w in sorted(counts.items())]

    def _fact_dict(self, f) -> dict:
        return {"id": f.id, "text": f.text, "when": f.when, "kind": f.kind,
                "who": f.who, "conf": f.conf, "topics": list(f.topics),
                "entities": list(f.entities), "unit": f.unit}

    def facts_page(self, *, kind: str = "", who: str = "", topic: str = "",
                   entity: str = "", conf_min: str = "", limit: int = 20,
                   offset: int = 0) -> tuple[list[dict], int]:
        store, vocab = self._index()

        topic_closure: set[str] | None = None
        if topic:
            code = vocab.resolve_topic(topic) or topic
            topic_closure = vocab.downset(code, include_candidates=True) or {code}
        entity_code = vocab.resolve_entity(entity) if entity else ""
        if entity and not entity_code:
            entity_code = entity
        entity_codes: set[str] = set()
        if entity_code:
            from ..kb import entities as entities_mod
            entity_codes = set(entities_mod.for_store(store, vocab).members(entity_code))
        conf_floor = CONF_ORDER.get(conf_min, 0) if conf_min else 0

        def match(f) -> bool:
            if kind and f.kind != kind:
                return False
            if who and norm_who(f.who) != norm_who(who):
                return False
            if conf_floor and CONF_ORDER.get(f.conf, 1) < conf_floor:
                return False
            if topic_closure is not None and not (set(f.topics) & topic_closure):
                return False
            if entity_codes and not (entity_codes & set(f.entities)):
                return False
            return True

        rows = sorted((f for f in store.facts.values() if match(f)),
                      key=lambda f: f.when, reverse=True)
        total = len(rows)
        page = rows[offset:offset + limit]
        return [self._fact_dict(f) for f in page], total

    def facts_between(self, date_from: str, date_to: str, limit: int = 400) -> list[dict]:
        store, _vocab = self._index()
        rows = sorted(
            (f for f in store.facts.values() if date_from <= f.when <= date_to),
            key=lambda f: f.when,
        )
        return [self._fact_dict(f) for f in rows[:limit]]

    def fact_by_id(self, fact_id: str) -> dict | None:
        store, _vocab = self._index()
        fact = store.facts.get(fact_id)
        return self._fact_dict(fact) if fact is not None else None

    def fact_sources(self, fact_id: str) -> list[dict]:
        store, _vocab = self._index()
        fact = store.facts.get(fact_id)
        if not fact:
            return []
        out = []
        for line_id in fact.src:
            line = store.lines.get(line_id)
            if line is not None:
                out.append({"id": line.id, "unit": line.unit, "date": line.unit_date,
                           "who": line.who, "text": line.text})
        return out

    def timeline(self) -> list[dict]:
        store, _vocab = self._index()
        buckets: dict[str, dict] = {}
        for u in store.units.values():
            if not u.date:
                continue
            buckets.setdefault(u.date, {"date": u.date, "units": 0, "facts": 0})["units"] += 1
        for f in store.facts.values():
            if not f.when:
                continue
            buckets.setdefault(f.when, {"date": f.when, "units": 0, "facts": 0})["facts"] += 1
        return sorted(buckets.values(), key=lambda b: b["date"])

    def add_topic(self, code: str, *, parent: str = "", aliases: list[str] | None = None) -> dict:
        self.ensure()
        new_code = norm_code(code)
        if not new_code:
            raise ValueError('Topic name cannot be empty')

        with write_lock(self.path):
            _store, vocab = Store.load([str(self.path)])
            if new_code in vocab.topics:
                raise ValueError(f'Topic already exists: {new_code}')
            parent_code = ""
            if parent:
                parent_code = vocab.resolve_topic(parent) or ""
                if not parent_code:
                    raise ValueError(f'Parent topic not found: {parent}')

            topic = Topic(new_code, parents={parent_code} if parent_code else set(),
                          status="canonical")
            for alias in (aliases or []):
                a = norm_code(alias)
                if a and a != new_code:
                    topic.aliases.add(a)
            vocab.topics[new_code] = topic
            for alias in topic.aliases:
                vocab._alias_t[alias] = new_code
            self._publish_vocab_locked(vocab)

        self.invalidate()
        return {"code": new_code, "parents": sorted(topic.parents), "status": "canonical",
                "aliases": sorted(topic.aliases), "fact_count": 0}

    def _publish_vocab_locked(self, vocab) -> None:
        tree = ET.parse(self.path)
        root = tree.getroot()
        prior_vocab_el = root.find("vocab")
        new_vocab_el = vocab.to_xml()
        if prior_vocab_el is None:
            root.insert(0, new_vocab_el)
        else:
            root.insert(list(root).index(prior_vocab_el), new_vocab_el)
            root.remove(prior_vocab_el)
        ET.indent(tree, space="  ")

        fd, tmp_name = tempfile.mkstemp(
            suffix=".xml", prefix=f".{self.path.stem}-", dir=self.path.parent)
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
            Store.load([str(tmp_path)])  # refuse to publish an unreadable file
            os.replace(tmp_path, self.path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def settle_topics(self) -> dict:
        if not self.path.exists():
            return {"filled": 0, "promoted": []}
        with write_lock(self.path):
            store_, vocab = Store.load([str(self.path)])
            filled, promoted = kite_topic_promotion.settle(
                vocab, lambda unit: store_.units[unit].date if unit in store_.units else "")
            if filled or promoted:
                self._publish_vocab_locked(vocab)
        if filled or promoted:
            self.invalidate()
        return {"filled": filled, "promoted": promoted}

    @classmethod
    def settle_all_topics(cls, data_dir: Path | str | None = None) -> dict[str, dict]:
        base = Path(data_dir or get_settings().kite_data_dir)
        out: dict[str, dict] = {}
        for path in sorted(base.glob("*/codebook.xml")):
            try:
                if not kite_topic_promotion.needs_settle(path.read_text(encoding="utf-8")):
                    continue
                mem = cls(path.parent.name)
                mem.dir, mem.path = path.parent, path
                out[path.parent.name] = mem.settle_topics()
            except Exception as exc:      # noqa: BLE001
                out[path.parent.name] = {"error": str(exc)}
        return out


    def remember(self, messages: list[dict], *, session_id: str,
                 date: str | None = None, title: str = "",
                 profile=None) -> int:
        cfg = store.get_active_llm_config()
        _export_provider_env()
        self.ensure()
        with write_lock(self.path):
            memory = Memory.load(self.path, model=cfg["model"])

            # DEFAULT_MEMORY_PROFILE——``memoket_kite.remember.extract_facts``


            patched = []
            if profile is not None:
                from memoket_kite.defaults import DEFAULT_MEMORY_PROFILE as _P
                for attr in ("EXTRACT_PROMPT", "EXTRACT_PROMPT_NO_FACETS"):
                    patched.append((attr, getattr(_P, attr)))
                    setattr(_P, attr, getattr(profile, attr))
            try:
                facts = memory.remember(messages, session_id=session_id,
                                        date=date, title=title or None)
            finally:
                if patched:
                    from memoket_kite.defaults import DEFAULT_MEMORY_PROFILE as _P
                    for attr, val in patched:
                        setattr(_P, attr, val)
        self.invalidate()
        return len(facts)

    def ask(self, question: str, limit: int = 10) -> tuple[str, list[dict]]:
        cfg = store.get_active_llm_config()
        _export_provider_env()
        self.ensure()
        memory = Memory.load(self.path, model=cfg["model"])
        with _watch_provider() as failures:
            result = memory.answer_with_evidence(question, limit=limit)


        evidence = getattr(result, "evidence", None)
        if evidence is None:
            evidence = getattr(result, "facts", None) or []
        facts = []
        for f in evidence:
            fact_id = f.id
            when = getattr(f, "when", "") or ""
            kind = getattr(f, "kind", "") or ""
            sources = [str(x.get("content", "")) if isinstance(x, dict) else str(x)
                       for x in (getattr(f, "sources", None) or [])]
            source_ids: list[str] = []


            if not when or not kind or not sources:
                try:
                    stored = self.fact_by_id(fact_id)
                    if stored:
                        when = when or stored.get("when", "")
                        kind = kind or stored.get("kind", "")
                        original = self.fact_sources(fact_id)
                        if original:
                            sources = [str(row.get("text", "")) for row in original if row.get("text")]
                            source_ids = [str(row.get("id", "")) for row in original if row.get("id")]
                except Exception:  # noqa: BLE001
                    pass
            facts.append({"id": fact_id, "text": f.content, "date": when,
                          "kind": kind, "sources": sources,
                          **({"_source_ids": source_ids} if source_ids else {})})
        if failures and not facts:
            raise ProviderFailed(failures[0])
        return result.text, facts


    def preview_entity_consolidation(self, min_len: int = 5, batch_size: int = 60) -> dict[str, str]:
        cfg = store.get_active_llm_config()
        _export_provider_env()
        _store, vocab = self._index()
        candidates = vocab.entity_merge_candidates(min_len=min_len)
        staged = copy.deepcopy(vocab)
        return _vote_entity_merges(staged, candidates, cfg["model"], batch_size)


    @staticmethod
    def note_prefix(note_id: str) -> str:
        return f"note-{note_id}-"

    def facts_for_prefix(self, prefix: str) -> list[dict]:
        store_, _vocab = self._index()
        rows = [f for f in store_.facts.values() if f.unit.startswith(prefix)]
        rows.sort(key=lambda f: (f.unit, _fact_seq(f.id)))
        out = []
        for f in rows:
            d = self._fact_dict(f)
            d["manual"] = f.unit.endswith("-manual")
            out.append(d)
        return out

    def _rewrite_xml(self, mutate) -> None:
        self.ensure()
        with write_lock(self.path):
            tree = ET.parse(self.path)
            root = tree.getroot()
            mutate(root)
            ET.indent(tree, space="  ")
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".xml", prefix=f".{self.path.stem}-",
                dir=self.path.parent, delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                tree.write(handle, encoding="utf-8", xml_declaration=True)
            try:
                _verify_loadable(temp_path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
            os.replace(temp_path, self.path)
        self.invalidate()

    def delete_facts(self, ids: set[str]) -> int:
        removed = 0

        def mutate(root):
            nonlocal removed
            for sess in root.iter("session"):
                for fe in list(sess.findall("fact")):
                    if fe.get("id") in ids:
                        sess.remove(fe)
                        removed += 1
        if ids:
            self._rewrite_xml(mutate)
        return removed

    def set_fact_text(self, fact_id: str, text: str) -> bool:
        hit = False

        def mutate(root):
            nonlocal hit
            for fe in root.iter("fact"):
                if fe.get("id") == fact_id:
                    fe.text = text
                    hit = True
        self._rewrite_xml(mutate)
        return hit

    def set_fact_attr(self, fact_id: str, name: str, value: str) -> bool:
        hit = False

        def mutate(root):
            nonlocal hit
            for fe in root.iter("fact"):
                if fe.get("id") == fact_id:
                    if value:
                        fe.set(name, value)
                    elif name in fe.attrib:
                        del fe.attrib[name]
                    hit = True
        self._rewrite_xml(mutate)
        return hit

    def fact_attrs(self, name: str) -> dict[str, str]:
        self.ensure()
        key = f"{self.path}#{name}"
        mtime = self.path.stat().st_mtime
        self._last_used[str(self.path)] = time.time()
        hit = self._cache.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
        out: dict[str, str] = {}
        try:
            for _ev, el in ET.iterparse(self.path):
                if el.tag == "fact" and el.get(name):
                    out[el.get("id") or ""] = el.get(name) or ""
        except ET.ParseError:
            out = {}
        self._cache[key] = (mtime, out, None)
        return out

    def add_manual_fact(self, session_id: str, text: str, *, date: str, title: str,
                        who: str = "") -> dict:
        new_id = ""

        def mutate(root):
            nonlocal new_id
            timeline = root.find("timeline")
            if timeline is None:
                timeline = ET.SubElement(root, "timeline")
            sess = next((s for s in timeline.findall("session") if s.get("id") == session_id), None)
            if sess is None:
                sess = ET.SubElement(timeline, "session", {"id": session_id, "t": "", "date": date,
                                                            "dur": "", "title": title})
            n = len(sess.findall("fact")) + 1
            line_id = f"{session_id}L{n}"
            fe = ET.SubElement(sess, "fact", {"id": f"{session_id}F{n}", "kind": "statement", "who": who,
                                              "t": "", "conf": "high", "topics": "", "entities": "",
                                              "src": line_id, "manual": "1"})
            fe.text = text
            le = ET.SubElement(sess, "line", {"id": line_id, "who": who or "user", "t": ""})
            le.text = text
            new_id = fe.get("id")
        self._rewrite_xml(mutate)
        return self.fact_by_id(new_id) or {"id": new_id, "text": text}

    def remove_sessions(self, prefix: str, keep_suffix: str = "-manual") -> int:
        removed = 0

        def mutate(root):
            nonlocal removed
            timeline = root.find("timeline")
            if timeline is None:
                return
            for sess in list(timeline.findall("session")):
                sid = sess.get("id") or ""
                if sid.startswith(prefix) and not (keep_suffix and sid.endswith(keep_suffix)):
                    timeline.remove(sess)
                    removed += 1
        self._rewrite_xml(mutate)
        return removed

    def apply_entity_consolidation(self, rewrites: dict[str, str]) -> Path:
        self.ensure()
        with write_lock(self.path):
            backup_path = self.path.with_name(f"{self.path.stem}.bak-{int(time.time())}{self.path.suffix}")
            shutil.copy2(self.path, backup_path)

            tree = ET.parse(self.path)
            root = tree.getroot()
            _store, vocab = Store.load([str(self.path)])

            applied: dict[str, str] = {}
            for loser, winner in rewrites.items():
                if loser in vocab.entities and winner in vocab.entities:
                    applied.update(vocab.merge_entities([loser], winner))

            for fact in root.iter("fact"):
                original_codes = (fact.get("entities") or "").split()
                rewritten_codes = []
                for code in original_codes:
                    new_code = applied.get(code, code)
                    if new_code not in rewritten_codes:
                        rewritten_codes.append(new_code)
                fact.set("entities", " ".join(rewritten_codes))

            new_vocab_el = vocab.to_xml()
            prior_vocab_el = root.find("vocab")
            if prior_vocab_el is not None:
                root.insert(list(root).index(prior_vocab_el), new_vocab_el)
                root.remove(prior_vocab_el)
            else:
                root.insert(0, new_vocab_el)

            ET.indent(tree, space="  ")
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".xml", prefix=f".{self.path.stem}-",
                dir=self.path.parent, delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                tree.write(handle, encoding="utf-8", xml_declaration=True)
            _verify_loadable(temp_path)
            os.replace(temp_path, self.path)

        self.invalidate()
        return backup_path

    def stats(self) -> dict:
        store, vocab = self._index()
        dates = sorted(u.date for u in store.units.values() if u.date)
        return {
            "facts": len(getattr(store, "facts", {}) or {}),
            "topics": len(vocab.topics),

            "entities": sum(1 for c, e in vocab.entities.items() if not is_speaker_tag(c) and not is_speaker_tag(getattr(e, "name", ""))),
            "units": len(getattr(store, "units", {}) or {}),
            "lines": len(getattr(store, "lines", {}) or {}),
            "speakers": sorted(getattr(store, "speakers", set()) or []),
            "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else None,
            "codebook": str(self.path),
        }
