"""Multi-note writing plans: ordered sections, progress tracking and resumable execution."""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Request

from ..harness import prompts
from ..database import store
from ..harness import tools
from ..util import llm
from ..harness import loop, modes
from ..harness.events import EventType, to_sse, sse as _sse
from ..harness.hooks.section import SectionHooks
from ..harness.state import State
from ..editor.profile import entries as _profile
from ..database.retrieval import retrieve as _retrieve
from .schemas import WritingPlanOut, WritingPlanRunIn, WritingPlanStartIn
from .deps import current_user, sse_response


PLAN_SOURCE = "plan"

router = APIRouter(prefix="/api/writing-plan", tags=["writing-plan"])

TRACKING_NOTE_TITLE = '📋 Writing tracker'


PLAN_SAFETY_CAP = 300


def _make_summary(title: str, content: str) -> str:
    text = content.strip()
    if not text:
        return f'{title} (empty)'
    headings = [
        line.strip().lstrip("#").strip()
        for line in text.splitlines()
        if line.strip().startswith("#")
    ]
    parts = [f"《{title}》"]
    if headings:
        parts.append('Covers: ' + "、".join(headings[:8]))
    tail = [p for p in text.split("\n\n") if p.strip()]
    if tail:
        parts.append(tail[-1].strip()[:120])
    return " ｜ ".join(parts)


def _score_context(section_title: str, goal: str,
                   other_summaries: list[str]) -> dict[str, str]:
    """What the scorer needs to know beyond the text itself.

    Facts are *not* in here. The loop passes the run's accumulated material
    to ``evaluate`` directly, which is the fix for a bug both long-form
    harnesses had: retrieval ran separately in the write step, the revise
    step and the scoring step, so the scorer judged the text against a third
    batch of facts and reported "not found in the knowledge base" about
    material the writer had just used.
    """
    ctx = {'Section topic': section_title}
    if goal:
        ctx['Overall writing goal'] = goal
    if other_summaries:
        ctx['Summaries of completed sections'] = "\n".join(f"- {s}" for s in other_summaries)
    return ctx


def _sync_tracking_note(user: str, plan: dict, sections: list[dict]) -> None:
    doc = prompts.render_tracking_doc(plan["goal"], plan["status"], sections)
    if plan.get("doc_note_id"):
        existing = store.get_note(user, plan["doc_note_id"])
        if existing:

            store.update_note(user, plan["doc_note_id"], TRACKING_NOTE_TITLE, doc,
                              source="harness")
            return


    note = store.create_note(user, TRACKING_NOTE_TITLE, doc, plan["parent_note_id"],
                             source=PLAN_SOURCE)
    store.set_plan_doc_note(user, plan["id"], note["id"])
    plan["doc_note_id"] = note["id"]


@router.get("", response_model=WritingPlanOut)
def get_plan(parent_note_id: str, user: str = Depends(current_user)):
    plan = store.get_active_plan(user, parent_note_id)
    if not plan:
        return WritingPlanOut()
    return WritingPlanOut(plan=plan, sections=store.list_sections(plan["id"]))


@router.post("/start", response_model=WritingPlanOut)
async def start_plan(body: WritingPlanStartIn, user: str = Depends(current_user)):
    goal = body.goal.strip()
    if not goal:
        raise HTTPException(400, "goal required")
    if body.parent_note_id != store.ROOT_ID and not store.get_note(user, body.parent_note_id):
        raise HTTPException(404, 'Parent node not found')

    facts, _ids, _took = _retrieve(user, goal, "", [], limit=8, scope=body.scope)
    sibling_notes = store.child_notes(user, body.parent_note_id, limit=8)
    folder_ctx = prompts.folder_context_block(sibling_notes)

    plan_system = prompts.compose_system(prompts.PLAN_SYSTEM, "plan_generate", user)
    parsed = await llm.complete_json(
        [{"role": "system", "content": plan_system},
         {"role": "user", "content": prompts.plan_user(goal, facts, folder_ctx)}],
        max_tokens=600, temperature=0.4)
    titles = [str(t).strip() for t in parsed if str(t).strip()] if isinstance(parsed, list) else []
    if not titles:
        raise HTTPException(502, 'The model did not return a valid section list. Try another goal description.')

    plan = store.create_plan(user, body.parent_note_id, goal)
    sections = store.add_sections(plan["id"], titles)
    _sync_tracking_note(user, plan, sections)
    return WritingPlanOut(plan=plan, sections=sections)


@router.post("/run")
async def run_plan(body: WritingPlanRunIn, request: Request, user: str = Depends(current_user)):
    plan = store.get_active_plan(user, body.parent_note_id)
    if not plan:
        raise HTTPException(404, "no active plan for this folder")

    async def gen():
        sections = store.list_sections(plan["id"])
        yield _sse("plan-loaded", {"plan": plan, "sections": sections})

        steps = 0
        while steps < PLAN_SAFETY_CAP:
            steps += 1
            if await request.is_disconnected():
                break

            sections = store.list_sections(plan["id"])
            target = next((s for s in sections if s["status"] in ("pending", "in_progress")), None)

            if target is None:
                done_summaries = [s["summary"] for s in sections if s["summary"]]
                facts, _ids, _took = _retrieve(user, plan["goal"], "", [], limit=8, scope=body.scope)
                sibling_notes = store.child_notes(user, body.parent_note_id, limit=8)
                folder_ctx = prompts.folder_context_block(sibling_notes)
                more_system = prompts.compose_system(
                    prompts.MORE_SECTIONS_SYSTEM, "more_sections", user)
                try:
                    parsed = await llm.complete_json(
                        [{"role": "system", "content": more_system},
                         {"role": "user", "content": prompts.more_sections_user(
                             plan["goal"], done_summaries, facts, folder_ctx)}],
                        max_tokens=400, temperature=0.4)
                    more = [str(t).strip() for t in parsed if str(t).strip()] if isinstance(parsed, list) else []
                except Exception as exc:


                    yield _sse("error", {"detail": f'Could not determine whether more sections are needed; retry: {exc}'})
                    continue

                if not more:
                    store.set_plan_status(user, plan["id"], "done")
                    plan["status"] = "done"
                    _sync_tracking_note(user, plan, sections)
                    yield _sse("plan-done", {"plan": plan})
                    break

                new_sections = store.add_sections(plan["id"], more)
                if not new_sections:


                    store.set_plan_status(user, plan["id"], "done")
                    plan["status"] = "done"
                    _sync_tracking_note(user, plan, sections)
                    yield _sse("plan-done", {"plan": plan, "reason": 'Proposed sections duplicate existing ones, or the section limit was reached'})
                    break
                _sync_tracking_note(user, plan, sections + new_sections)
                yield _sse("plan-extended", {"sections": new_sections})
                continue

            note = store.get_note(user, target["note_id"]) if target["note_id"] else None
            is_new_note = note is None
            if is_new_note:
                note = store.create_note(user, target["title"], "", body.parent_note_id,
                                         source=PLAN_SOURCE)
            if target["status"] != "in_progress" or is_new_note:
                store.update_section(plan["id"], target["id"], status="in_progress", note_id=note["id"])
            target = {**target, "status": "in_progress", "note_id": note["id"]}

            other_summaries = [s["summary"] for s in sections
                               if s["id"] != target["id"] and s["summary"]]
            sibling_notes = store.child_notes(
                user, body.parent_note_id, exclude_id=note["id"], limit=6)

            # One section = one harness run. Rounds, material accumulation,
            # dedup, the repair-vs-continue policy, scoring, best-of and the
            # stop conditions are all in the shared loop now; this function
            # only decides *which* section runs next and what happens to the
            # plan when one finishes.
            st = State(
                mode=modes.for_run(modes.SECTION, has_profile=bool(_profile(user))),
                ctx=tools.ToolContext(user=user, note_id=note["id"],
                                      note_title=target["title"], scope=body.scope),
                request=request,
                content=note["content"],
            )
            st.bag["score_context"] = _score_context(
                target["title"], plan["goal"], other_summaries)
            folder_ctx = prompts.folder_context_block(sibling_notes)
            hooks = SectionHooks(
                goal=plan["goal"], other_summaries=other_summaries,
                folder_ctx=folder_ctx, profile=_profile(user))

            st.bag.update(goal=plan["goal"], other_summaries=other_summaries,
                          folder_ctx=folder_ctx, profile=_profile(user))

            yield _sse("section-start", {
                "section_id": target["id"], "title": target["title"],
                "note_id": note["id"], "is_new_note": is_new_note,
            })

            reason = "max_rounds"
            async for event in loop.run(st, hooks):
                if event.type is EventType.RUN_FINISHED:
                    reason = event.data.get("reason", reason)
                yield to_sse(event)

            summary = _make_summary(target["title"], st.content)
            store.update_section(plan["id"], target["id"], status="done",
                                 summary=summary)
            yield _sse("section-done", {
                "section_id": target["id"], "summary": summary,
                "reason": reason,
                "forced": reason == "max_rounds",
                "material_used_up": reason == "material_used_up",
                "blocked": reason == "blocked",
                "blocked_reason": (st.ev.blocked_reason
                                   if reason == "blocked" and st.ev else None),
            })
            sections = store.list_sections(plan["id"])
            _sync_tracking_note(user, plan, sections)

        yield _sse("done", {})

    return sse_response(gen())


@router.post("/{parent_note_id}/abandon")
def abandon_plan(parent_note_id: str, user: str = Depends(current_user)):
    plan = store.get_active_plan(user, parent_note_id)
    if not plan:
        raise HTTPException(404, "no active plan for this folder")
    store.set_plan_status(user, plan["id"], "abandoned")
    return {"abandoned": plan["id"]}
