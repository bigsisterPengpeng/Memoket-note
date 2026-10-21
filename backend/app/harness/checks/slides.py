"""Advisory structure checks for generated Markdown slides."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .citations import cited_ids


MAX_CHARS = 200

MAX_BULLETS = 6


NOUN_PHRASE_MAX = 6

_CLAIM = re.compile('[0-9]|\u662f|\u8981|\u628a|\u4ece|\u5230|\u6539|\u964d|\u6da8|\u5ef6|\u505c|\u4e0d|\u6ca1|\u4ecd|\u5df2|\u5c06|\u9700|\u5e94')


@dataclass(frozen=True)
class SlideCheck:
    pages: int

    cited_pages: int
    over_dense: list[int]

    weak_titles: list[int]

    stray_numbers: list[str]

    missed_sections: list[str]

    @property
    def cite_coverage(self) -> float:
        return round(self.cited_pages / self.pages, 2) if self.pages else 0.0

    def notes(self) -> list[str]:
        out: list[str] = []
        if self.pages and self.cite_coverage < 0.5:
            out.append(f'{self.pages} slides, only {self.cited_pages} have source citations. Add supporting evidence to the remaining slides.')
        if self.over_dense:
            out.append(f"Slide {'、'.join((str(i) for i in self.over_dense))} is too dense (over {MAX_CHARS} characters or {MAX_BULLETS} bullets).")
        if self.weak_titles:
            out.append(f"Slide {'、'.join((str(i) for i in self.weak_titles))} has a noun-phrase title that does not state its conclusion.")
        if self.stray_numbers:
            out.append(f"These numbers do not appear in the source: {'、'.join(self.stray_numbers[:6])}")
        if self.missed_sections:
            out.append(f"These source sections have no corresponding slide: {'、'.join(self.missed_sections[:4])}")
        return out


_FENCE = re.compile(r"^```")


def split_pages(md: str) -> list[str]:
    lines = (md or "").split("\n")
    start = 0
    if lines and lines[0].strip() == "---":                 # front-matter
        for i, ln in enumerate(lines[1:], 1):
            if ln.strip() == "---":
                start = i + 1
                break
    pages: list[list[str]] = [[]]
    fenced = False
    for ln in lines[start:]:
        if _FENCE.match(ln.strip()):
            fenced = not fenced
        if not fenced and ln.strip() == "---":
            pages.append([])
            continue
        pages[-1].append(ln)
    return [p for p in ("\n".join(x).strip() for x in pages) if p]


def _sections(src: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^##\s+(\S.*)$", src)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


_NUM = re.compile(r"\d+(?:\.\d+)?")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.、])\s+", re.M)


def check_slides(md: str, source: str) -> SlideCheck:
    pages = split_pages(md)
    cited = sum(1 for p in pages if cited_ids(p))
    dense: list[int] = []
    weak: list[int] = []
    for i, p in enumerate(pages, 1):
        body = re.sub(r"^#+\s+.*$", "", p, flags=re.M)
        if len(re.sub(r"\s", "", body)) > MAX_CHARS or len(_BULLET.findall(p)) > MAX_BULLETS:
            dense.append(i)
        head = next((m.group(1).strip() for m in re.finditer(r"^#+\s+(.*)$", p, re.M)), "")


        plain = re.sub(r"[\s\W_]", "", head)
        if 1 < i < len(pages) and 0 < len(plain) <= NOUN_PHRASE_MAX and not _CLAIM.search(head):
            weak.append(i)


    src_nums = set(_NUM.findall(source or ""))
    stray: list[str] = []
    for n in _NUM.findall("\n".join(pages)):
        if n not in src_nums and n not in stray and len(n) >= 2:
            stray.append(n)


    flat = "\n".join(pages)
    shown = set(cited_ids(flat))
    missed = [t for t, body in _sections(source or "")
              if t not in flat and not (set(cited_ids(body)) & shown)]
    return SlideCheck(pages=len(pages), cited_pages=cited, over_dense=dense,
                      weak_titles=weak, stray_numbers=stray, missed_sections=missed)
