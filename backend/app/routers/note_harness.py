from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends, HTTPException, Request

from ..database import store
from ..editor import intent as doc_intent
from ..editor import style_anchors
from ..harness import tools
from ..harness import feedback, loop, modes, workflows
from ..harness.events import to_sse
from ..harness.hooks.note import NoteHooks
from ..harness.round_snapshot import with_round_snapshots
from ..harness.state import State
from ..editor.profile import entries as _profile
from .schemas import NoteHarnessRunIn
from .deps import current_user, sse_response

router = APIRouter(prefix="/api/note-harness", tags=["note-harness"])

# The request may ask for more rounds than this; it does not get them. Every
# other limit -- how many rounds a mode wants, when to stall, when the
# material runs out -- is Mode data or a stop condition, and lives with the
# rest of the configuration in harness/modes.py.
MAX_ROUNDS_CAP = 30


def rounds_for(requested: int | None, mode) -> int:
    return max(1, min(requested or mode.max_rounds, MAX_ROUNDS_CAP))


def _score_context(st: State) -> dict[str, str]:
    """Assemble note structure, task contracts and preference evidence for the judge."""
    ctx: dict[str, str] = {}
    spine, beats = st.bag.get("spine", ""), st.bag.get("beats") or []
    if spine:
        ctx['Core tension'] = spine
    if beats:
        ctx['Structural beats'] = "\n".join(f"- {b}" for b in beats)
    if st.bag.get("outline_mode"):
        # In outline mode the headings are the **user's**, not part of the
        # output. Without saying so the scorer marks them down: three rounds


        # user supplied, and a hard guard elsewhere guarantees it cannot be
        # changed. Penalised and unfixable is a loop that can only spin.
        ctx['User-defined heading structure'] = (
            "All headings belong to the user's outline. This task only fills their bodies. **Do"
            " not judge heading levels, wording or order**: they express the user's intent and "
            'are outside the generated output. Judge only the section bodies.'
        )
    if contract := workflows.quality_contract(st.ctx.intent):
        ctx['Workflow quality contract'] = contract
    if block := feedback.context_block(st.bag.get("writing_feedback")):
        ctx['Past user edit decisions'] = block
    if anchors := st.bag.get("style_anchors"):
        ctx['User writing samples'] = ((
            'Judge only tone, sentence length, rhythm and organization against these samples. '
            'Facts in the samples do not belong to the current note.\n\n'
        )
                                      + "\n\n".join(str(x) for x in anchors[:3]))
    return ctx


@router.post("/run")
async def run(body: NoteHarnessRunIn, request: Request,
              user: str = Depends(current_user)):
    note = store.get_note(user, body.note_id)
    if not note:
        raise HTTPException(404, "note not found")

    polish = body.mode == "polish"
    run_intent = body.intent or doc_intent.as_text(note.get("intent") or {})
    anchors = style_anchors.entries(user, note, doc_intent.workflow_of(run_intent))
    if not polish and not doc_intent.goal_of(run_intent):


        raise HTTPException(
            422,
            'Smart continuation requires an explicitly selected writing workflow or a custom goal',
        )

    async def gen():
        st = State(
            mode=dataclasses.replace(
                modes.for_run(modes.NOTE, has_profile=bool(_profile(user) or anchors),
                              polish=polish),
                max_rounds=rounds_for(body.max_rounds, modes.NOTE),
                review_each_round=body.review_each_round),
            ctx=tools.ToolContext(user=user, note_id=body.note_id, scope=body.scope,
                                  note_title=note["title"],

                                  intent=run_intent,

                                  intent_checked=tuple(doc_intent.normalize(note.get("intent") or {})["checked"]),

                                  tray=store.list_tray(user, body.note_id)),
            request=request,
            content=body.content,
        )
        hooks = NoteHooks(polish=polish, spine=body.spine, beats=body.beats,
                          profile=_profile(user))


        st.bag["polish"] = polish


        st.bag["writing_feedback"] = store.writing_feedback(user, body.note_id)
        st.bag["style_anchors"] = anchors

        # The skeleton is established before the loop starts: a failure here
        # has to be reportable without a round having begun, and every round
        # after it reads spine/beats out of the bag.
        async for event in hooks.skeleton(st):
            yield to_sse(event)

        st.bag["score_context"] = _score_context(st)


        async for event in with_round_snapshots(loop.run(st, hooks), st):
            yield to_sse(event)

    return sse_response(gen())
