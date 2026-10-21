"""Note-tree exports with hierarchy, cloned branches, links and metadata preserved where supported."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import httpx

from . import store

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
ASSET_REF = re.compile(r"/api/assets/([a-f0-9]{24}\.[a-z0-9]+)")
NOTE_LINK = re.compile(r"\]\(note://([a-f0-9]{12})\)")

NOTE_LINK_FULL = re.compile(r"\[([^\]\n]*)\]\(note://([a-f0-9]{12})\)")


MERMAID_KEY_LEN = 24
MERMAID_RENDER_MAX = 4 * 1024 * 1024
MERMAID_RENDERS_MAX = 64


def mermaid_key(code: str) -> str:
    import hashlib
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()[:MERMAID_KEY_LEN]


def mermaid_blocks(md: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for b in md_to_blocks(md):
        if b.kind == "code" and b.lang == "mermaid" and b.text.strip():
            out[mermaid_key(b.text)] = b.text
    return out


_SENTENCE_END = "。！？"
_PAUSE = "；，,：:"


def clip_title(line: str, max_len: int = 60) -> str:
    for i, ch in enumerate(line):
        if ch in _SENTENCE_END and i >= 2:
            return line[:min(i, max_len)]
        if ch in _PAUSE and i >= 8:
            return line[:min(i, max_len)]
    return line[:max_len]


def display_title(title: str, content: str) -> str:
    t = (title or "").strip()
    if t and t not in ('\u672a\u547d\u540d', "Untitled", "note"):
        return t
    for line in (content or "").split("\n"):

        line = re.sub(r"^#+\s*", "", line.strip()).strip()
        if line:
            return clip_title(line)
    return "Untitled"


def safe_name(name: str) -> str:
    name = _BAD.sub(" ", name).strip(" .")
    return (name or "Untitled")[:80]


@dataclass
class ExportFile:
    path: str
    content: str
    note_id: str = ""
    title: str = ""
    assets: set[str] = field(default_factory=set)


_YAML_PLAIN = re.compile(r"^[^\[\]{}\"'*&!|>%@`#,\-?:][^#]*$")


def yaml_scalar(value: str) -> str:
    v = value or ""
    if v and _YAML_PLAIN.match(v) and ": " not in v and not v.endswith(":") and "\n" not in v and v == v.strip():
        return v
    return json.dumps(v, ensure_ascii=False)


def note_body(n: dict, paths: dict[str, str] | None = None, depth: int = 0,
              exported: set[str] | None = None) -> tuple[str, set[str]]:
    front = (f"---\nid: {n['id']}\nmemoket_id: {n['id']}\ntitle: {yaml_scalar(n['title'] or '')}\n"
             + (f"icon: {yaml_scalar(n['icon'])}\n" if n.get("icon") else "")
             + f"created: {n['created_at']}\nupdated: {n['updated_at']}\n---\n\n")
    body = n["content"] or ""
    assets = set(ASSET_REF.findall(body))
    up = "../" * depth
    body = ASSET_REF.sub(lambda m: f"{up}_assets/{m.group(1)}", body)
    if paths:


        if exported is not None:
            def _plain(m: re.Match) -> str:
                nid = m.group(2)
                if nid not in paths or nid in exported:
                    return m.group(0)
                return f'{m.group(1)} (note not included in this export)'
            body = NOTE_LINK_FULL.sub(_plain, body)

        def _link(m: re.Match) -> str:
            target = paths.get(m.group(1))
            if not target:
                return m.group(0)
            return "](<" + up + target + ">)"
        body = NOTE_LINK.sub(_link, body)
    return front + body, assets


def render_tree(user: str, only: set[str] | None = None) -> list[ExportFile]:
    notes = {n["id"]: n for n in store.list_notes(user)}
    rows = store.tree(user)
    children: dict[str, list[dict]] = {}
    for r in rows:
        children.setdefault(r["parent_note_id"], []).append(r)
    for lst in children.values():
        lst.sort(key=lambda r: (r.get("position") or 0, r["note_id"]))
    plan: list[tuple[dict | None, str]] = []
    written: dict[str, str] = {}
    used: set[str] = set()

    def unique(path: str) -> str:
        base, i = path, 2
        while path in used:
            root, ext = base.rsplit(".", 1) if "." in base.rsplit("/", 1)[-1] else (base, "")
            path = f"{root} ({i})" + (f".{ext}" if ext else "")
            i += 1
        used.add(path)
        return path

    def walk(parent: str, prefix: str) -> None:
        for r in children.get(parent, []):
            nid = r["note_id"]
            n = notes.get(nid)
            if not n:
                continue
            name = safe_name(display_title(n["title"], n["content"]))
            has_kids = bool(children.get(nid))
            if nid in written:
                if only is None:
                    link = unique(f"{prefix}{name}.link.txt")
                    plan.append((None, link)); clone_of[link] = (name, written[nid])
                continue
            if has_kids:
                written[nid] = unique(f"{prefix}{name}/{name}.md"); plan.append((n, written[nid]))
                walk(nid, f"{prefix}{name}/")
            else:
                written[nid] = unique(f"{prefix}{name}.md"); plan.append((n, written[nid]))

    clone_of: dict[str, tuple[str, str]] = {}
    walk(store.ROOT_ID, "")
    for nid, n in notes.items():
        if nid not in written:
            written[nid] = unique(f"_Unfiled/{safe_name(display_title(n['title'], n['content']))}.md")
            plan.append((n, written[nid]))

    out: list[ExportFile] = []
    for n, path in plan:
        if n is None:
            name, target = clone_of[path]
            out.append(ExportFile(path=path, content=f'Clone of "{name}"; body: {target}\n'))
            continue
        if only is not None and n["id"] not in only:
            continue

        body, assets = note_body(n, written, depth=path.count("/"),
                                 exported=None if only is None else set(only) & set(written))
        out.append(ExportFile(path=path, content=body, note_id=n["id"],
                              title=display_title(n["title"], n["content"]), assets=assets))
    return out


_FEISHU_LANG = {
    "c": 8, "cpp": 9, "c++": 9, "csharp": 10, "css": 12, "go": 17, "html": 22,
    "java": 24, "javascript": 25, "js": 25, "json": 26, "kotlin": 28, "latex": 29,
    "lua": 30, "makefile": 31, "markdown": 32, "md": 32, "objectivec": 36, "php": 40,
    "python": 43, "py": 43, "r": 45, "ruby": 49, "rust": 50, "scala": 51, "scheme": 52,
    "shell": 53, "sh": 53, "sql": 54, "swift": 55, "typescript": 58, "ts": 58,
    "xml": 60, "yaml": 61, "yml": 61, "bash": 63,
}


_NOTION_LANG = {k: k for k in ("c", "css", "go", "html", "java", "javascript", "json",
                               "kotlin", "latex", "lua", "makefile", "markdown", "php",
                               "python", "r", "ruby", "rust", "scala", "scheme", "shell",
                               "sql", "swift", "typescript", "xml", "yaml", "bash", "mermaid")}
_NOTION_LANG.update({"cpp": "c++", "js": "javascript", "ts": "typescript",
                     "py": "python", "sh": "shell", "yml": "yaml", "md": "markdown"})


@dataclass
class Block:
    kind: str                       # heading / bullet / ordered / todo / code / quote / para / table / divider / image
    text: str = ""
    level: int = 0
    lang: str = ""
    checked: bool = False
    rows: list[list[str]] = field(default_factory=list)
    children: list["Block"] = field(default_factory=list)
    alt: str = ""
    src: str = ""


_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TASK = re.compile(r"^\[( |x|X)\]\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_DIVIDER = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_IMAGE_LINE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def _split_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, buf, i = [], [], 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("|"); i += 2; continue
        if ch == "|":
            cells.append("".join(buf).strip()); buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _strip_frontmatter(md: str) -> str:
    text = md
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            text = text[end + 5:]
    return text


def md_to_blocks(md: str) -> list[Block]:
    lines = _strip_frontmatter(md).split("\n")
    out: list[Block] = []
    para: list[str] = []
    stack: list[tuple[int, Block]] = []

    def flush_para() -> None:
        if para:
            out.append(Block("para", "\n".join(s.strip() for s in para)))
            para.clear()

    def close_lists() -> None:
        stack.clear()

    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```") or ln.startswith("~~~"):
            fence = ln[:3]
            flush_para(); close_lists()
            lang = ln[3:].strip().split()[0] if ln[3:].strip() else ""
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].startswith(fence):
                buf.append(lines[j]); j += 1
            out.append(Block("code", "\n".join(buf), lang=lang.lower()))
            i = j + 1
            continue
        m = _HEADING.match(ln)
        if m:
            flush_para(); close_lists()
            out.append(Block("heading", m.group(2).strip(), level=len(m.group(1)))); i += 1; continue
        if _DIVIDER.match(ln):
            flush_para(); close_lists()
            out.append(Block("divider")); i += 1; continue
        m = _IMAGE_LINE.match(ln)
        if m:
            flush_para(); close_lists()
            out.append(Block("image", alt=m.group(1).strip(), src=m.group(2).strip())); i += 1; continue
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]) and "|" in lines[i + 1]:
            flush_para(); close_lists()
            rows = [_split_cells(ln)]
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(_split_cells(lines[j])); j += 1
            width = max(len(r) for r in rows)
            out.append(Block("table", rows=[r + [""] * (width - len(r)) for r in rows]))
            i = j
            continue
        m = _LIST.match(ln)
        if m:
            flush_para()
            indent = len(m.group(1).expandtabs(4))
            body = m.group(3).strip()
            kind = "ordered" if m.group(2)[0].isdigit() else "bullet"
            b = Block(kind, body)
            t = _TASK.match(body)
            if t and kind == "bullet":
                b = Block("todo", t.group(2).strip(), checked=t.group(1) != " ")
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if stack:
                parent = stack[-1][1]
                b.level = parent.level + 1
                parent.children.append(b)
            else:
                out.append(b)
            stack.append((indent, b))
            i += 1
            continue
        m = _QUOTE.match(ln)
        if m:
            flush_para(); close_lists()
            buf = [m.group(1).strip()]
            j = i + 1
            while j < len(lines) and (q := _QUOTE.match(lines[j])):
                buf.append(q.group(1).strip()); j += 1
            out.append(Block("quote", "\n".join(buf).strip()))
            i = j
            continue
        if not ln.strip():
            flush_para(); close_lists(); i += 1; continue

        if stack and ln.startswith((" ", "\t")) and not para:
            stack[-1][1].text += "\n" + ln.strip()
            i += 1
            continue
        close_lists()
        para.append(ln)
        i += 1
    flush_para()
    return out


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    strike: bool = False
    link: str = ""


_CITE = re.compile(r" ?\[(?:[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9_-]*-manualF[1-9]\d*)\]")
_INLINE = re.compile(
    r"(?P<fence>`+)(?P<code>.+?)(?P=fence)"
    r"|!\[(?P<imgalt>[^\]]*)\]\((?P<imgsrc>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
    r"|\[\[(?P<wiki>[^\]|]+)(?:\|(?P<wikilabel>[^\]]+))?\]\]"
    r"|\[(?P<ltxt>[^\]]+)\]\((?P<lurl>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|__(?P<bold2>.+?)__"
    r"|~~(?P<strike>.+?)~~"
    r"|(?<![\w*])\*(?P<em>[^*\n]+?)\*(?![\w*])"
    r"|(?<![\w_])_(?P<em2>[^_\n]+?)_(?![\w_])",
    re.S,
)


def strip_citations(text: str) -> str:
    return _CITE.sub("", text or "")


def inline_runs(text: str, **style) -> list[Run]:
    s = strip_citations(text)
    runs: list[Run] = []
    pos = 0

    def plain(t: str) -> None:
        if t:
            runs.append(Run(t, **style))

    for m in _INLINE.finditer(s):
        plain(s[pos:m.start()])
        pos = m.end()
        g = m.groupdict()
        if g["code"] is not None:
            runs.append(Run(g["code"], **{**style, "code": True}))
        elif g["imgalt"] is not None:
            plain(f"[Image: {g['imgalt'] or 'image'}]")
        elif g["wiki"] is not None:
            plain((g["wikilabel"] or g["wiki"]).strip())
        elif g["ltxt"] is not None:
            url = g["lurl"]
            sub = {**style, "link": url} if re.match(r"^https?://", url) else style
            runs.extend(inline_runs(g["ltxt"], **sub))
        elif g["bold"] is not None or g["bold2"] is not None:
            runs.extend(inline_runs(g["bold"] if g["bold"] is not None else g["bold2"], **{**style, "bold": True}))
        elif g["strike"] is not None:
            runs.extend(inline_runs(g["strike"], **{**style, "strike": True}))
        else:
            runs.extend(inline_runs(g["em"] if g["em"] is not None else g["em2"], **{**style, "italic": True}))
    plain(s[pos:])
    return runs or [Run("", **style)]


def _chunks(s: str, n: int = 2000) -> list[str]:
    return [s[i:i + n] for i in range(0, max(1, len(s)), n)] or [""]


# ---------------------------------------------------------------- Notion

def _notion_rich(runs: list[Run]) -> list[dict]:
    out = []
    for r in runs:
        for c in _chunks(r.text):
            t: dict = {"type": "text", "text": {"content": c}}
            if r.link:
                t["text"]["link"] = {"url": r.link}
            if r.bold or r.italic or r.code or r.strike:
                t["annotations"] = {"bold": r.bold, "italic": r.italic, "strikethrough": r.strike,
                                    "underline": False, "code": r.code, "color": "default"}
            out.append(t)
    return out


def _notion_items(b: Block, depth: int = 0) -> list[dict]:
    t = {"bullet": "bulleted_list_item", "ordered": "numbered_list_item", "todo": "to_do"}[b.kind]
    body: dict = {"rich_text": _notion_rich(inline_runs(b.text))}
    if b.kind == "todo":
        body["checked"] = b.checked
    blk = {"object": "block", "type": t, t: body}
    overflow: list[dict] = []
    for kid in b.children:
        sub = _notion_items(kid, depth + 1)
        if depth < 2:
            body.setdefault("children", []).extend(sub)
        else:
            overflow.extend(sub)
    return [blk] + overflow


def _notion_note(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _notion_rich(inline_runs(text, italic=True))}}


def md_to_notion_blocks(md: str) -> list[dict]:
    blocks: list[dict] = []
    for b in md_to_blocks(md):
        if b.kind == "heading":
            if b.level <= 3:
                t = f"heading_{b.level}"
                blocks.append({"object": "block", "type": t, t: {"rich_text": _notion_rich(inline_runs(b.text))}})
            else:

                blocks.append({"object": "block", "type": "paragraph",
                               "paragraph": {"rich_text": _notion_rich(inline_runs(b.text, bold=True))}})
        elif b.kind in ("bullet", "ordered", "todo"):
            blocks.extend(_notion_items(b))
        elif b.kind == "code":
            blocks.append({"object": "block", "type": "code",
                           "code": {"rich_text": [{"type": "text", "text": {"content": c}} for c in _chunks(b.text)],
                                    "language": _NOTION_LANG.get(b.lang, "plain text")}})
        elif b.kind == "quote":
            blocks.append({"object": "block", "type": "quote", "quote": {"rich_text": _notion_rich(inline_runs(b.text))}})
        elif b.kind == "divider":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif b.kind == "table":
            width = len(b.rows[0])
            blocks.append({"object": "block", "type": "table",
                           "table": {"table_width": width, "has_column_header": True, "has_row_header": False,
                                     "children": [{"object": "block", "type": "table_row",
                                                   "table_row": {"cells": [_notion_rich(inline_runs(c)) for c in row]}}
                                                  for row in b.rows]}})
        elif b.kind == "image":
            m = ASSET_REF.search(b.src) or re.search(r"_assets/([a-f0-9]{24}\.[a-z0-9]+)", b.src)
            if re.match(r"^https?://", b.src):
                blocks.append({"object": "block", "type": "image", "image": {"type": "external", "external": {"url": b.src}}})
            elif m:


                blocks.append({"object": "block", "type": "image", "image": {}, "_asset": m.group(1), "_alt": b.alt})
            else:
                blocks.append(_notion_note(f"[Image: {b.alt or 'image'}]（{b.src}）"))
        else:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": _notion_rich(inline_runs(b.text))}})
    return blocks


def _feishu_elements(runs: list[Run]) -> list[dict]:
    out = []
    for r in runs:
        for c in _chunks(r.text):
            el: dict = {"text_run": {"content": c}}
            st: dict = {}
            if r.bold: st["bold"] = True
            if r.italic: st["italic"] = True
            if r.strike: st["strikethrough"] = True
            if r.code: st["inline_code"] = True
            if r.link: st["link"] = {"url": quote(r.link, safe="")}
            if st:
                el["text_run"]["text_element_style"] = st
            out.append(el)
    return out


def _feishu_text(text: str, **style) -> dict:
    return {"elements": _feishu_elements(inline_runs(text, **style))}


def _feishu_item(b: Block) -> dict:
    if b.kind == "todo":
        blk = {"block_type": 17, "todo": {**_feishu_text(b.text), "style": {"done": b.checked}}}
    elif b.kind == "ordered":
        blk = {"block_type": 13, "ordered": _feishu_text(b.text)}
    else:
        blk = {"block_type": 12, "bullet": _feishu_text(b.text)}
    if b.children:
        blk["children"] = [_feishu_item(k) for k in b.children]
    return blk


def md_to_feishu_children(md: str, renders: dict[str, bytes] | None = None) -> list[dict]:
    out: list[dict] = []
    for b in md_to_blocks(md):
        if b.kind == "heading":
            lvl = min(b.level, 9)
            out.append({"block_type": 2 + lvl, f"heading{lvl}": _feishu_text(b.text)})
        elif b.kind in ("bullet", "ordered", "todo"):
            out.append(_feishu_item(b))
        elif b.kind == "code":


            png = (renders or {}).get(mermaid_key(b.text)) if b.lang == "mermaid" else None
            if png:
                key = mermaid_key(b.text)
                out.append({"block_type": 27, "image": {}, "_asset_bytes": png,
                            "_asset_name": f"mermaid-{key}.png", "_alt": 'Mermaid diagram'})
            code: dict = {"elements": [{"text_run": {"content": c}} for c in _chunks(b.text)]}
            if b.lang and (n := _FEISHU_LANG.get(b.lang)):
                code["style"] = {"language": n}
            out.append({"block_type": 14, "code": code})
            if b.lang == "mermaid" and not png:
                out.append({"block_type": 2, "text": _feishu_text('(The preceding block is Mermaid source. Feishu cannot render it directly. Export again from MEMOKET NOTE to include a rendered diagram.)', italic=True)})
        elif b.kind == "quote":
            out.append({"block_type": 15, "quote": _feishu_text(b.text)})
        elif b.kind == "divider":
            out.append({"block_type": 22, "divider": {}})
        elif b.kind == "table":
            cols = len(b.rows[0])
            cells = [{"block_type": 32, "table_cell": {}, "children": [{"block_type": 2, "text": _feishu_text(c)}]}
                     for row in b.rows for c in row]
            out.append({"block_type": 31, "table": {"property": {"row_size": len(b.rows), "column_size": cols, "header_row": True}},
                        "children": cells})
        elif b.kind == "image":
            m = ASSET_REF.search(b.src) or re.search(r"_assets/([a-f0-9]{24}\.[a-z0-9]+)", b.src)
            if m:
                out.append({"block_type": 27, "image": {}, "_asset": m.group(1), "_alt": b.alt})
            else:
                out.append({"block_type": 2, "text": _feishu_text(f"[Image: {b.alt or 'image'}]（{b.src}）")})
        else:
            out.append({"block_type": 2, "text": _feishu_text(b.text)})
    return out


Call = Callable[..., dict]


class RemoteError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, code: str = ""):
        super().__init__(message)
        self.status, self.code = status, code


def explain_notion(status: int, message: str) -> str:
    msg = (message or "").strip()
    if status == 401:
        return f"Notion rejected the token ({msg or 'unauthorized'}). Copy the Internal Integration Secret from notion.so/profile/integrations."
    if status == 404:
        return (f"Notion could not find the page ({msg}). Check the parent page ID and add the integration under the page's Connections menu.")
    if status == 403:
        return f'Notion denied access ({msg}). Enable Insert content and Update content in the integration capabilities.'
    if status == 429:
        return f'Notion rate-limited the request ({msg}). Retry later.'
    if status == 400:
        return f'Notion rejected the content ({msg}）'
    return f'Notion returned {status}：{msg}'


def explain_feishu(code: int | str, msg: str, helps: str = "") -> str:
    c = str(code)
    hint = f"（{helps}）" if helps else ""
    if c == "10003":
        return 'Feishu rejected the App ID (10003 invalid param). Copy the App ID from the app credentials in the developer console.'
    if c == "10014":
        return 'Feishu rejected the App Secret (10014 app secret invalid). Copy the App Secret from the app credentials in the developer console.'
    if c == "1770039":
        return 'Feishu could not find the folder (1770039). Check the token after /drive/folder/ in the folder URL.'
    if c in ("99991663", "99991664", "99991672", "99991679"):
        return f'The app lacks this permission scope ({c} {msg}). Add docx:document and drive:drive in the developer console and publish the app configuration.'
    if c in ("1770032", "1770033", "1770034", "1770035", "1770002") or "permission" in (msg or "").lower() or "forbidden" in (msg or "").lower():
        return f'Feishu denied access ({c} {msg}). Add the app as an editor of the target folder and grant docx:document and drive:drive.'
    return f'Feishu returned {c}：{msg}{hint}'


def _local_asset(name: str, asset_dir: Path | None, max_size: int) -> Path | None:
    if asset_dir is not None:
        p = asset_dir / name
    else:
        from . import assets as _assets_store
        p = _assets_store.assets_dir() / name
    return p if p.is_file() and p.stat().st_size <= max_size else None


_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


class NotionWriter:
    MAX_IMAGE = 20 * 1024 * 1024

    def __init__(self, token: str, *, call: Call | None = None, version: str = "2026-03-11", asset_dir: Path | None = None):
        self.h = {"Authorization": f"Bearer {token.strip()}", "Notion-Version": version, "Content-Type": "application/json"}
        self._call = call
        self._asset_dir = asset_dir

    def _req(self, method: str, path: str, json: dict | None = None) -> dict:
        if self._call:
            return self._call(method, path, json)
        try:
            if method == "UPLOAD":


                j = dict(json or {})
                data, mime, name = j.pop("_data"), j.pop("_mime"), j.pop("_name")
                h = {k: v for k, v in self.h.items() if k != "Content-Type"}
                r = httpx.post("https://api.notion.com/v1" + path, headers=h, timeout=120,
                               files={"file": (name, data, mime)})
            else:
                r = httpx.request(method, "https://api.notion.com/v1" + path, headers=self.h, json=json, timeout=30)
        except httpx.RequestError as exc:
            raise RemoteError(f'Could not connect to Notion ({exc.__class__.__name__}: {exc}). Check the network or proxy.', status=0, code="network")
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {}


            raise RemoteError(explain_notion(r.status_code, str(body.get("message") or r.text[:200])),
                              status=r.status_code, code=str(body.get("code") or r.status_code))
        return r.json()

    def probe(self) -> None:
        self._req("GET", "/users/me")

    def check_parent(self, page_id: str) -> None:
        self._req("GET", f"/pages/{page_id}")

    def upload_file(self, name: str, data: bytes, mime: str) -> str:
        d = self._req("POST", "/file_uploads", {"filename": name[:200], "content_type": mime})
        fid = str(d.get("id") or "")
        if not fid:
            raise RemoteError('Notion did not assign an upload ID', status=0, code="file_upload")
        self._req("UPLOAD", f"/file_uploads/{fid}/send", {"_data": data, "_mime": mime, "_name": name})
        return fid

    def prepare(self, blocks: list[dict]) -> list[dict]:
        out: list[dict] = []
        for b in blocks:
            if not b.get("_asset"):
                out.append(b)
                continue
            alt = b.get("_alt") or 'image'
            p = _local_asset(b["_asset"], self._asset_dir, self.MAX_IMAGE)
            if not p:
                out.append(_notion_note(f'[Image: {alt}] (file unavailable locally)'))
                continue
            try:
                fid = self.upload_file(p.name, p.read_bytes(), _MIME.get(p.suffix.lower(), "application/octet-stream"))
            except (RemoteError, httpx.HTTPError, KeyError) as exc:
                out.append(_notion_note(f'[Image: {alt}] (Notion upload failed: {exc}）'))
                continue
            out.append({"object": "block", "type": "image",
                        "image": {"type": "file_upload", "file_upload": {"id": fid}}})
        return out

    def create_page(self, parent_page_id: str, title: str, blocks: list[dict]) -> dict:
        blocks = self.prepare(blocks)
        d = self._req("POST", "/pages", {"parent": {"page_id": parent_page_id},
                                          "properties": {"title": {"title": [{"text": {"content": title[:200]}}]}},
                                          "children": blocks[:100]})
        pid = d["id"]
        for i in range(100, len(blocks), 100):
            self._req("PATCH", f"/blocks/{pid}/children", {"children": blocks[i:i + 100]})
            time.sleep(0.34)
        url = str(d.get("url") or "")
        rev = str(d.get("last_edited_time") or "")
        if len(blocks) > 100:
            page = self._req("GET", f"/pages/{pid}")
            rev = str(page.get("last_edited_time") or rev)
        return {"id": pid, "url": url or f"https://www.notion.so/{pid.replace('-', '')}", "rev": rev}

    def replace_children(self, page_id: str, title: str, blocks: list[dict]) -> dict:
        blocks = self.prepare(blocks)
        self._req("PATCH", f"/pages/{page_id}", {"properties": {"title": {"title": [{"text": {"content": title[:200]}}]}}})
        cursor = None
        while True:
            d = self._req("GET", f"/blocks/{page_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else ""))
            for b in d.get("results", []):
                self._req("DELETE", f"/blocks/{b['id']}")
            if not d.get("has_more"):
                break
            cursor = d.get("next_cursor")
        for i in range(0, len(blocks), 100):
            self._req("PATCH", f"/blocks/{page_id}/children", {"children": blocks[i:i + 100]})
        page = self._req("GET", f"/pages/{page_id}")
        return {"id": page_id, "url": str(page.get("url") or f"https://www.notion.so/{page_id.replace('-', '')}"),
                "rev": str(page.get("last_edited_time") or "")}

    def last_edited(self, page_id: str) -> str:
        return str(self._req("GET", f"/pages/{page_id}").get("last_edited_time") or "")


class FeishuWriter:
    BATCH = 300
    MAX_IMAGE = 20 * 1024 * 1024

    def __init__(self, app_id: str, app_secret: str, *, call: Call | None = None, base: str = "https://open.feishu.cn/open-apis",
                 asset_dir: Path | None = None):
        self.app_id, self.app_secret, self.base = app_id.strip(), app_secret.strip(), base
        self._call = call
        self._token = ""
        self._asset_dir = asset_dir

    def _req(self, method: str, path: str, json: dict | None = None, auth: bool = True) -> dict:
        if self._call:
            return self._call(method, path, json)
        headers = {"Authorization": f"Bearer {self.token()}"} if auth else {}
        try:
            if method == "UPLOAD":

                j = dict(json or {})
                data, mime = j.pop("_data"), j.pop("_mime")
                r = httpx.post(self.base + path, headers=headers, timeout=120, data={k: str(v) for k, v in j.items()},
                               files={"file": (j["file_name"], data, mime)})
            else:
                r = httpx.request(method, self.base + path, headers=headers, json=json, timeout=30)
        except httpx.RequestError as exc:
            raise RemoteError(f'Could not connect to Feishu ({exc.__class__.__name__}: {exc}). Check the network or proxy.', status=0, code="network")
        return self._check(r)

    def _check(self, r: httpx.Response) -> dict:
        try:
            d = r.json()
        except ValueError:
            raise RemoteError(f'Feishu returned {r.status_code}：{r.text[:200]}', status=r.status_code, code=str(r.status_code))
        code = d.get("code", 0 if r.status_code < 400 else r.status_code)
        if code != 0:
            helps = ((d.get("error") or {}).get("helps") or [{}])[0].get("description", "")
            raise RemoteError(explain_feishu(code, d.get("msg", ""), helps), status=r.status_code, code=str(code))
        return d

    def token(self) -> str:
        if not self._token:
            d = self._req("POST", "/auth/v3/tenant_access_token/internal",
                          {"app_id": self.app_id, "app_secret": self.app_secret}, auth=False)
            self._token = d.get("tenant_access_token") or ""
            if not self._token:
                raise RemoteError('Feishu rejected this app', status=401, code="no-token")
        return self._token

    def probe(self) -> None:
        self.token()

    def create_document(self, folder_token: str, title: str) -> str:
        d = self._req("POST", "/docx/v1/documents", {"folder_token": folder_token, "title": title[:200]})
        return d["data"]["document"]["document_id"]

    def doc_url(self, doc_id: str) -> str:
        try:
            d = self._req("POST", "/drive/v1/metas/batch_query",
                          {"request_docs": [{"doc_token": doc_id, "doc_type": "docx"}], "with_url": True})
            return str(((d.get("data") or {}).get("metas") or [{}])[0].get("url") or "")
        except (RemoteError, KeyError, IndexError):
            return ""

    def _count_children(self, doc_id: str) -> int:
        n, token = 0, ""
        while True:
            d = self._req("GET", f"/docx/v1/documents/{doc_id}/blocks/{doc_id}/children?page_size=500"
                          + (f"&page_token={token}" if token else ""))
            data = d.get("data") or {}
            n += len(data.get("items") or [])
            if not data.get("has_more"):
                return n
            token = data.get("page_token") or ""
            if not token:
                return n

    @staticmethod
    def flatten(children: list[dict]) -> tuple[list[str], list[dict], list[tuple[str, dict]]]:
        ids: list[str] = []
        flat: list[dict] = []
        images: list[tuple[str, dict]] = []
        seq = 0

        def walk(b: dict) -> str:
            nonlocal seq
            seq += 1
            bid = f"b{seq}"
            node = {k: v for k, v in b.items() if not k.startswith("_") and k != "children"}
            node["block_id"] = bid
            kids = b.get("children") or []
            if kids:
                node["children"] = [walk(k) for k in kids]
            flat.append(node)
            if b.get("_asset") or b.get("_asset_bytes"):
                images.append((bid, b))
            return bid

        for b in children:
            ids.append(walk(b))
        return ids, flat, images

    def _asset_path(self, name: str) -> Path | None:
        return _local_asset(name, self._asset_dir, self.MAX_IMAGE)

    def upload_image(self, doc_id: str, block_id: str, path: Path | None, *,
                     data: bytes | None = None, name: str = "", mime: str = "") -> None:
        if path is not None:
            data, name = path.read_bytes(), path.name
            mime = _MIME.get(path.suffix.lower(), "application/octet-stream")
        assert data is not None and name
        d = self._req("UPLOAD", "/drive/v1/medias/upload_all",
                      {"file_name": name, "parent_type": "docx_image", "parent_node": block_id, "size": len(data), "_data": data, "_mime": mime or "image/png"})
        token = (d.get("data") or {}).get("file_token") or ""
        if token:
            self._req("PATCH", f"/docx/v1/documents/{doc_id}/blocks/{block_id}", {"replace_image": {"token": token}})

    def replace_children(self, doc_id: str, children: list[dict]) -> None:
        while (n := self._count_children(doc_id)):
            self._req("DELETE", f"/docx/v1/documents/{doc_id}/blocks/{doc_id}/children/batch_delete",
                      {"start_index": 0, "end_index": n})

        prepared = []
        for b in children:
            if b.get("_asset") and not self._asset_path(b["_asset"]):
                prepared.append({"block_type": 2, "text": _feishu_text(f"[Image: {b.get('_alt') or 'image'}] (file unavailable locally)")})
            else:
                prepared.append(b)
        def size(b: dict) -> int:
            return 1 + sum(size(k) for k in b.get("children") or [])

        index = 0
        i = 0
        while i < len(prepared):
            j, total = i, 0
            while j < len(prepared) and (j == i or total + size(prepared[j]) <= self.BATCH):
                total += size(prepared[j]); j += 1
            ids, flat, images = self.flatten(prepared[i:j])
            i = j
            d = self._req("POST", f"/docx/v1/documents/{doc_id}/blocks/{doc_id}/descendant",
                          {"children_id": ids, "index": index, "descendants": flat})
            created = (d.get("data") or {}).get("children") or []
            real = {tmp: (created[k] or {}).get("block_id", "") for k, tmp in enumerate(ids) if k < len(created)}
            for tmp, blk in images:
                rid = real.get(tmp)
                if not rid:
                    continue
                if blk.get("_asset_bytes"):
                    self.upload_image(doc_id, rid, None, data=blk["_asset_bytes"],
                                      name=blk.get("_asset_name") or "mermaid.png", mime="image/png")
                    continue
                p = self._asset_path(blk["_asset"])
                if p:
                    self.upload_image(doc_id, rid, p)
            index += len(ids)

    def edited_time(self, doc_id: str) -> str:
        d = self._req("GET", f"/docx/v1/documents/{doc_id}")
        return str((d.get("data") or {}).get("document", {}).get("revision_id") or "")
