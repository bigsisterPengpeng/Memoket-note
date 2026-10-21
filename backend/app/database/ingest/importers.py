"""Wash content from other note apps into clean markdown memoket-note can take.

The four sources (Apple Notes / Notion / Evernote / Obsidian) get content in very different ways,
but **the washing step is shared**, so it lives here as pure functions: no network, no file system,
no other app modules (only the i18n dictionary, for the default title), testable on its own. Fetching
content and POSTing live in ``scripts/import_notes.py``.

Research and each source's pitfalls: ``docs/import-from-other-note-apps.md``.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from datetime import date as _date

from ...util import i18n

# ---------------------------------------------------------------- the shared product


@dataclass(frozen=True)
class ImportedNote:
    """One note handed to the importer after washing.

    ``source_id`` must be stable on the source side (Notion page_id, hash of the Obsidian relative path,
    ENEX guid...) - it is spliced into KITE's session_id, and re-running the import uses it to skip content
    already imported without spending LLM calls. A random value would double everything on every import.
    """

    title: str
    content: str
    date: str = ""            # YYYY-MM-DD, empty when unavailable (the caller decides what to fall back to)
    source: str = "import"    # obsidian / notion / apple / evernote
    source_id: str = ""
    icon: str = ""            # note icon (boxicons class name) carried in the front-matter we export ourselves; restored on re-import
    folder: str = ""          # folder/notebook name on the source side, used for filing on this side


# ---------------------------------------------------------------- dates

_DATE_PATTERNS = (
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})"),                    # 2026-03-15…
    re.compile(r"^(\d{4})(\d{2})(\d{2})T"),                     # 20260315T091500Z (ENEX)
    re.compile(r"^\w+,\s+(\d{1,2})\s+(\w+)\s+(\d{4})"),         # English dates from AppleScript
)
_MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    "January February March April May June July August September "
    "October November December".split(), 1)}


def normalize_date(raw: str | None) -> str:
    """Normalize every vendor's assorted date formats to YYYY-MM-DD; return an empty string when unrecognized.

    **Do not guess** when unrecognized: the caller falls back to the file mtime or today on an empty string,
    and a wrongly guessed date is worse than none - it enters the knowledge base looking "plausible".
    """
    s = (raw or "").strip()
    if not s:
        return ""
    m = _DATE_PATTERNS[0].match(s) or _DATE_PATTERNS[1].match(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _DATE_PATTERNS[2].match(s)
    if m and m.group(2) in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(2)]}-{int(m.group(1)):02d}"
    return ""


def today() -> str:
    return _date.today().isoformat()


# ---------------------------------------------------------------- Obsidian

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
_WIKI = re.compile(r"\[\[([^\]|#]+?)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
# Only eat inline whitespace, **never newlines**: eating a newline pushes an immediately following
# code block off the start of its line, and the dataview cleanup below that matches at line start
# stops working entirely (caught on the spot by the self-test).
_EMBED = re.compile(r"!\[\[[^\]]+\]\][ \t]*")
_CODE_FENCE = re.compile(r"^```(\w*)\n.*?^```\s*$", re.M | re.S)
# In the Obsidian ecosystem these code blocks are "templates/queries", not content; pure noise for
# extraction
_TEMPLATE_LANGS = {"dataview", "dataviewjs", "templater", "tasks", "query", "meta-bind"}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split off YAML frontmatter. Only flat ``key: value`` - nested structures are useless for import
    and not worth a YAML dependency."""
    m = _FRONTMATTER.match(text or "")
    if not m:
        return {}, text or ""
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("-"):
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip().strip("'\"")
    return meta, text[m.end():]


def clean_obsidian(text: str) -> str:
    """Wash Obsidian-specific syntax into plain markdown.

    - ``[[A|B]]`` -> ``B``, ``[[A#anchor]]`` -> ``A``: link syntax is noise for extraction,
      while the link **text** is often an entity name and must stay
    - ``![[attachment.png]]``: removed entirely; KITE only takes text
    - dataview/templater code blocks: removed; they are templates, not content
    """
    body = _EMBED.sub("", text or "")
    body = _WIKI.sub(lambda m: (m.group(2) or m.group(1)).strip(), body)
    body = _CODE_FENCE.sub(
        lambda m: "" if m.group(1).lower() in _TEMPLATE_LANGS else m.group(0), body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


# ---------------------------------------------------------------- HTML / ENML

_BLOCK_TAGS = ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
               "blockquote", "pre")


def html_to_markdown(source: str) -> str:
    """Convert Apple Notes HTML / Evernote ENML into plain markdown.

    Deliberately only **structure** (headings, lists, bold, links, line breaks), no attempt to reproduce
    layout: what enters the knowledge base is text and the facts in it, style is of no use at all, and every
    extra conversion rule is one more place to go wrong.

    markdownify/html2text are not used because both vendors' markup is a restricted subset: the Apple Notes
    body is simple HTML generated by Notes.app itself, and ENML is a subset of XHTML with its own
    DTD (``<en-note>``/``<en-media>``) - generic converters leave garbage on ``<en-media>``,
    so it has to be handled here anyway.
    """
    if not source or not source.strip():
        return ""
    try:
        from lxml import etree, html as lhtml
    except ImportError:                       # pragma: no cover - lxml is an existing dependency
        return re.sub(r"<[^>]+>", "", source)

    # ENML's <en-media> (attachments) and <en-crypt> (encrypted blocks) are removed whole first: the
    # former is a placeholder for a base64 attachment, the latter cannot be decrypted at all; kept,
    # they only turn into garbage in the body.
    cleaned = re.sub(r"<en-(media|crypt)\b[^>]*?(/>|>.*?</en-\1>)", "", source, flags=re.S)
    try:
        root = lhtml.fromstring(cleaned)
    except (etree.ParserError, ValueError):
        return re.sub(r"<[^>]+>", "", cleaned).strip()

    out: list[str] = []

    def walk(el, depth: int = 0) -> None:
        tag = (el.tag if isinstance(el.tag, str) else "").lower()
        if tag in ("script", "style", "en-media", "en-crypt"):
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            out.append(f"\n\n{'#' * int(tag[1])} {el.text_content().strip()}\n\n")
            return
        if tag == "li":
            # Take only this item's **own** text, not the content of nested sub-lists along with it
            # (text_content() would squash "B" and the "C" under it into "BC").
            own = [el.text or ""]
            nested = []
            for child in el:
                if (child.tag if isinstance(child.tag, str) else "").lower() in ("ul", "ol"):
                    nested.append(child)
                else:
                    own.append(child.text_content())
                own.append(child.tail or "")
            # depth is "how many ul/ol levels wrap it"; outermost list items get no indent
            out.append(f"\n{'  ' * max(0, depth - 1)}- {''.join(own).strip()}")
            for sub in nested:
                walk(sub, depth)
            return
        if tag == "a":
            href = (el.get("href") or "").strip()
            txt = el.text_content().strip()
            out.append(f"[{txt}]({href})" if href and txt else txt)
            return
        if tag in ("b", "strong"):
            txt = el.text_content().strip()
            out.append(f"**{txt}**" if txt else "")
            return
        if tag == "br":
            out.append("\n")
            return
        if el.text:
            out.append(el.text)
        for child in el:
            walk(child, depth + 1 if tag in ("ul", "ol") else depth)
            if child.tail:
                out.append(child.tail)
        if tag in _BLOCK_TAGS:
            out.append("\n")

    walk(root)
    text = _html.unescape("".join(out))
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------- Evernote ENEX


def parse_enex(xml_bytes: bytes, *, limit: int = 0) -> list[ImportedNote]:
    """Parse one ``.enex``.

    Streamed with ``iterparse`` rather than read into memory at once: a large notebook's ENEX can reach
    hundreds of MB, and most of that volume is base64 attachments in ``<resource>`` - exactly what we discard.
    """
    from lxml import etree

    notes: list[ImportedNote] = []
    ctx = etree.iterparse(_BytesReader(xml_bytes), events=("end",), tag="note",
                          recover=True, huge_tree=True)
    for _ev, el in ctx:
        title = (el.findtext("title") or "").strip() or i18n.msg("(no title)")
        content = el.findtext("content") or ""
        created = normalize_date(el.findtext("created"))
        guid = (el.findtext("guid") or "").strip()
        body = html_to_markdown(content)
        if body:
            notes.append(ImportedNote(
                title=title, content=body, date=created, source="evernote",
                # Without a guid fall back to title+date: ENEX exports do not always carry a guid,
                # and having no stable identifier at all would make re-running the import double the
                # content.
                source_id=guid or f"{title}-{created}"))
        el.clear()
        while el.getprevious() is not None:
            del el.getparent()[0]
        if limit and len(notes) >= limit:
            break
    return notes


class _BytesReader:
    """A minimal file-like for lxml.iterparse, so a large ENEX need not be written to a temporary file."""

    def __init__(self, data: bytes) -> None:
        self._data, self._pos = data, 0

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = len(self._data) - self._pos
        chunk = self._data[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk
