"""Compare claim quantities, dates and subjects with retrieved facts to classify source relationships."""

from __future__ import annotations

import re
from collections import defaultdict


_UNITS = ('mAh|km/h|kmh|mm|cm|km|kg|TB/s|TB|PB|GB|MB|MHz|GHz|Hz|GWh|MWh|kWh|kW|kV|MW|GW|W|V|tps|fps|ms|\u03bcs|us|min|dB|\u5e73\u65b9\u516c\u91cc|\u5e73\u65b9\u7c73|\u516c\u91cc|\u4e07\u5428|\u4e07\u5143|\u4ebf\u5143|\u7f8e\u5143|\u7f8e\u91d1|\u5757\u94b1|\u4e2a\u6708|\u5143|\u4e07|\u4ebf|\u53f0|\u4eba|\u5929|\u5468|\u5c0f\u65f6|\u5206\u949f|\u79d2|\u6b21|\u6761|\u9875|\u7248|\u6279|\u5957|%|\uff05|\u5e74|\u5361|\u8f86|\u5ea6|\u5428|\u7c73|\u4e2a|\u9879|\u5bb6|\u573a|\u4f4d|\u540d|\u7bc7|\u5f20/\u4eba\u5929|\u5f20|\u4efd|\u500d|\u8f6e|\u4ef6|\u5c42|\u7ea7|\u671f|\u5ea7|\u9897|\u9846|\u6b3e|\u79cd|\u6b65|\u6839')


#   `s0kmh`（50 km/h）→ 0 km/h · `S0ms`（50ms）→ 0ms · `S0%`（50%）→ 0% ·


_NUM = re.compile(f'(?<![\\dA-Za-z.])(-?\\d+(?:\\.\\d+)?)[+\u591a\u4f59]?\\s*({_UNITS})(?![A-Za-z])', re.IGNORECASE)


_UNIT_CANON = {u.lower(): u for u in _UNITS.split("|")}
_UNIT_ALIAS = {"％": "%", '\u9846': '\u9897', "kmh": "km/h", "μs": "us", "min": '\u5206\u949f'}
_DATE_FULL = re.compile('(\\d{4})[-/\u5e74.](\\d{1,2})[-/\u6708.](\\d{1,2})\u65e5?')
_DATE_MD = re.compile('(?<!\\d)(\\d{1,2})\\s*\u6708\\s*(\\d{1,2})\\s*\u65e5?')


_DATE_YM = re.compile('(\\d{4})\\s*\u5e74\\s*(\\d{1,2})\\s*\u6708(?!\\s*\\d)')
_DATE_M = re.compile('(?<![\\d\u5e74])(\\d{1,2})\\s*\u6708(?:\u672b|\u521d|\u4e2d|\u5e95|\u4efd)?(?!\\s*\\d)')
_DATE_Y = re.compile('(?<!\\d)((?:19|20)\\d{2})\\s*\u5e74(?!\\s*\\d{1,2}\\s*\u6708)')
_EN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
_CJK = re.compile('[\u4e00-\u9fff]')
_STOP = set('\u7684\u4e86\u5728\u662f\u548c\u4e0e\u53ca\u6216\u628a\u88ab\u5bf9\u5230\u4ece\u8fd9\u90a3\u6211\u4eec\u4f60\u4ed6\u5979\u5b83\u5c31\u4e5f\u90fd\u8fd8\u53c8\u5f88\u4e0d\u6ca1\u6709\u4e2a\u4e00\u4e86\u7740\u8fc7\u4e3a\u4ee5\u53ca\u4ee5')


_GARBAGE = re.compile(r"<\|[^|>]*\|>")


_CN_DIGIT = {'\u96f6': 0, "〇": 0, '\u4e00': 1, '\u4e8c': 2, '\u4e24': 2, '\u4e09': 3, '\u56db': 4, '\u4e94': 5, '\u516d': 6, '\u4e03': 7, '\u516b': 8, '\u4e5d': 9}
_CN_UNIT = {'\u5341': 10, '\u767e': 100, '\u5343': 1000, '\u4e07': 10000, '\u4ebf': 100000000}
_CN_NUM = re.compile('[\u96f6\u3007\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343]{1,8}')
_CN_MONTH = re.compile('(?<!\\d)([\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]{1,2})\\s*\u6708')
_CN_HARD_UNITS = '\u53f0|\u5143|\u7f8e\u5143|\u7f8e\u91d1|\u5757\u94b1|\u4e07|\u4ebf|\u5929|\u5468|\u4e2a\u6708|\u5c0f\u65f6|\u5206\u949f|\u4eba|\u516c\u91cc|\u5428|\u5ea6|\u6b21|\u6761|\u5957|\u5f20|\u4efd'

_CN_QTY = re.compile(f'(?<![\u7edf\u552f\u5355\u540c\u7b2c\u6bcf])([\u96f6\u3007\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343]{{1,8}})\\s*({_CN_HARD_UNITS})(?![\u4e00-\u9fff]?[\u6708\u65e5])')


def cn_to_int(s: str) -> int | None:
    if not s or not _CN_NUM.fullmatch(s):
        return None
    total, cur = 0, 0
    for ch in s:
        if ch in _CN_DIGIT:
            cur = _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            unit = _CN_UNIT[ch]
            if unit >= 10000:
                total = (total + cur) * unit
            else:
                total += (cur if cur else 1) * unit
            cur = 0
        else:
            return None
    return total + cur


def cn_month_to_digits(text: str) -> str:
    def _m(m):
        n = cn_to_int(m.group(1))
        return f'{n}\u6708' if n and 1 <= n <= 12 else m.group(0)
    return _CN_MONTH.sub(_m, text or "")


def _cn_numerals_to_digits(text: str) -> str:
    text = cn_month_to_digits(text)

    def _q(m):
        n = cn_to_int(m.group(1))
        return f"{n}{m.group(2)}" if n is not None else m.group(0)
    return _CN_QTY.sub(_q, text)


def extract_values(text: str) -> dict:
    text = _cn_numerals_to_digits(_GARBAGE.sub(" ", text or ""))
    nums: list[tuple[float, str]] = []
    for v, u in _NUM.findall(text):
        u = _UNIT_CANON.get(u.lower(), u)
        nums.append((float(v), _UNIT_ALIAS.get(u, u)))
    dates: list[str] = []
    for y, m, d in _DATE_FULL.findall(text):
        dates.append(f"{int(y)}-{int(m)}-{int(d)}")
    stripped = _DATE_FULL.sub(" ", text)
    for m, d in _DATE_MD.findall(stripped):
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            dates.append(f"{int(m)}-{int(d)}")
    stripped = _DATE_MD.sub(" ", stripped)
    for y, m in _DATE_YM.findall(stripped):
        if 1 <= int(m) <= 12:
            dates.append(f"{int(y)}-{int(m)}")
    stripped = _DATE_YM.sub(" ", stripped)
    for m in _DATE_M.findall(stripped):
        if 1 <= int(m) <= 12:
            dates.append(f"{int(m)}")
    for y in _DATE_Y.findall(stripped):
        dates.append(y)

    years = {float(y) for y in dates if len(y) == 4 and "-" not in y}
    nums = [(v, u) for v, u in nums if not (u == '\u5e74' and v in years)]
    return {"nums": nums, "dates": dates}


def fmt_date(d: str) -> str:
    p = d.split("-")
    if len(p) == 1:
        return f'{d}\u5e74' if len(d) == 4 else f'{d}\u6708'
    if len(p) == 2 and len(p[0]) == 4:
        return f'{p[0]}\u5e74{p[1]}\u6708'
    return d


def _terms(text: str) -> set[str]:


    from .search import _EN_STOP

    text = _GARBAGE.sub(" ", text or "")
    out = {w.lower() for w in _EN.findall(text)
           if len(w) >= 2 and w.lower() not in _EN_STOP}
    cjk = "".join(_CJK.findall(text))
    for i in range(len(cjk) - 1):
        g = cjk[i:i + 2]
        if g[0] not in _STOP and g[1] not in _STOP:
            out.add(g)
    return out


def overlap(a: str, b: str) -> float:
    ta, tb = _terms(a), _terms(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def shared_terms(a: str, b: str) -> int:
    return len(_terms(a) & _terms(b))


_ID_NUM = re.compile(r"(?<![0-9A-Za-z.])(\d{3,})(?![0-9A-Za-z])")
_YEAR_NUM = re.compile(r"^(?:19|20)\d{2}$")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _id_numbers(text: str) -> set[str]:
    t = _THOUSANDS.sub("", _GARBAGE.sub(" ", text or ""))
    return {n for n in _ID_NUM.findall(t) if not _YEAR_NUM.match(n)}


def evidence_runs(a: str, b: str, *, common=None) -> list[str]:
    from .search import _is_speaker_word

    sh = {t for t in _terms(a) & _terms(b) if not _is_speaker_word(t)}
    runs = [t for t in sh if not _CJK.search(t)]
    cjk = "".join(_CJK.findall(_GARBAGE.sub(" ", a or "")))
    spans: list[tuple[int, int]] = []
    for t in sh:
        if not _CJK.search(t):
            continue
        i = cjk.find(t)
        while i >= 0:
            spans.append((i, i + len(t)))
            i = cjk.find(t, i + 1)
    spans.sort()
    merged: list[tuple[int, int]] = []
    for s0, e0 in spans:
        if merged and s0 < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e0))
        else:
            merged.append((s0, e0))
    runs += [cjk[s0:e0] for s0, e0 in merged]
    out: list[str] = []
    for h in sorted(set(runs), key=lambda h: (-len(h), h)):
        if not any(h in o for o in out):
            out.append(h)


    out += sorted(_id_numbers(a) & _id_numbers(b))
    return [h for h in out if not common(h)] if common else out


LONG_RUN_CHARS = 5
_CJK_RUN = re.compile('^[\u4e00-\u9fff]+$')


#   |---|---:|---:|---:|


COMMON_DF_MIN = 20
COMMON_DF_RATIO = 0.06


def shared_evidence(a: str, b: str, *, common=None) -> int:
    runs = evidence_runs(a, b, common=common)
    n = len(runs)
    if n == 1 and _CJK_RUN.match(runs[0]) and len(runs[0]) >= LONG_RUN_CHARS:
        n = 2
    return n


MIN_SHARED_TERMS = 2


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def _date_keys(dates: list[str]) -> dict[str, set[str]]:
    k: dict[str, set[str]] = {"days": set(), "months": set(), "years": set(), "mo_only": set(), "yr_only": set()}
    for d in dates:
        p = d.split("-")
        if len(p) == 3:
            k["days"].add(f"{p[1]}-{p[2]}"); k["months"].add(p[1]); k["years"].add(p[0])
        elif len(p) == 2 and len(p[0]) == 4:
            k["months"].add(p[1]); k["years"].add(p[0]); k["mo_only"].add(p[1])
        elif len(p) == 2:
            k["days"].add(d); k["months"].add(p[0])
        elif len(d) == 4:
            k["years"].add(d); k["yr_only"].add(d)
        else:
            k["months"].add(d); k["mo_only"].add(d)
    return k


def _date_agreement(p: dict[str, set[str]], f: dict[str, set[str]]) -> list[str]:
    if p["days"] & f["days"]:
        return sorted(p["days"] & f["days"])
    same_month = (p["mo_only"] & f["months"]) | (f["mo_only"] & p["months"])
    if same_month:
        return [f'{m}\u6708' for m in sorted(same_month, key=int)]
    same_year = (p["yr_only"] & f["years"]) | (f["yr_only"] & p["years"])
    if same_year:
        return [f'{y}\u5e74' for y in sorted(same_year)]
    return []


CONFLICT_MIN_OVERLAP = 0.35


ACCUMULATION_MIN_SHARED = 3

MERGE_MIN_PASSAGE_OVERLAP = 0.3


def detect(passage: str, facts: list[dict], *, min_overlap: float = 0.12,
           conflict_min_overlap: float = CONFLICT_MIN_OVERLAP, common=None) -> list[dict]:
    pv = extract_values(passage)
    p_days = _date_keys(pv["dates"])["days"]

    def _same_quantity(fv: dict) -> bool:
        if any(abs(v - q) < 1e-9 and u == w for v, u in fv["nums"] for q, w in pv["nums"]):
            return True
        return bool(p_days and p_days & _date_keys(fv["dates"])["days"])

    scored = []
    for f in facts:
        text = f.get("text") or ""
        s = overlap(passage, text)
        scored.append((s, f, extract_values(text), shared_evidence(passage, text, common=common)))
    related = [(s, f, fv) for s, f, fv, n in scored
               if s >= min_overlap and (n >= MIN_SHARED_TERMS or _same_quantity(fv))]
    if not pv["nums"] and not pv["dates"]:


        m = _merge_candidate([(s, f) for s, f, _fv in related if s >= max(min_overlap, 0.3)])
        return [m] if m else []
    out: list[dict] = []


    by_unit: dict[str, list[tuple[float, dict, float, list[float]]]] = defaultdict(list)
    for s, f, fv in related:
        per_unit: dict[str, list[float]] = defaultdict(list)
        for v, u in fv["nums"]:
            per_unit[u].append(v)
        for u, vals in per_unit.items():
            by_unit[u].append((vals[-1], f, s, vals))
    for pval, unit in pv["nums"]:
        rows = by_unit.get(unit) or []
        if not rows:
            continue
        same = [r for r in rows if any(abs(x - pval) < 1e-9 for x in r[3])]
        if same:
            f = max(same, key=lambda r: r[2])[1]
            out.append({"relation": "corroborated", "unit": unit,
                        "say": f"The knowledge-base record from {f.get('date') or 'an unspecified date'} also states {_fmt(pval)}{unit}。",
                        "fact_ids": [f["id"]], "values": [_fmt(pval) + unit]})

        distinct: dict[str, dict] = {}
        ordered = sorted(rows, key=lambda r: r[1].get("date") or "")
        if ordered and len(ordered[0][3]) > 1:
            distinct.setdefault(_fmt(ordered[0][3][0]), ordered[0][1])
        for v, f, _s, _vals in ordered:
            distinct.setdefault(_fmt(v), f)
        diff = [r for r in rows if abs(r[0] - pval) >= 1e-9]
        if len(ordered) >= 2 and len(distinct) >= 2:
            chain = [f"{k}{unit}" for k in distinct] + ([f'{_fmt(pval)}{unit} (in your note)'] if _fmt(pval) not in distinct else [])
            out.append({"relation": "continuation", "unit": unit,
                        "say": 'This quantity changes: ' + " → ".join(chain),
                        "fact_ids": [f["id"] for f in distinct.values()], "values": chain})
        elif diff and not same:


            diff = [r for r in diff if r[2] >= conflict_min_overlap]
            if not diff:
                continue
            agreed = {r[1]["id"] for r in rows
                      if any(abs(x - q) < 1e-9 for x in r[3] for q, u2 in pv["nums"] if u2 == unit)}
            diff = [r for r in diff if r[1]["id"] not in agreed]
            if not diff:
                continue
            v, f, _s, _vals = max(diff, key=lambda r: r[2])
            out.append({"relation": "conflict", "unit": unit,
                        "say": f"The knowledge-base record from {f.get('date') or 'an unspecified date'} differs: the record states {_fmt(v)}{unit}, while the note states {_fmt(pval)}{unit}。",
                        "fact_ids": [f["id"]], "values": [_fmt(v) + unit, _fmt(pval) + unit]})


    seen: set[str] = set()
    deduped = []
    for r in out:
        if r["relation"] == "conflict":
            fid = r["fact_ids"][0]
            if fid in seen:
                continue
            seen.add(fid)
        deduped.append(r)
    out = deduped


    already = {fid for r in out for fid in r["fact_ids"] if r["relation"] == "corroborated"}
    if pv["dates"]:
        p_keys = _date_keys(pv["dates"])


        strong = [(s, f, fv) for s, f, fv in related
                  if fv["dates"] and shared_evidence(passage, f.get("text") or "", common=common) >= MIN_SHARED_TERMS]


        got_ok = got_bad = False

        agreed_days: set[str] = set()
        ordered_strong = sorted(strong, key=lambda r: -r[0])[:3]
        for _s, _f, _fv in ordered_strong:
            agreed_days |= p_keys["days"] & _date_keys(_fv["dates"])["days"]
        for s, f, fv in ordered_strong:
            if got_ok and got_bad:
                break
            f_keys = _date_keys(fv["dates"])
            agreed = _date_agreement(p_keys, f_keys)
            if agreed:
                if got_ok or f["id"] in already:
                    continue
                got_ok = True
                out.append({"relation": "corroborated", "unit": "date",
                            "say": f"The date matches the knowledge-base record from {f.get('date') or 'an unspecified date'} ({'、'.join(agreed)}）。",
                            "fact_ids": [f["id"]], "values": agreed})
                continue


            if got_bad or not (s >= conflict_min_overlap and p_keys["days"] and f_keys["days"]):
                continue


            mine = sorted(p_keys["days"] - f_keys["days"] - agreed_days) or sorted(p_keys["days"] - f_keys["days"]) or sorted(p_keys["days"])
            got_bad = True
            out.append({"relation": "conflict", "unit": "date",
                        "say": f"The date in the knowledge-base record from {f.get('date') or 'an unspecified date'} differs: the record states {'、'.join(sorted(f_keys['days']))}, while the note states {'、'.join(mine)}。",
                        "fact_ids": [f["id"]], "values": sorted(f_keys["days"]) + mine})


    p_units = {u for _v, u in pv["nums"]}
    extras: list[tuple[float, dict, list[str]]] = []
    for s, f, fv in related:
        if s < max(min_overlap, 0.2):
            continue
        same_unit = any(u in p_units for _v, u in fv["nums"])
        if not same_unit and shared_evidence(passage, f.get("text") or "", common=common) < ACCUMULATION_MIN_SHARED:
            continue
        missing = [_fmt(v) + u for v, u in fv["nums"] if u not in p_units]
        if not pv["dates"]:
            missing += [fmt_date(d) for d in fv["dates"]]
        if missing:
            extras.append((s, f, missing))
    if extras:
        extras.sort(key=lambda r: -r[0])
        values: list[str] = []
        for _s, _f, miss in extras[:3]:
            for m in miss:
                if m not in values:
                    values.append(m)
        out.append({"relation": "accumulation", "unit": "",
                    "say": f"The knowledge base includes {len(values)} additional conditions not stated here: {'、'.join(values[:4])}{('…' if len(values) > 4 else '')}",
                    "fact_ids": [f["id"] for _s, f, _m in extras[:3]], "values": values})


    m = _merge_candidate([(s, f) for s, f, _fv in related if s >= MERGE_MIN_PASSAGE_OVERLAP])
    if m:
        out.append(m)


    supported = any(r["relation"] in ("conflict", "continuation", "corroborated") for r in out)
    if not supported:
        out.append({"relation": "unsupported", "unit": "",
                    "why": "no_record" if not related else "no_value",
                    "say": ('No knowledge-base record supports this sentence. This does not establish that it is false.' if not related
                            else 'Related records do not contain the quantities in this passage; these numbers have no located source.'),
                    "fact_ids": [], "values": [_fmt(v) + u for v, u in pv["nums"]] + [fmt_date(d) for d in pv["dates"]]})

    seen = set()
    uniq = []
    for r in out:
        key = (r["relation"], r.get("unit"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    order = {"conflict": 0, "continuation": 1, "unsupported": 2, "accumulation": 3, "merge": 4, "corroborated": 5}
    uniq.sort(key=lambda r: order.get(r["relation"], 9))
    return uniq


# of his wife coming home to his garden.」vs「Colin's father dreams of his wife.」），


MIN_TWO_WAY = 0.55


def _merge_candidate(related: list[tuple[float, dict]], *, min_pair: float = 0.5) -> dict | None:
    best: tuple[float, dict, dict] | None = None
    for i in range(len(related)):
        for j in range(i + 1, len(related)):
            a, b = related[i][1], related[j][1]
            if a["id"] == b["id"]:
                continue
            ta, tb = a.get("text") or "", b.get("text") or ""
            if ta == tb:
                s = 1.0
            else:
                s = overlap(ta, tb)

                if s >= min_pair:
                    ta_, tb_ = _terms(ta), _terms(tb)
                    if len(ta_ & tb_) / max(len(ta_), len(tb_)) < MIN_TWO_WAY:
                        continue
            if s >= min_pair and (best is None or s > best[0]):
                best = (s, a, b)
    if not best:
        return None
    _s, a, b = best
    a, b = sorted((a, b), key=lambda f: f.get("date") or "")
    da, db = a.get("date") or 'an unspecified date', b.get("date") or 'an unspecified date'

    when = da if da == db else f'{da} and {db}'
    return {"relation": "merge", "unit": "",
            "say": f'Knowledge-base records from {when} appear to describe the same event. Merge them?',
            "fact_ids": [a["id"], b["id"]], "values": []}
