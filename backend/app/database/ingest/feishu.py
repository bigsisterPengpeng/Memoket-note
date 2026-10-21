"""Feishu cloud docs -> Markdown (docs/import-sync-plan.md section 1).

Two parts: ``blocks_to_markdown`` is a pure function (docx v1 block structure -> markdown, testable offline);
``FeishuClient`` wraps open-apis (tenant_access_token -> list documents in the knowledge base / drive ->
fetch blocks). The self-built app needs docx:document:readonly, wiki:wiki:readonly, drive:drive:readonly,
and the documents / knowledge base must add the app as a collaborator - the same model as Notion's connect integration.
"""

from __future__ import annotations

import time
from typing import Callable

import httpx

from ...util import i18n

BASE = "https://open.feishu.cn/open-apis"

# block_type of docx v1 (the "block types" table in the official docs)
_HEADINGS = {3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6, 9: 6, 10: 6, 11: 6}
_TYPE_KEY = {1: "page", 2: "text", 12: "bullet", 13: "ordered", 14: "code", 15: "quote",
             17: "todo", 19: "callout", 22: "divider", 27: "image", 31: "table", 32: "table_cell"}
for _t, _lvl in _HEADINGS.items():
    _TYPE_KEY[_t] = f"heading{_t - 2}"


# Feishu docx code-block language enum -> markdown language name (the few dozen common ones from the
# official "code block languages" table; unrecognized ones get no language, no guessing). The
# writing side is `exporters._FEISHU_LANG`; the two tables must match.
_CODE_LANG = {
    1: "", 8: "c", 9: "cpp", 10: "csharp", 12: "css", 17: "go", 22: "html",
    24: "java", 25: "javascript", 26: "json", 28: "kotlin", 29: "latex", 30: "lua",
    31: "makefile", 32: "markdown", 36: "objectivec", 40: "php", 43: "python",
    45: "r", 49: "ruby", 50: "rust", 51: "scala", 52: "scheme", 53: "shell",
    54: "sql", 55: "swift", 58: "typescript", 60: "xml", 61: "yaml", 63: "bash",
}


def _inline(elements: list[dict] | None) -> str:
    out = []
    for el in elements or []:
        tr = el.get("text_run")
        if tr:
            s = tr.get("content") or ""
            st = tr.get("text_element_style") or {}
            if st.get("inline_code"):
                s = f"`{s}`"
            if st.get("bold"):
                s = f"**{s}**"
            if st.get("italic"):
                s = f"*{s}*"
            if st.get("strikethrough"):
                s = f"~~{s}~~"
            link = (st.get("link") or {}).get("url")
            if link:
                s = f"[{s}]({link})"
            out.append(s)
        elif el.get("mention_doc"):
            out.append(el["mention_doc"].get("title") or "")
        elif el.get("mention_user"):
            out.append("@" + (el["mention_user"].get("name") or el["mention_user"].get("user_id") or ""))
        elif el.get("equation"):
            out.append(f"${el['equation'].get('content', '')}$")
    return "".join(out)


def blocks_to_markdown(blocks: list[dict]) -> str:
    """All blocks of one document (flat list, with parent_id / children) -> markdown. The title block (page) itself does not go into the body."""
    by_id = {b.get("block_id"): b for b in blocks if b.get("block_id")}
    root = next((b for b in blocks if b.get("block_type") == 1), None)
    order = root.get("children") or [] if root else [b["block_id"] for b in blocks if b.get("parent_id") in ("", None)]
    lines: list[str] = []
    counters: dict[str, int] = {}

    def gap() -> None:
        """Leave a blank line before block-level elements.

        **Anything right after a list item is swallowed by markdown as that item's continuation** - the round-trip
        test (round 649, real account) hit it twice in a row: `> quote` right after `- second list item`, and a plain
        paragraph right after `2. second ordered item`. No blank line between list items (those should be tight anyway).
        """
        if lines and lines[-1].strip():
            lines.append("")

    def render(bid: str, depth: int = 0) -> None:
        b = by_id.get(bid)
        if not b:
            return
        t = b.get("block_type")
        key = _TYPE_KEY.get(t, "")
        body = b.get(key) or {}
        indent = "  " * depth
        if t in _HEADINGS:
            gap()
            lines.append(f"{'#' * _HEADINGS[t]} {_inline(body.get('elements'))}")
            lines.append("")
        elif t == 2:
            gap()
            lines.append(indent + _inline(body.get("elements")))
            lines.append("")
        elif t == 12:
            lines.append(f"{indent}- {_inline(body.get('elements'))}")
        elif t == 13:
            n = counters.get(b.get("parent_id", ""), 0) + 1
            counters[b.get("parent_id", "")] = n
            lines.append(f"{indent}{n}. {_inline(body.get('elements'))}")
        elif t == 17:
            done = (body.get("style") or {}).get("done")
            lines.append(f"{indent}- [{'x' if done else ' '}] {_inline(body.get('elements'))}")
        elif t == 14:

            # ```python exported and imported back became a bare ``` - the code block lost
            # highlighting, once more per re-import.
            gap()
            lang = _CODE_LANG.get((body.get("style") or {}).get("language"), "")
            lines.append("```" + lang)
            lines.append(_inline(body.get("elements")))
            lines.append("```")
            lines.append("")
        elif t == 15:
            gap()
            lines.append(f"> {_inline(body.get('elements'))}")
            lines.append("")
        elif t == 19:
            for cid in b.get("children") or []:
                render(cid, depth)
            return
        elif t == 22:
            gap()
            lines.append("---")
            lines.append("")
        elif t == 27:
            gap()
            lines.append(f"![{i18n.msg('image')}]({body.get('token', '')})")
            lines.append("")
        elif t == 31:
            prop = body.get("property") or {}
            cols = int(prop.get("column_size") or 0)
            cells = body.get("cells") or []
            if cols and cells:
                rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
                def cell_text(cid: str) -> str:
                    c = by_id.get(cid) or {}
                    parts = []
                    for kid in c.get("children") or []:
                        kb = by_id.get(kid) or {}
                        kk = _TYPE_KEY.get(kb.get("block_type"), "")
                        parts.append(_inline((kb.get(kk) or {}).get("elements")))
                    return " ".join(p for p in parts if p).replace("|", "\\|")
                for ri, row in enumerate(rows):
                    lines.append("| " + " | ".join(cell_text(c) for c in row) + " |")
                    if ri == 0:
                        lines.append("|" + "---|" * cols)
                lines.append("")
            return
        elif t == 32:
            return
        # child blocks (nested lists etc.)
        for cid in b.get("children") or []:
            if t in (12, 13, 17):
                render(cid, depth + 1)
            elif t not in (31,):
                render(cid, depth)
        if t in (12, 13, 17) and depth == 0:
            # no blank line between top-level list items; after a list ends the next paragraph
            # brings the blank line
            pass

    for bid in order:
        render(bid)
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip() + "\n"


def page_title(blocks: list[dict]) -> str:
    root = next((b for b in blocks if b.get("block_type") == 1), None)
    return _inline((root or {}).get("page", {}).get("elements")).strip() if root else ""


class FeishuClient:
    """Minimal client. ``get`` is injectable (a fake one in tests), httpx by default."""

    def __init__(self, app_id: str, app_secret: str, *, base: str = BASE,
                 get: Callable[..., dict] | None = None, post: Callable[..., dict] | None = None):
        self.app_id, self.app_secret, self.base = app_id.strip(), app_secret.strip(), base
        self._get, self._post = get, post
        self._token = ""

    # -- HTTP --
    def _do_post(self, path: str, json: dict) -> dict:
        if self._post:
            return self._post(path, json)
        r = httpx.post(self.base + path, json=json, timeout=30)
        r.raise_for_status()
        return r.json()

    def _do_get(self, path: str, params: dict | None = None) -> dict:
        if self._get:
            return self._get(path, params or {})
        r = httpx.get(self.base + path, params=params, timeout=60,
                      headers={"Authorization": f"Bearer {self.token()}"})
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _ok(d: dict, what: str) -> dict:
        if d.get("code", 0) != 0:
            raise RuntimeError(i18n.msg("Feishu {what} failed: {code} {msg}", what=what, code=d.get('code'), msg=d.get('msg', '')))
        return d.get("data") or {}

    def token(self) -> str:
        if not self._token:
            d = self._do_post("/auth/v3/tenant_access_token/internal", {"app_id": self.app_id, "app_secret": self.app_secret})
            if d.get("code", 0) != 0 or not d.get("tenant_access_token"):
                raise RuntimeError(i18n.msg("Feishu rejected this app: {code} {msg}", code=d.get('code'), msg=d.get('msg', '')))
            self._token = d["tenant_access_token"]
        return self._token

    # -- listing documents --
    def list_wiki_docs(self, limit: int = 0) -> list[dict]:
        """docx nodes in all knowledge-base spaces: {document_id, title, created, edited}."""
        out: list[dict] = []
        spaces = self._ok(self._do_get("/wiki/v2/spaces", {"page_size": 50}), i18n.msg("listing knowledge bases")).get("items") or []
        for sp in spaces:
            stack = [""]
            while stack and (not limit or len(out) < limit):
                parent = stack.pop()
                page_token = ""
                while True:
                    params = {"page_size": 50}
                    if parent:
                        params["parent_node_token"] = parent
                    if page_token:
                        params["page_token"] = page_token
                    d = self._ok(self._do_get(f"/wiki/v2/spaces/{sp['space_id']}/nodes", params), i18n.msg("listing nodes"))
                    for n in d.get("items") or []:
                        if n.get("has_child"):
                            stack.append(n["node_token"])
                        if n.get("obj_type") == "docx":
                            out.append({"document_id": n["obj_token"], "title": n.get("title") or "",
                                        "created": n.get("obj_create_time") or "", "edited": n.get("obj_edit_time") or ""})
                    if not d.get("has_more"):
                        break
                    page_token = d.get("page_token") or ""
                    time.sleep(0.2)
        return out[:limit] if limit else out

    def list_drive_docs(self, limit: int = 0, folder: str = "") -> list[dict]:
        """docx files in the drive (my space), recursing into subfolders."""
        out: list[dict] = []
        stack = [folder]
        while stack and (not limit or len(out) < limit):
            cur = stack.pop()
            page_token = ""
            while True:
                params = {"page_size": 50}
                if cur:
                    params["folder_token"] = cur
                if page_token:
                    params["page_token"] = page_token
                d = self._ok(self._do_get("/drive/v1/files", params), i18n.msg("listing files"))
                for f in d.get("files") or []:
                    if f.get("type") == "folder":
                        stack.append(f["token"])
                    elif f.get("type") == "docx":
                        out.append({"document_id": f["token"], "title": f.get("name") or "",
                                    "created": f.get("created_time") or "", "edited": f.get("modified_time") or ""})
                if not d.get("has_more"):
                    break
                page_token = d.get("next_page_token") or ""
                time.sleep(0.2)
        return out[:limit] if limit else out

    # The token part of a link: `https://xxx.feishu.cn/docx/<token>` / `/wiki/<token>`, possibly
    # followed by `?from=...` or `#anchor`. A bare token is accepted too.
    _REF = __import__("re").compile(r"(?:/(docx|wiki|docs)/)?([A-Za-z0-9]{16,32})(?:[?#].*)?$")

    def resolve_doc(self, ref: str) -> dict:
        """A link / token -> `{document_id, title}`.

        **Why this path exists**: Feishu authorizes per document, while the "list" path requires the app to be
        a member of the knowledge-base space. Measured (round 649, real account): a wiki document with the app added
        as a collaborator on the document itself could be read by `get_node`, yet `/wiki/v2/spaces` listed not a single
        space - **readable but not listable**. Being able to paste a link is what makes this feature work for "people who are not admins".
        """
        m = self._REF.search((ref or "").strip())
        if not m:
            raise RuntimeError(i18n.msg("Cannot tell which document this is: {ref}", ref=ref[:40]))
        kind, token = m.group(1), m.group(2)
        if kind == "wiki":
            node = self._ok(self._do_get("/wiki/v2/spaces/get_node", {"token": token}), i18n.msg("looking up the node")).get("node") or {}
            if node.get("obj_type") != "docx":
                raise RuntimeError(i18n.msg("This is a \"{kind}\"; only documents (docx) can be imported", kind=node.get('obj_type') or i18n.msg('unknown type')))
            return {"document_id": node.get("obj_token") or "", "title": node.get("title") or ""}
        return {"document_id": token, "title": ""}

    def document_blocks(self, document_id: str) -> list[dict]:
        blocks: list[dict] = []
        page_token = ""
        while True:
            params = {"page_size": 500, "document_revision_id": -1}
            if page_token:
                params["page_token"] = page_token
            d = self._ok(self._do_get(f"/docx/v1/documents/{document_id}/blocks", params), i18n.msg("fetching the document content"))
            blocks += d.get("items") or []
            if not d.get("has_more"):
                break
            page_token = d.get("page_token") or ""
        return blocks


def epoch_to_date(v: str | int | None) -> str:
    """Feishu gives second-level unix timestamp strings; unrecognized gives an empty string (_land falls back to today, no guessing)."""
    try:
        n = int(str(v or "").strip())
    except ValueError:
        return ""
    if n <= 0:
        return ""
    if n > 10**11:          # milliseconds
        n //= 1000
    return time.strftime("%Y-%m-%d", time.localtime(n))
