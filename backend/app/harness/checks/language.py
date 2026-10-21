"""Detect malformed language artifacts and repetitive phrasing in newly generated text."""

from __future__ import annotations

import re

from ..state import State
from ..types import Verdict
from .pick import pick_dimension

MIN_LETTERS = 40
ZH, EN = "zh", "en"

_CJK = re.compile('[\u4e00-\u9fff\u3400-\u4dbf]')
_LATIN = re.compile(r"[A-Za-z]")
_CITE_OR_CODE = re.compile(r"\[[A-Za-z0-9_\-]+\]|```.*?```|`[^`\n]*`|https?://\S+", re.S)


def main_language(text: str, *, min_letters: int | None = None) -> str:
    body = _CITE_OR_CODE.sub(" ", text or "")
    cjk = len(_CJK.findall(body))
    latin = len(_LATIN.findall(body))

    zh_w, en_w = cjk, latin / 4

    if zh_w + en_w < (MIN_LETTERS if min_letters is None else min_letters):
        return ""
    return ZH if zh_w >= en_w else EN


def _fresh_text(content: str, before: str) -> str:
    if not (before or "").strip():
        return ""
    return "\n\n".join(p for p in re.split(r"\n\s*\n", content or "")
                       if p.strip() and p.strip() not in before)


def language_consistent(st: State) -> Verdict | None:
    before = str(st.bag.get("content_at_start") or "")
    lang = st.bag.get("body_lang") or main_language(before)
    if not lang:
        return None
    fresh = _fresh_text(st.content, before)
    got = main_language(fresh)
    if not got or got == lang:
        return None
    want = 'English' if lang == EN else 'Chinese'
    return Verdict(
        pick_dimension(st, "style_fit", "fits_context"),
        f"The user's body is in {want}, but this round's new content is in {('Chinese' if got == ZH else 'English')}. Continue and revise in {want}. Paraphrase material from other languages into {want} before incorporating it.",
    )


def switched(text: str, body_lang: str) -> str:
    if not body_lang:
        return ""
    got = main_language(text)
    if not got or got == body_lang:
        return ""
    want = 'English' if body_lang == EN else 'Chinese'
    return f"The body is in {want}, but this revision is in {('Chinese' if got == ZH else 'English')}"


_COMMON = re.compile(
    '[\\x00-\\x7F\xa0-\u024f\u0370-\u03ff\u0400-\u04ff\u2000-\u206f\u2070-\u209f\u20a0-\u20cf\u2100-\u214f\u2190-\u21ff\u2200-\u22ff\u2300-\u23ff\u2460-\u24ff\u2500-\u27bf\u2900-\u2bff\u2e80-\u2eff\u3000-\u303f\u3040-\u30ff\u3100-\u312f\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef\\U0001F000-\\U0001FAFF\\U00020000-\\U0002FA1F\ufe00-\ufe0f\u200b-\u200d\u2028-\u2029]')


def _block(ch: str) -> str:
    import unicodedata
    try:
        return unicodedata.name(ch).split()[0]
    except ValueError:
        return "UNKNOWN"


def scripts_in(text: str) -> set[str]:
    return {_block(ch) for ch in (text or "") if not _COMMON.match(ch)}


def foreign_runs(text: str, allowed: set[str]) -> list[str]:
    out: list[str] = []
    cur = ""
    for ch in (text or "") + " ":
        if not _COMMON.match(ch) and _block(ch) not in allowed:
            cur += ch
            continue
        if cur and cur not in out:
            out.append(cur)
        cur = ""
    return out


def strip_foreign(text: str, allowed: set[str]) -> str:
    out = "".join(ch for ch in (text or "")
                  if _COMMON.match(ch) or _block(ch) in allowed)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return re.sub(r"[ \t]+(?=\n|$)", "", out)


JUNK_WORDS = ('\u4e00\u672c\u9053', '\u505a\u7230\u7247')


_TAIL = re.compile(r"[。！？!?…」』）)\]][ \t\u3000]*([\u4e00-\u9fff]{2,12})[\s。．.]*$")


def _grams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)}


def junk_tails(text: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text or ""):
        para = para.rstrip()
        m = _TAIL.search(para)
        if not m:
            continue
        tail = m.group(1)
        if not any(w in tail for w in JUNK_WORDS):
            continue
        rest = para[:m.start(1)]
        if any(g in rest for g in _grams(tail)):
            continue
        if tail not in out:
            out.append(tail)
    return out


def strip_junk_tails(text: str, tails: list[str]) -> str:
    out = text or ""
    for t in tails:
        out = re.sub(r"[ \t\u3000]*" + re.escape(t) + r"(?=[\s。．.]*(?:\n|$))", "", out)
    return out


def no_junk_tail(st: State) -> Verdict | None:
    before = str(st.bag.get("content_at_start") or "")


    fresh = _fresh_text(st.content, before) if before.strip() else st.content
    tails = junk_tails(fresh)
    if not tails:
        return None
    return Verdict(

        pick_dimension(st, "fits_context"),
        f"Removed unrelated model-generated text appended to paragraph endings: {'、'.join(tails[:3])}. It does not belong to the note.",
        fix=lambda text: strip_junk_tails(text, junk_tails(_fresh_text(text, before) if before.strip() else text)),


        fix_note=f'Removed {len(tails)} unrelated model-generated paragraph endings.',
    )


def no_foreign_script(st: State) -> Verdict | None:
    before = str(st.bag.get("content_at_start") or "")
    allowed = scripts_in(before) | scripts_in("\n".join(st.facts or []))
    fresh = _fresh_text(st.content, before) if before.strip() else st.content
    runs = foreign_runs(fresh, allowed)
    if not runs:
        return None
    return Verdict(


        pick_dimension(st, "fits_context"),
        f"Removed model-generated characters outside the note's writing system: {'、'.join((r[:12] for r in runs[:3]))}. They do not belong to the note.",
        fix=lambda text: strip_foreign(text, allowed),


        fix_note=(f"Removed {len(runs)} runs of characters outside the note's writing system ({'、'.join((r[:8] for r in runs[:3]))}); all other text was preserved."),
    )
