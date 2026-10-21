"""Language patterns used to identify unsupported placeholders, process commentary and missing-evidence stand-ins."""

from __future__ import annotations

import re


LEAK_PHRASES = ('\u77e5\u8bc6\u5e93', "KB", '\u68c0\u7d22\u5230\u7684\u8bb0\u5f55', '\u53ef\u6838\u5bf9\u7684\u8bb0\u5f55', '\u53ef\u6838\u5bf9\u7684\u4e8b\u5b9e')
AUDIT_PHRASES = ('\u4e0d\u80fd\u8bc1\u660e', '\u65e0\u6cd5\u8bc1\u660e', '\u4e0d\u80fd\u636e\u6b64', '\u4e0d\u8db3\u4ee5\u8bf4\u660e', '\u4ecd\u9700\u4e0e',
                 '\u9010\u9879\u6838\u5bf9', '\u5f85\u6838\u5bf9', '\u5f85\u8865\u8bc1\u636e', '\u65e0\u6cd5\u5224\u65ad', '\u5c1a\u65e0\u6cd5\u5224\u65ad',
                 '\u4e0d\u80fd\u636e\u4ee5', '\u65e0\u4ece\u5224\u65ad', '\u96be\u4ee5\u8bc1\u5b9e')


REWRITE_PHRASES = (
    '\u5e94\u6539\u4e3a[\uff1a:]', '\u4e0d\u80fd\u5728\u6b63\u6587\u4e2d\u5199\u6210', '\u66f4\u51c6\u786e\u7684\u5199\u6cd5\u662f',
    '\u4e0d\u5e94\u628a[^\u3002\uff01\uff1f\\n]{0,40}\u5199\u6210\u5df2\u7ecf', '\u5e94\u628a[^\u3002\uff01\uff1f\\n]{0,12}\u5199\u6210\u62df\u8bae', '\u4e0d\u5b9c\u76f4\u63a5\u5199\u6210',
    '\u6700\u591a\u53ef\u4ee5\u5199\u6210', '\u4e0d\u80fd\u4ec5\u51ed[^\u3002\uff01\uff1f\\n]{0,16}(?:\u63a8\u65ad|\u5224\u65ad)',
    '\u4e0d\u80fd\u7ee7\u7eed\u4f5c\u4e3a[^\u3002\uff01\uff1f\\n]{0,12}\u4fdd\u7559', '\u5e94\u660e\u786e\u6807\u6ce8\u4e3a\u5f85\u8865\u5145',
    '\u5c31\u73b0\u6709\u6750\u6599\u800c\u8a00', '\u7ed9\u5b9a\u7684?(?:\u8bbf\u8c08\u7247\u6bb5|\u6750\u6599|\u77e5\u8bc6\u5e93)',
)


_MECHANISM = re.compile("|".join(
    "(?<![A-Za-z])KB(?![A-Za-z])" if w == "KB" else re.escape(w) for w in LEAK_PHRASES))
_AUDIT_VOICE = re.compile("|".join(re.escape(w) for w in AUDIT_PHRASES)
                          + '|\u7f3a\u5c11.{0,12}\u8bb0\u5f55\uff0c\u56e0\u6b64')
_REWRITE_NOTE = re.compile("|".join(REWRITE_PHRASES))

_META_SENT = re.compile(_MECHANISM.pattern + "|" + _AUDIT_VOICE.pattern
                        + "|" + _REWRITE_NOTE.pattern)


_META_PREFIX = re.compile(r"^(?:\[[^\]]{1,40}\]\s*)+")
_META_SUFFIX = re.compile(r"（[^）]{0,60}）\s*$")


_STOP = set('\u7684\u4e86\u548c\u4e0e\u53ca\u6216\u5bf9\u4e8e\u5173\u4e8e\u8fd9\u4e2a\u90a3\u4e2a\u53ef\u4ee5\u9700\u8981\u6211\u4eec\u4ed6\u4eec\u4ec0\u4e48\u600e\u4e48\u4ee5\u53ca\u4e00\u4e2a\u8fdb\u884c\u95ee\u9898\u65f6\u95f4\u65b9\u5f0f\u65b9\u6cd5\u5185\u5bb9\u60c5\u51b5\u5730\u65b9\u4e1c\u897f\u90e8\u5206\u5f00\u59cb\u7ed3\u675f\u73b0\u5728\u5df2\u7ecf\u8fd8\u6709\u5c31\u662f\u4e0d\u662f')


def _terms(text: str) -> set[str]:
    out = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)}
    out |= set(re.findall(r"\d[\d.,%]*", text))
    for seg in re.findall('[\u4e00-\u9fff]{2,}', text):
        out |= {seg[i:i + 2] for i in range(len(seg) - 1)}
    return out - _STOP


def _fact_body(fact: str) -> str:
    return _META_SUFFIX.sub("", _META_PREFIX.sub("", fact)).strip()


def fact_usage(content: str, facts: list[str], *, min_overlap: int = 3) -> tuple[int, list[str]]:
    if not facts or not content.strip():
        return 0, []
    body = _terms(content)
    used = []
    for f in facts:
        ft = _terms(_fact_body(f))
        if not ft:
            continue
        if len(ft & body) >= min_overlap:
            used.append(f)
    return len(used), used


def grounding_gap(content: str, facts: list[str]) -> str:
    if not facts:
        return ""
    n, _used = fact_usage(content, facts)
    if n:
        return ""
    preview = "；".join(_fact_body(f)[:40] for f in facts[:3])
    return (f'This round retrieved {len(facts)} records, but the body uses none of them and contains only generic content. Retrieved material: {preview}. Incorporate specific supported projects, numbers and decisions belonging to the user rather than expanding general knowledge.')


def material_exhausted(content: str, facts: list[str], *, min_facts: int = 2) -> bool:
    if len(facts) < min_facts:
        return False
    used, _ = fact_usage(content, facts)
    return used == len(facts)


_STAND_IN = '\u5f85\u6307\u5b9a|\u5f85\u5012\u6392|\u5f85\u8865\u5145|\u5f85\u786e\u8ba4|\u5f85\u660e\u786e|\u5f85\u5b9a|\u5f85\u586b|\u5f85\u8865'
_END = r"(?=$|[\s|。，、；：！？,;:!?)）\]】》」』])"
_PLACEHOLDER = re.compile(f"(?:{_STAND_IN}){_END}" + '|TBD|\uff08\u5f85[^\uff09]{0,8}\uff09|_{3,}|\\bXX\\b|X{3,}|\u8fd9(?:\u91cc|\u4e00(?:\u8282|\u5757|\u6bb5))\u9700\u8981\u8865[\u4e0a\u9f50\u5168]?[^\u3002\uff01\uff1f\\n]{0,32}(?:\u8bb0\u5f55|\u6750\u6599|\u6570\u636e|\u7eaa\u8981)')


_QUOTED = re.compile(r"[「『“\"']([^」』”\"'\n]{1,8})[」』”\"']")


def placeholder_lines(content: str, *, limit: int = 6) -> list[str]:
    out = []
    fenced = False
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if s and _PLACEHOLDER.search(_QUOTED.sub("　", s)):
            out.append(s[:160])
            if len(out) >= limit:
                break
    return out


def _seen(before: str):
    if not (before or "").strip():
        return lambda _s: False
    return lambda s: s in before


def audit_voice_lines(content: str, *, limit: int = 5,
                      before: str = "") -> list[str]:
    seen = _seen(before)
    out = []
    for sent in re.split(r"(?<=[。！？\n])", content):
        s = sent.strip()


        if s and _META_SENT.search(s) and not seen(s):
            out.append(s[:160])
            if len(out) >= limit:
                break
    return out


def meta_sentences(text: str, before: str = "") -> list[str]:
    return audit_voice_lines(text, limit=10_000, before=before)


_BOLD_PUNCT = re.compile('(?<![\\w\u4e00-\u9fff])\\*\\*([^*\\n]+?)([\uff1a:\uff0c,\u3002\uff1b;\uff01!\uff1f?\u3001\uff09)])\\*\\*')


def fix_bold_punct(md: str) -> str:
    out: list[str] = []
    fenced = False
    for line in md.split("\n"):
        if re.match(r"^\s*(`{3,}|~{3,})", line):
            fenced = not fenced
            out.append(line)
            continue
        out.append(line if fenced else _BOLD_PUNCT.sub(r"**\1**\2", line))
    return "\n".join(out)


def scrub_meta_sentences(content: str, before: str = "") -> str:
    return fix_bold_punct(scrub_meta_sentences_v(content, before)[0])


def scrub_meta_sentences_v(content: str, before: str = "") -> tuple[str, list[str]]:
    if not content or not _META_SENT.search(content):
        return content, []
    seen = _seen(before)
    removed: list[str] = []
    out = []
    for para in re.split(r"(\n\s*\n)", content):
        if para.strip().startswith(("|", "```", "#")) or "\n" in para.strip()[:0]:
            out.append(para)
            continue
        if not _META_SENT.search(para):
            out.append(para)
            continue
        kept = []
        for x in re.split(r"(?<=[。！？])", para):
            if not x:
                continue
            bad = bool(_META_SENT.search(x)) and not seen(x)
            (removed if bad else kept).append(x.strip() or x)
        out.append("".join(k if k in para else k for k in kept))
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip(), removed


_ABSTAIN = re.compile(
    '\u9700\u8981\u8865[\u4e0a\u9f50\u5168]?[^\u3002\uff01\uff1f\\n]{0,24}(?:\u8bb0\u5f55|\u6750\u6599|\u6570\u636e|\u7eaa\u8981)|(?:\u8865\u4e0a|\u8865\u9f50)[^\u3002\uff01\uff1f\\n]{0,24}(?:\u7684\u5b9e\u9645\u8bb0\u5f55|\u7684\u8bb0\u5f55)|\u8fd9(?:\u91cc|\u4e00(?:\u8282|\u5757|\u6bb5))[^\u3002\uff01\uff1f\\n]{0,16}(?:\u8fd8)?\u6ca1\u6709[^\u3002\uff01\uff1f\\n]{0,12}\u8bb0\u5f55')


def abstention_lines(content: str, *, limit: int = 3) -> list[str]:
    out = []
    for sent in re.split(r"(?<=[。！？\n])", content or ""):
        s = sent.strip()
        if s and _ABSTAIN.search(s):
            out.append(s[:160])
            if len(out) >= limit:
                break
    return out
