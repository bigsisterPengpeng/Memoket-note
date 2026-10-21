"""Locate and apply bounded edits while protecting pre-run user text, unique anchors and sentence boundaries."""

from __future__ import annotations

import difflib
import re


_REWRITE_SAME = 0.62


_BROKEN = re.compile(r"[：:，,。.；;！!？?]\s*[、，,；;。.]"
                     r"|(?:^|\n)\s*[、，,；;]"
                     r"|[，、]\s*(?:\n\n|$)")


def tidy_blank_lines(content: str) -> str:
    out: list[str] = []
    in_fence = False
    blanks = 0
    for line in content.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            blanks += 1
            if blanks > 1:
                continue
        else:
            blanks = 0
        out.append(line.rstrip() if not in_fence else line)
    return "\n".join(out)


_LINK = re.compile(r"\[[^\]\n]+\]\([^)\s]+\)")
_LINK_URL = re.compile(r"\]\([^)\s]+\)|note://[0-9a-f]{12}|https?://")


def _dangling_links(text: str) -> int:
    return len(_LINK_URL.findall(text)) - len(_LINK.findall(text))


def breakage(before: str, after: str) -> str:
    was = len(_BROKEN.findall(before))
    now = _BROKEN.findall(after)
    if len(now) > was:
        return "".join(now[-1].split())
    if _dangling_links(after) > _dangling_links(before):
        return 'incomplete link'
    return ""


def _locate(content: str, anchor: str, anchor_end: str) -> tuple[int, int]:
    i = content.find(anchor)
    if i < 0:
        return -1, -1
    if not anchor_end:
        return i, i + len(anchor)
    first, best = i, (-1, -1)
    while i >= 0:
        j = content.find(anchor_end, i + len(anchor))
        if j >= 0:
            end = j + len(anchor_end)
            if best[0] < 0 or end - i < best[1] - best[0]:
                best = (i, end)
        i = content.find(anchor, i + 1)


    return best if best[0] >= 0 else (first, first + len(anchor))


def _span_missing(content: str, anchor: str, anchor_end: str) -> bool:
    if not anchor_end:
        return False
    i = content.find(anchor)
    while i >= 0:
        if content.find(anchor_end, i + len(anchor)) >= 0:
            return False
        i = content.find(anchor, i + 1)
    return True


def _replaced_span(content: str, anchor: str, anchor_end: str) -> str:
    i, j = _locate(content, anchor, anchor_end)
    return content[i:j] if i >= 0 else ""


def _is_same_meaning_rewrite(old: str, new: str) -> bool:
    old, new = old.strip(), new.strip()
    if not old or not new or len(old) < 24:
        return False
    return difflib.SequenceMatcher(None, old, new).ratio() > _REWRITE_SAME


_CORE_STRIP = re.compile(r"[\s#*_`>|\-\d\.,;:!?，。；：！？、（）()\[\]【】「」『』“”‘’\"']+")


def _core(s: str) -> str:
    return _CORE_STRIP.sub("", s or "").lower()


def _pieces(span: str) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for para in re.split(r"\n\s*\n", span or ""):
        p = para.strip()
        if len(p) >= 4:
            out.append((p, True))
        for sent in re.split(r"(?<=[。！？!?\n])", p):
            t = sent.strip()
            if len(t) >= 4 and t != p:
                out.append((t, False))
    return out


def _is_mechanical(old: str, new: str) -> bool:
    return _core(old) == _core(new) and _core(old) != ""


def user_text_touched(content: str, op: str, anchor: str, text: str,
                      anchor_end: str = "", before: str = "") -> str:
    if op not in ("replace", "delete") or not (before or "").strip():
        return ""
    span = _replaced_span(content, anchor, anchor_end)
    if not span.strip():
        return ""


    whole = "\n" in span.strip() or any(p == span.strip() for p, _ in _pieces(span))
    touched = [p for p, is_para in [(span.strip(), whole), *_pieces(span)]
               if p in before and (not is_para or content.count(p) <= before.count(p))]
    if not touched:
        return ""
    if op == "replace" and _is_mechanical(span, text):
        return ""
    key = " ".join(touched[0].split())[:24]
    return (f"Blocked an attempt to {('delete ' if op == 'delete' else 'rewrite ')} content written before this run. Continuation may add text but must preserve existing wording, except mechanical numbering, heading-level and punctuation fixes: {key}…")


def meta_in_text(text: str, before: str = "") -> str:
    from .checks.grounding_rules import meta_sentences
    hits = meta_sentences(text or "", before)
    return hits[0] if hits else ""


from .checks.citations import CITE as _CITE_RE

_TRAILING_CITES = re.compile(r"(?:[ \t]*\[(?:[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12,64})-[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9_-]*-manualF[1-9]\d*)\])+")


def absorb_trailing_citations(content: str, op: str, anchor: str, anchor_end: str = "") -> str:
    if op not in ("replace", "delete"):
        return anchor_end
    i, end = _locate(content, anchor, anchor_end)
    if i < 0:
        return anchor_end
    m = _TRAILING_CITES.match(content, end)
    if not m:
        return anchor_end


    return (anchor_end + m.group(0)) if anchor_end else m.group(0)


def citation_only_paragraphs(content: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", content or ""):
        p = para.strip()
        if p and _CITE_RE.search(p) and not _CITE_RE.sub("", p).strip():
            out.append(p)
    return out


def drop_citation_only_paragraphs(content: str) -> tuple[str, list[str]]:
    gone = citation_only_paragraphs(content)
    if not gone:
        return content, []
    paras = re.split(r"(\n\s*\n)", content or "")
    kept = [p for p in paras if p.strip() not in gone]
    return tidy_blank_lines("".join(kept)), gone


def _unit_of(fact_id: str) -> str:
    parts = (fact_id or "").split("-")
    return parts[-2] if len(parts) >= 3 else ""


def source_switch(content: str, anchor: str, text: str, anchor_end: str = "") -> str:
    from .checks.citations import cited_ids
    old = cited_ids(_replaced_span(content, anchor, anchor_end))
    new = cited_ids(text)
    if not old or not new:
        return ""
    gone = [c for c in old if c not in new]
    added = [c for c in new if c not in old]
    if not gone or not added:
        return ""
    units = {_unit_of(c) for c in old}
    foreign = [c for c in added if _unit_of(c) not in units]
    if not foreign:
        return ""
    return (f'This revision replaces [{gone[0]}] with a fact from another meeting [{foreign[0]}]. Citation replacements must refer to facts from the same meeting.')


def reject_revision(content: str, op: str, anchor: str, text: str,
                    anchor_end: str = "", edited: set[str] | None = None,
                    before: str = "", body_lang: str = "") -> str:
    key = " ".join(anchor.split())[:40]
    meta = meta_in_text(text, before) if op != "delete" else ""
    if meta:
        return (f'Discarded revision containing meta commentary ("{meta[:30]}...") instead of note content: {key[:24]}…')
    if op != "delete" and body_lang:

        from .checks.language import switched
        why = switched(text, body_lang)
        if why:
            return f'Discarded revision that changes language ({why}): {key[:24]}…'
    if op == "replace":

        why = source_switch(content, anchor, text, anchor_end)
        if why:
            return f'{why}; discarded: {key[:24]}…'
    if op in ("replace", "delete") and _span_missing(content, anchor, anchor_end):
        return f'Discarded revision because its end marker does not occur in the body: {key[:24]}…'
    if op == "replace" and edited is not None and key in edited:
        return f'Skipped a location already changed in the previous round: {key[:24]}…'
    if op == "replace" and _is_same_meaning_rewrite(
            _replaced_span(content, anchor, anchor_end), text):
        return f'Discarded revision that merely rephrases without improving content: {key[:24]}…'
    if op in ("insert", "insert_before") and _splits_a_sentence(content, op, anchor, anchor_end, text):


        return f'Discarded revision that would split a sentence: {key[:24]}…'
    if op == "replace" and not anchor_end and content.count(anchor) > 1:


        return f'The location occurs multiple times and has no end marker to disambiguate it: {key[:24]}…'
    return ""


_SENTENCE_END = set("。！？!?…；;」』）】》”’\n")


def _splits_a_sentence(content: str, op: str, anchor: str, anchor_end: str, text: str) -> bool:
    body = (text or "").strip()

    if len(body) < 20 or not any(ch in "。！？!?" for ch in body):
        return False
    i, end = _locate(content, anchor, anchor_end)
    if i < 0:
        return False
    cut = i if op == "insert_before" else end
    head = content[:cut]
    if not head.strip():
        return False
    if (text or "").startswith(("\n", "\r")):


        rest_same_line = content[cut:].split("\n", 1)[0]
        return bool(rest_same_line.strip()) and head.rstrip(" \t")[-1:] not in _SENTENCE_END
    return head.rstrip(" \t")[-1:] not in _SENTENCE_END


def apply_revision(content: str, op: str, anchor: str, text: str,
                    insert_offset: int = 0, anchor_end: str = "") -> str:
    i, end = _locate(content, anchor, anchor_end)
    if i < 0:
        return content
    if anchor_end and end <= i + len(anchor):
        end = i + len(anchor)
    if op == "insert":
        end += insert_offset
        return content[:end] + text + content[end:]
    if op == "insert_before":
        return content[:i] + text + content[i:]
    if op == "delete":
        return content[:i] + content[end:]
    return content[:i] + text + content[end:]  # replace


def expand_sources(raw: list, facts: list[str]) -> list[str]:
    out: list[str] = []
    for item in raw[:6]:
        key = str(item).strip().strip("[]")
        if not key:
            continue
        hit = next((f for f in facts if key in f[:60]), None)
        out.append(hit or str(item))
    return out
