"""Parse user-authored headings and constrain writing to the requested outline. Existing structure remains the authoritative section boundary."""

from __future__ import annotations

import difflib
import re

_HEADING = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$", re.M)
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})", re.M)


def _mask_fences(content: str) -> str:
    if "```" not in content and "~~~" not in content:
        return content
    out = list(content)
    fenced = False
    for m in re.finditer(r"^.*$", content, re.M):
        is_fence = bool(_FENCE.match(m.group(0)))
        if is_fence or fenced:
            for i in range(m.start(), m.end()):
                out[i] = "x"
        if is_fence:
            fenced = not fenced
    return "".join(out)


def _marks(content: str) -> list[re.Match]:
    return list(_HEADING.finditer(_mask_fences(content or "")))


EMPTY_BODY_CHARS = 40

OUTLINE_RATIO = 0.6

MIN_HEADINGS = 3


def headings(content: str) -> list[tuple[int, str]]:
    return [(len(m.group(1)), m.group(2)) for m in _marks(content)]


def _bodies(content: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    marks = _marks(content)
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(content or "")
        out.append((m.group(2), (content or "")[m.end():end].strip()))
    return out


def section_bodies(content: str) -> list[tuple[str, str]]:
    return _bodies(content)


def is_outline(content: str) -> bool:
    body = _bodies(content)
    if len(body) < MIN_HEADINGS:
        return False
    titles = [t for t, _b in body]
    if len(set(titles)) != len(titles):


        return False
    empty = sum(1 for _t, b in body if len(b) < EMPTY_BODY_CHARS)
    return empty / len(body) >= OUTLINE_RATIO


def outline_block(content: str) -> str:
    hs = headings(content)
    if not hs:
        return ""
    tree = "\n".join(f"{'  ' * (lv - 1)}- {txt}" for lv, txt in hs)
    return (
        '[User-supplied structure: explicit writing intent]\n'
        + tree
        + '\n\nPreserve every heading exactly. Do not delete, reorder, merge or rewrite headings. Empty sections are intentional places to write, not defects.\nWrite only the specified section this round, without creating headings. The user has already supplied the structure. Do not append duplicate sections.\nIf a section lacks supporting knowledge-base material, leave it unchanged and continue with a supported section. Do not invent content, insert placeholders or add commentary about insufficient evidence. Write what the records support.\n'
    )


def structure_intact(before: str, after: str) -> bool:
    old = headings(before)
    if not old:
        return True
    old_set = set(old)
    kept = [h for h in headings(after) if h in old_set]
    return kept == old


def next_gap(content: str) -> tuple[str, int] | None:
    marks = _marks(content)
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(content or "")
        body = (content or "")[m.end():end].strip()
        if len(body) < EMPTY_BODY_CHARS:
            return m.group(2), m.end()
    return None


def section_end(content: str, title: str) -> int | None:
    marks = _marks(content)
    want = (title or "").strip()
    for i, m in enumerate(marks):
        if m.group(2).strip() != want:
            continue
        level = len(m.group(1))
        for n in marks[i + 1:]:
            if len(n.group(1)) <= level:
                return n.start()
        return len(content or "")
    return None


PLACE_DIRECTIVE = re.compile(
    r"^\s*[\u3010\[]\s*(?:Place|\u653e\u5230)[:\uff1a]\s*(.+?)\s*[\u3011\]]\s*$",
    re.IGNORECASE,
)


def parse_place_directive(first_line: str) -> str | None:
    """Read the first-line placement target, including legacy model responses."""
    m = PLACE_DIRECTIVE.match(first_line or "")
    if not m:
        return None
    target = m.group(1).strip().strip("「」\"'")
    return None if target.casefold() in ("end", '\u6587\u672b', '\u672b\u5c3e', '\u6700\u540e', "") else target


def insert_into(content: str, pos: int, text: str) -> str:
    body = text.strip()
    if not body:
        return content
    head = content[:pos].rstrip("\n")
    tail = content[pos:].lstrip("\n")


    tail = re.sub(r"^[，、。；：,;:]+\s*", "", tail)
    return f"{head}\n\n{body}\n\n{tail}"


def strip_headings(text: str) -> str:
    masked = _mask_fences(text or "").splitlines()
    kept = [ln for ln, mk in zip((text or "").splitlines(), masked)
            if not _HEADING.match(mk)]
    out = "\n".join(kept)

    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _is_block(para: str) -> bool:
    p = para.lstrip()
    return p.startswith(("```", "|", ">", "    ")) or "```" in p


_CITE = re.compile(r"\[[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+\]")


def cites_conflict(a: str, b: str) -> bool:
    ca, cb = set(_CITE.findall(a or "")), set(_CITE.findall(b or ""))
    return bool(ca and cb and ca != cb)


def drop_already_written(content: str, text: str, *, threshold: float = 0.62) -> str:
    body = (text or "").strip()
    if not body:
        return body


    old = [p for p in re.split(r"\n\s*\n", content or "")
           if len(p.strip()) >= 40 and not _is_block(p.strip())]
    kept = []
    for para in re.split(r"\n\s*\n", body):
        p = para.strip()
        if len(p) < 40 or _is_block(p):


            kept.append(para)
            continue


        seen = old + [x.strip() for x in kept if len(x.strip()) >= 40]


        if any(not cites_conflict(p, o.strip())
               and difflib.SequenceMatcher(None, p, o.strip()).ratio() > threshold
               for o in seen):
            continue
        kept.append(para)
    whole = re.sub(r"\n{3,}", "\n\n", "\n\n".join(kept)).strip()


    return whole


SENTENCE_THRESHOLD = 0.62
MIN_SENTENCE_LEN = 18
MIN_BLOCK_LEN = 20


_SENT_SPLIT = re.compile(r"(?<=[。！？!?])|(?<=\n)")
_TABLE_ROW = re.compile(r"^\s*\|")


_CITATION_ONLY = re.compile(r"^(?:\s*\[[^\]\n]+\]\s*)+$")


def strip_fences(text: str) -> str:
    out, fenced = [], False
    for ln in (text or "").split("\n"):
        if ln.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append(ln)
    return "\n".join(out)


def sentence_blocks(text: str, *, min_len: int = MIN_BLOCK_LEN) -> list[str]:
    return [p.strip() for p in strip_fences(text).split("\n\n")
            if len(p.strip()) >= min_len]


def sentence_pieces(paragraph: str) -> list[str]:
    return [p for p in _SENT_SPLIT.split(paragraph or "") if p]


def is_sentence(piece: str) -> bool:
    t = (piece or "").strip()
    return (len(t) >= MIN_SENTENCE_LEN
            and not _TABLE_ROW.match(t)
            and not _HEADING.match(t)
            and not _CITATION_ONLY.match(t))


def sentences(paragraph: str) -> list[str]:
    return [t for t in (p.strip() for p in sentence_pieces(paragraph))
            if is_sentence(t)]


_LIST_MARK = re.compile(r"^\s*(?:[-*+•·]|\d+[.)、])\s+")
TEMPLATE_RUN = 3
TEMPLATE_PREFIX = 8


def template_rows(text: str) -> set[str]:
    groups: dict[str, list[str]] = {}
    for ln in strip_fences(text or "").split("\n"):
        if not _LIST_MARK.match(ln):
            continue
        t = ln.strip()
        groups.setdefault(t[:TEMPLATE_PREFIX], []).append(t)
    return {t for g in groups.values() if len(g) >= TEMPLATE_RUN for t in g}


def near_duplicate(a: str, b: str, threshold: float = SENTENCE_THRESHOLD) -> bool:
    if cites_conflict(a, b):
        return False
    sm = difflib.SequenceMatcher(None, a, b)
    if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
        return False
    return sm.ratio() >= threshold


def drop_restated_sentences(content: str, text: str, *,
                            threshold: float = SENTENCE_THRESHOLD) -> str:
    body = (text or "").strip()
    if not body:
        return body


    template = template_rows((content or "") + "\n" + (text or ""))
    seen = [s for para in sentence_blocks(content) for s in sentences(para)
            if s not in template]
    kept_paras: list[str] = []
    for para in re.split(r"\n\s*\n", body):
        stripped = para.strip()
        if len(stripped) < MIN_BLOCK_LEN or _is_block(stripped):


            kept_paras.append(para)
            continue
        pieces, dropped = [], False
        for piece in sentence_pieces(para):
            t = piece.strip()
            if not is_sentence(t) or t in template:
                pieces.append(piece)
                continue
            if any(near_duplicate(t, old, threshold) for old in seen):
                dropped = True
                continue
            pieces.append(piece)


            seen.append(t)
        if not dropped:
            kept_paras.append(para)
            continue
        rebuilt = "".join(pieces).strip()
        if rebuilt:
            kept_paras.append(rebuilt)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(kept_paras)).strip()
