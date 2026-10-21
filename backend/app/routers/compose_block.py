"""Streaming block-writing actions. Adapters provide surrounding text, task state and the appropriate mode."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from ..database import store
from ..harness import tools
from ..util import llm
from ..editor import vision
from ..editor import restructure, textshape
from ..editor.preconditions import note_precondition
from ..editor import intent as doc_intent
from ..harness import loop, modes, score_context
from ..harness.events import to_sse
from ..harness.hooks.block import BlockHooks
from ..harness.state import State
from ..editor.profile import entries as _profile
from .schemas import ComposeBlockIn
from .deps import current_user, sse_response

router = APIRouter(prefix="/api/compose", tags=["compose"])

def _context_block(content: str, cursor: int, span: int = 900) -> tuple[str, str]:
    cur = max(0, min(cursor, len(content)))
    return content[max(0, cur - span):cur], content[cur:cur + span // 2]


MAX_PROMPT_CHARS = 2000


PROMPT_REQUIRED = ("prompt", "custom", "analysis")


def block_precondition(mode: str, prompt: str, selection: str) -> str:
    p = (prompt or "").strip()
    if mode in PROMPT_REQUIRED and not p:


        return ('Say what it should do first.' if mode != "custom"
                else 'Say what to do with the selected text — with nothing written, it cannot know what to change.')
    if mode == "custom" and not (selection or "").strip():
        return 'Nothing is selected — select some text first, then right-click “Custom prompt”.'
    if len(p) > MAX_PROMPT_CHARS:
        return f'The instruction is too long ({len(p)} characters, limit {MAX_PROMPT_CHARS}) — one sentence is enough; no need to paste the text in.'
    return ""


@router.post("/block")
async def compose_block(body: ComposeBlockIn, request: Request,
                        user: str = Depends(current_user)):
    mode = modes.BLOCK.get(body.mode)
    if not mode:
        raise HTTPException(
            400, f"Unknown mode {body.mode!r}; available: {'、'.join(modes.BLOCK)}")


    reason = block_precondition(body.mode, body.prompt, body.selection)
    if reason:
        raise HTTPException(400, reason)

    tray = store.list_tray(user, body.note_id) if body.note_id else []
    if body.from_tray and not tray:
        raise HTTPException(400, "Add notes or facts from the Memory pane before choosing Write with this note's material.")

    async def gen():
        before, after = _context_block(body.content, body.cursor)
        st = State(
            mode=mode,
            ctx=tools.ToolContext(user=user, note_id=body.note_id, scope=body.scope,
                                  note_title=body.title,
                                  content=body.content, cursor=body.cursor,
                                  intent=body.intent, tray=tray),
            request=request,
            before=before,
            after=after,
        )


        st.bag["score_context"] = score_context.for_block(
            before=before, after=after,
            prompt=body.prompt, selection=body.selection)
        hooks = BlockHooks(prompt=body.prompt, selection=body.selection,
                           profile=_profile(user), title=body.title, from_tray=body.from_tray)

        st.bag.update(prompt=body.prompt, selection=body.selection,
                      profile=_profile(user), from_tray=body.from_tray)
        async for event in loop.run(st, hooks):
            yield to_sse(event)

    return sse_response(gen())


_TABLE_PROMPT = """Inspect the image. If it contains a table or aligned data that can be tabulated, such as a
receipt, report or statistics screenshot, transcribe the complete content into a Markdown table.
Use a header row followed by one row per record. Output only the table. Use ? for unreadable
cells; never guess. If no tabular data is present, return only: No table."""


@router.post("/table-from-image")
async def table_from_image(file: UploadFile = File(...),
                           user: str = Depends(current_user)) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(400, 'The file is empty')
    if len(data) > 16 * 1024 * 1024:
        raise HTTPException(400, 'The image exceeds the 16 MB limit')
    mime = (file.content_type or "image/png").split(";")[0].strip()
    if not mime.startswith("image/"):
        raise HTTPException(400, f'This is not an image ({mime}）')
    try:
        out = await vision.ask_image(_TABLE_PROMPT, data, mime)
    except vision.VisionError as exc:
        raise HTTPException(502, str(exc)) from exc

    text = (out or "").strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    rows = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    detected = len(rows) >= 2 and any(set(ln) <= set("|-: ") for ln in rows[1:2])
    if not detected:
        return {"detected": False, "table": "", "raw": text[:300]}
    return {"detected": True, "table": "\n".join(rows), "raw": ""}


_RESTRUCTURE_SYSTEM = """Organize the note's structure. Decide which numbered lines should be headings,
lists, quotations or plain paragraphs. Do not output or rewrite body text: code
will preserve each original line and apply only the requested structural markers.

Return a JSON array using these operations:
{"op":"heading","line":3,"level":2}
{"op":"list","line":5,"indent":0}
{"op":"ordered","line":5}
{"op":"quote","line":9}
{"op":"paragraph","line":9}
{"op":"split","line":12}
{"op":"insert_heading","before":1,"level":2,"text":"Release cadence"}

Use split when a line contains at least three explicitly numbered parallel items.
Code determines the split boundaries; specify only the line.
insert_heading is the only operation that adds words: keep its title within
40 characters and summarize the actual following content, without a new claim.
Do not modify lines marked as code-block content or boundaries, or table rows.
Omit unchanged lines. Return [] if no changes are useful. Output only JSON."""


@router.post("/restructure")
async def restructure_note(body: ComposeBlockIn, user: str = Depends(current_user)) -> dict:
    src = body.content or ""
    if why := note_precondition("restructure", src):
        raise HTTPException(400, why)
    try:
        text = await llm.complete(
            [{"role": "system", "content": doc_intent.block(body.intent) + _RESTRUCTURE_SYSTEM},
             {"role": "user", "content": restructure.numbered(src)}],
            max_tokens=1500, temperature=0.1)
    except Exception as exc:                       # noqa: BLE001
        raise HTTPException(502, f'Restructuring request failed: {llm.describe_error(exc)}') from exc

    ops = llm.extract_json(text)
    if not isinstance(ops, list):
        return {"changed": False, "content": src, "ops": 0, "skipped": [],
                "detail": 'The model did not return a valid operation list'}
    out, skipped = restructure.apply_ops(src, ops)
    drift = textshape.content_drift(src, out)
    if drift:


        return {"changed": False, "content": src, "ops": 0,
                "skipped": skipped + ['Content changed during restructuring; discarded the result'],
                "detail": drift[:200]}
    return {"changed": out != src, "content": out, "ops": len(ops),
            "skipped": skipped, "detail": ""}
