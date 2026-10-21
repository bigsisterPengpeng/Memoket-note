"""Check user completion criteria. Protect existing user text, skip user-confirmed criteria and distinguish polishing from content generation."""

from __future__ import annotations

import re
from typing import Callable

from ...database.wordcount import word_count
from ...editor import outline
from ..state import State
from ..types import Verdict
from .pick import pick_dimension


RULES: dict[str, str] = {
    'max': '(?:\u2264|<=|\u4e0d\u8d85\u8fc7|\u4e0d\u591a\u4e8e|\u5c11\u4e8e|\u63a7\u5236\u5728|\u6700\u591a|atmost|nomorethan|within|maximum(?:of)?)(\\d+)(?:\u5b57|characters?|chars?)',
    'max2': '(\\d+)(?:\u5b57(?:\u4ee5\u5185|\u4ee5\u4e0b|\u4e4b\u5185|\u5185)|(?:characters?|chars?)(?:orless|maximum))',
    'min': '(?:\u2265|>=|\u81f3\u5c11|\u4e0d\u5c11\u4e8e|\u4e0d\u4f4e\u4e8e|\u6700\u5c11|atleast|minimum(?:of)?)(\\d+)(?:\u5b57|characters?|chars?)',
    'min2': '(\\d+)(?:\u5b57(?:\u4ee5\u4e0a|\u8d77)|(?:characters?|chars?)(?:ormore|minimum))',
    'nonempty': '\u5199\u4e0b\u6765\u5c31\u7b97\u5b8c|\u5199\u4e86\u5c31\u7b97|^(?:non-?empty(?:note|body)|writeanything)$',
    'sections_en': '^(?:sections:\\s*(.+)|(.+?)\\s+each\\s+(?:have|has)\\s+(?:a\\s+)?section)$',
    'sections': '^(.+?)\u5404\u6709\u4e00\u8282',
    'sections2': '^(.+?)(?:\u5404|\u90fd)?(?:\u5355\u72ec)?(?:\u6709|\u6210)\u4e00\u8282',
    'section_split': '[\u3001\uff0c,\u548c\u4e0e\u53ca]',
    'section_lead': '^(?:\u8981|\u9700\u8981|\u5f97)',
    'conclusion': '\u7ed3\u8bba\u5728\u524d|\u5148\u8bf4\u7ed3\u8bba|\u7ed3\u8bba\u5148\u884c|\u5f00\u5934.*\u7ed3\u8bba|conclusionfirst|startwith(?:the)?conclusion|leadwith(?:the)?conclusion',
    'conclusion_head': '\u7ed3\u8bba|\u603b\u7ed3|\u6458\u8981|TL;?DR|\u4e00\u53e5\u8bdd|conclusion|summary|recommendation',
    'conclusion_open': '\u7ed3\u8bba|\u603b\u4e4b|\u4e00\u53e5\u8bdd|\u5224\u65ad\u662f|\u5efa\u8bae|^\\s*(?:conclusion|in summary|we recommend|recommendation)\\b',
    'date_want': '\u6709\u65e5\u671f|\u6709\u65f6\u95f4|\u5e26\u65e5\u671f|\u6807\u65e5\u671f|(?:has|have|include|with|show|add|and)(?:a)?dates?|dates?for(?:each|every)|(?:each|every)(?:item|bullet|paragraph)(?:is)?dated',
    'cite_want': '\u6709\u4f9d\u636e|\u6709\u51fa\u5904|\u6709\u5f15\u7528|\u4e8b\u5b9e\u652f\u6491|\u6709\u6765\u6e90|\u6709\u8bc1\u636e|\u5f15\u7528\u6216\u51fa\u5904|\u6807\u51fa\u5904|\u6ce8\u660e\u51fa\u5904|(?:has|have|include|with|show|add|and)(?:a)?(?:sources?|citations?|references?|evidence)|(?:sources?|citations?)for(?:each|every)|(?:is|are|be)?grounded|supportedbyfacts',
    'numeric_only': '\u6570\u5b57|\u6570\u636e|numeric(?:al)?(?:claims?|items?)|numbers?|data',
    'date': '\\d{1,2}\\s*[\u6708/.-]\\s*\\d{1,2}|\\d{4}\\s*[-/\u5e74]\\s*\\d{1,2}|\\d{1,2}\\s*\u6708(?:\u5e95|\u521d|\u672b|\u4e2d)?|\u4eca\u5929|\u6628\u5929|\u524d\u5929|\u660e\u5929|\u672c\u5468|\u4e0a\u5468|\u4e0b\u5468|\u5468[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5\u5929]|\u661f\u671f[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5\u5929]|Q[1-4]\\b|\\d+\\s*\u53f7|\\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\\s+\\d{1,2}(?:,\\s*\\d{4})?\\b|\\b(?:today|yesterday|tomorrow|this week|last week|next week|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\\b',
    'link': '\\[[^\\]\\n]*\\]\\([^)\\s]+\\)|https?://\\S+',
    'cite': '\\[((?:[A-Za-z][A-Za-z0-9_-]*-(?:\\d+|[0-9a-f]{12,64})-[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9_-]*-manualF[1-9]\\d*))\\]',
    'note_link': '\\]\\(note://([0-9a-f]{12})\\)',
    'item': '^\\s*(?:[-*+]|\\d+[.)])\\s+\\S',
    'item_strip': '^\\s*(?:[-*+]|\\d+[.)])\\s+(?:\\[[ xX]\\]\\s*)?',
    'fence': '^\\s*(`{3,}|~{3,})',
    'split': '[\uff1b;\u3002\\n]+|\\.(?=\\s+[A-Z])',
}

WHY: dict[str, str] = {
    "max_ok": 'Now {words} chars',
    "max_over": 'Now {words} chars, {over} over',
    "min_ok": 'Now {words} chars',
    "min_short": 'Now {words} chars, {short} short',
    "nonempty_ok": '{words} chars written',
    "nonempty_no": 'The note is still empty',
    "sections_missing": 'Missing headings: {missing}',
    "sections_ok": 'All {n} sections present',
    "conclusion_ok": 'Opens with the conclusion',
    "conclusion_no": 'No conclusion at the start',
    "no_units": 'No items in the note yet',
    "no_numbers": 'No numbers in the note',
    "date_miss": '{miss} of {n} {unit} have no date',
    "date_ok": 'All {n} {unit} have a date',
    "cite_miss": '{miss} of {n} {unit} have no source',
    "cite_ok": 'All {n} {unit} have a source',
}
_IGNORE_CASE = ['cite_want', 'conclusion', 'conclusion_head', 'conclusion_open', 'date', 'date_want', 'max', 'max2', 'min', 'min2', 'nonempty', 'numeric_only', 'sections_en']
_R = {k: re.compile(v, re.I if k in _IGNORE_CASE else 0) for k, v in RULES.items()}
_HEAD_I = re.compile(RULES["conclusion_head"], re.I)
_FULLWIDTH = {ord(c): str(i) for i, c in enumerate("０１２３４５６７８９")}
PARA_MIN = 20


DATE_PENDING = '(date pending)'
_DATE_PENDING = re.compile('[\uff08(]\\s*(?:\u65e5\u671f\u5f85\u8865|date\\s+pending)\\s*[\uff09)]', re.I)


def has_date_pending(s: str) -> bool:
    return bool(_DATE_PENDING.search(s or ""))


def split_done(done: str) -> list[str]:
    return [s.strip() for s in _R["split"].split(done or "") if s.strip()]


def units(content: str) -> tuple[str, list[str]]:
    lines = (content or "").split("\n")
    items: list[str] = []
    paras: list[str] = []
    fenced = False
    cur: list[str] = []
    last_item = -1

    def flush() -> None:
        nonlocal cur
        if cur:
            paras.append("\n".join(cur))
            cur = []

    for line in lines:
        if _R["fence"].match(line):
            fenced = not fenced
            flush()
            continue
        if fenced:
            continue
        is_head = bool(re.match(r"^#{1,6}\s", line))
        if not line.strip() or is_head:
            flush()
            if is_head:
                last_item = -1
            continue
        if _R["item"].search(line):
            items.append(_R["item_strip"].sub("", line, count=1))
            last_item = len(items) - 1
        elif last_item >= 0:
            items[last_item] += "\n" + line
        cur.append(line)
    flush()
    if items:
        return "item", items
    return "paragraph", [p for p in paras if len(re.sub(r"\s", "", p)) >= PARA_MIN]


def _has_cite(s: str) -> bool:
    return bool(_R["cite"].search(s) or _R["note_link"].search(s) or _R["link"].search(s))


def _headings(content: str) -> list[str]:
    return [t for _, t in outline.headings(content or "")]


def _opening(content: str) -> str:
    lines = [l for l in (content or "").split("\n") if l.strip() and not re.match(r"^#{1,6}\s", l)]
    return "\n".join(lines[:2])


def check_done_item(item: str, content: str, *,
                    unit_filter: Callable[[str], bool] | None = None,
                    date_pending_ok: bool = False) -> dict | None:

    # English template criteria retain spaces in heading names (the compact CJK path below does not).
    english_sections = _R["sections_en"].search((item or "").strip())
    if english_sections:
        listed = english_sections.group(1) or english_sections.group(2)
        parts = re.split(r",|\band\b", listed, flags=re.I) if english_sections.group(2) else listed.split(",")
        names = [name.strip() for name in parts if name.strip()]
        heads = [re.sub(r"\s+", "", h).casefold() for h in _headings(content)]
        missing = [n for n in names if not any(re.sub(r"\s+", "", n).casefold() in h for h in heads)]
        return ({"kind": "sections", "status": "fail", "why": WHY["sections_missing"].format(missing=", ".join(missing)), "missing": missing}
                if missing else {"kind": "sections", "status": "pass", "why": WHY["sections_ok"].format(n=len(names))})
    t = re.sub(r"\s+", "", item or "").translate(_FULLWIDTH)
    words = word_count(content or "")
    m = _R["max"].search(t) or _R["max2"].search(t)
    if m:
        n = int(m.group(1))
        return ({"kind": "max", "status": "pass", "why": WHY["max_ok"].format(words=words)} if words <= n
                else {"kind": "max", "status": "fail", "why": WHY["max_over"].format(words=words, over=words - n), "n": n})
    m = _R["min"].search(t) or _R["min2"].search(t)
    if m:
        n = int(m.group(1))
        return ({"kind": "min", "status": "pass", "why": WHY["min_ok"].format(words=words)} if words >= n
                else {"kind": "min", "status": "fail", "why": WHY["min_short"].format(words=words, short=n - words), "n": n})
    if _R["nonempty"].search(t):
        return ({"kind": "nonempty", "status": "pass", "why": WHY["nonempty_ok"].format(words=words)} if words > 0
                else {"kind": "nonempty", "status": "fail", "why": WHY["nonempty_no"]})
    m = _R["sections"].search(t) or _R["sections2"].search(t)
    if m:
        names = [_R["section_lead"].sub("", s).strip() for s in _R["section_split"].split(m.group(1))]
        names = [s for s in names if s and len(s) <= 8]
        if names:
            heads = _headings(content)
            missing = [n for n in names if not any(n in h for h in heads)]
            return ({"kind": "sections", "status": "fail", "why": WHY["sections_missing"].format(missing=', '.join(missing)), "missing": missing}
                    if missing else {"kind": "sections", "status": "pass", "why": WHY["sections_ok"].format(n=len(names))})
    if _R["conclusion"].search(t):
        heads = _headings(content)
        first_head = heads[0] if heads else ""
        ok = bool(_HEAD_I.search(first_head) or _R["conclusion_open"].search(_opening(content)))
        return ({"kind": "conclusion", "status": "pass", "why": WHY["conclusion_ok"]} if ok
                else {"kind": "conclusion", "status": "fail", "why": WHY["conclusion_no"]})
    want_date = bool(_R["date_want"].search(t))
    want_cite = bool(_R["cite_want"].search(t))
    if want_date or want_cite:
        kind, texts = units(content)
        unit = 'items' if kind == "item" else 'paragraphs'
        if not texts:
            return {"kind": "cite" if want_cite else "date", "status": "fail", "why": WHY["no_units"]}
        scope = [s for s in texts if re.search(r"\d", s)] if (_R["numeric_only"].search(t) and want_cite) else texts
        if unit_filter is not None:
            scope = [s for s in scope if unit_filter(s)]
            if not scope:
                return None
        if not scope:
            return {"kind": "cite", "status": "pass", "why": WHY["no_numbers"]}
        parts: list[str] = []
        bad_date: list[str] = []
        bad_cite: list[str] = []
        if want_date:
            bad_date = [s for s in scope
                        if not _R["date"].search(s) and not (date_pending_ok and has_date_pending(s))]
            parts.append(WHY["date_miss"].format(n=len(scope), unit=unit, miss=len(bad_date)) if bad_date
                         else WHY["date_ok"].format(n=len(scope), unit=unit))
        if want_cite:
            bad_cite = [s for s in scope if not _has_cite(s)]
            parts.append(WHY["cite_miss"].format(n=len(scope), unit=unit, miss=len(bad_cite)) if bad_cite
                         else WHY["cite_ok"].format(n=len(scope), unit=unit))
        fail = bool(bad_date or bad_cite)

        kind_out = "date" if bad_date else "cite" if bad_cite else ("cite" if want_cite else "date")
        return {"kind": kind_out, "status": "fail" if fail else "pass", "why": '; '.join(parts),
                "bad": bad_date or bad_cite, "unit": unit}
    return None


def check_done(done: str, content: str, checked: list[str] | tuple[str, ...] = ()) -> list[dict]:
    out = []
    for text in split_done(done):
        r = check_done_item(text, content)
        if r:
            out.append({"text": text, "status": r["status"], "why": r["why"], "checked": False})
        else:
            out.append({"text": text, "status": "manual", "why": "", "checked": text in checked})
    return out


_NEEDS_WRITING = {"min", "sections", "nonempty"}


def judgeable(done: str, checked: tuple[str, ...] = (), *, polish: bool = False) -> list[str]:
    out = []
    for text in split_done(done):
        if text in checked:
            continue
        r = check_done_item(text, "")
        if r is None:
            continue
        if polish and r["kind"] in _NEEDS_WRITING:
            continue
        out.append(text)
    return out


def _dimension(st: State, kind: str) -> str:
    if kind in ("cite", "date"):
        return pick_dimension(st, "factual_grounding", "no_fabrication", "data_grounding")
    if kind in ("max", "conclusion"):
        return pick_dimension(st, "fits_context")
    return pick_dimension(st, "beat_coverage", "section_coverage", "material_use")


def _locate(bad: list[str], content: str, unit: str) -> list[str]:
    out: list[str] = []
    paras = [p for p in re.split(r"\n\s*\n", content or "") if p.strip()]
    for b in bad[:3]:
        head = b.strip().splitlines()[0]
        n = 0
        for i, para in enumerate(paras, start=1):
            if head[:20] and head[:20] in para:
                n = i
                break
        where = f'Paragraph {n}' if n else 'This item'
        out.append(f'''{where} "{head[:30]}{('…' if len(head) > 30 else '')}"''')
    return out


def mark_date_pending(content: str, bad: list[str]) -> str:
    lines = (content or "").split("\n")
    for b in bad:
        body = [l for l in (b or "").splitlines() if l.strip()]
        if not body:
            continue
        target = body[-1].strip()
        for i, line in enumerate(lines):
            if not line.strip().endswith(target):
                continue
            if has_date_pending(line) or _R["date"].search(line):
                continue
            lines[i] = line.rstrip() + " " + DATE_PENDING
            break
    return "\n".join(lines)


def _hint(r: dict, content: str = "") -> str:
    kind = r["kind"]
    unit = r.get("unit", 'paragraphs')
    if kind == "cite":
        where = '; '.join(_locate(r.get("bad", []), content, unit))


        return (f'Missing sources: {where}. For each item, append a fact ID copied exactly from supporting material. If no material supports the claim, state which record is needed instead. Do not invent identifiers or leave unsupported claims unchanged.')
    if kind == "date":
        where = '; '.join(_locate(r.get("bad", []), content, unit))
        return (f'Missing dates: {where}. Name a date explicitly supported by the material, for example "April 16: EVT review". If the material has no date, append "(date pending)". Do not invent dates or leave a missing date unacknowledged.')
    if kind == "max":
        return f"Reduce the body to at most {r.get('n')} characters. Remove repetition and unnecessary setup before removing supported statements."
    if kind == "min":
        return f"Continue an uncovered aspect until the body reaches {r.get('n')} characters without padding or repetition."
    if kind == "sections":
        return 'Add headings and body text for these sections: ' + ', '.join(r.get("missing", [])) + '. '
    if kind == "conclusion":
        return 'Put the conclusion in the opening paragraph or first heading; move background later.'
    return 'Write the body first.'


def done_criteria(st: State) -> Verdict | None:
    from ...editor import intent as doc_intent
    done = doc_intent.done_of(st.ctx.intent)
    if not done:
        return None
    checked = tuple(getattr(st.ctx, "intent_checked", ()) or ())
    polish = bool(st.bag.get("polish"))
    start = str(st.bag.get("content_at_start") or "")


    from .grounding_rules import abstention_lines
    fresh_only = (lambda s: s.strip() not in start and not abstention_lines(s)) if start else None
    for text in judgeable(done, checked, polish=polish):
        r = check_done_item(text, st.content, unit_filter=fresh_only, date_pending_ok=True)
        if not r or r["status"] != "fail":
            continue
        scope = 'newly written ' if (fresh_only and r["kind"] in ("cite", "date")) else ""


        streak = int((st.bag.get("check_name_streak_prev") or {}).get("done_criteria", 0)) + 1
        again = ('The previous round raised this issue and it is still unresolved. Fix it before adding new passages: '
                 if streak >= 2 else "")


        fixer = fix_checker = None
        fix_note = ""
        if r["kind"] == "date" and streak >= 2 and r.get("bad"):
            bad = list(r["bad"])
            fix_note = (f'Added (date pending) to {len(bad)} lines still missing a date. The harness added this marker; replace it with a sourced date when available.')

            def mark_missing_dates(c: str, _bad: list[str] = bad) -> str:
                return mark_date_pending(c, _bad)

            def date_requirement_resolved(c: str, _text: str = text) -> bool:
                rr = check_done_item(_text, c, unit_filter=fresh_only, date_pending_ok=True)
                return not rr or rr["status"] != "fail" or rr["kind"] != "date"

            fixer, fix_checker = mark_missing_dates, date_requirement_resolved

        return Verdict(
            dimension=_dimension(st, r["kind"]),
            message=f'''Your completion criterion "{text}" is not met: {scope}{r['why']}. {again}{_hint(r, st.content)}''',
            fix=fixer,
            fix_done=fix_checker,
            fix_note=fix_note,
        )
    return None
