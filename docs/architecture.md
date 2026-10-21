# Architecture

MEMOKET NOTE is an agent-native writing workspace built on
[memoket-kite](https://github.com/memoket/memoket-kite). The application owns the
editing and task state. Its writing agent harness coordinates tools, iterative
drafting, quality checks, stopping conditions and recovery. KITE supplies the
memory engine.

## Application boundaries

| Layer | Main paths | Responsibility |
|---|---|---|
| React interface | `frontend/src/components/` | Note navigation, task controls, source inspection and edit review |
| CodeMirror editor | `frontend/src/editor/` | Document transactions, selections, generated blocks and change rendering |
| FastAPI application | `backend/app/routers/` | Request validation, streamed progress and operation boundaries |
| Writing agent harness | `backend/app/harness/` | Shared run loop, modes, tools, checks, policy and recovery |
| Persistence | `backend/app/database/` | Notes, task state, revisions, knowledge metadata and KITE adapters |
| Desktop shell | `desktop/src/` | Electron windows, permissions and backend process lifecycle |

The frontend talks to the local API. During web development Vite proxies `/api`
to the backend. The desktop package starts a bundled backend and loads the built
frontend. The backend can call user-configured model and transcription services.

## Writing task lifecycle

A run carries the note, goal, current content, selected evidence, round state,
quality feedback and execution policy. Task modes configure the shared loop
rather than copying it into separate implementations.

1. A router validates the task and builds its initial context.
2. Hooks prepare task-specific evidence and generation inputs.
3. Middleware records and transforms run state around lifecycle events.
4. Generation or revision proposes content.
5. Deterministic checks inspect constraints that code can evaluate.
6. A configured judge scores writing dimensions against the supplied evidence.
7. Policy selects another round, repair, pause or a stopping condition.
8. The application persists progress and exposes proposed changes for review.

See `harness/loop.py`, `harness/modes.py`, `harness/hooks/` and
`harness/middleware/`. Structured event types and runtime state live in
`harness/types.py` and `harness/state.py`.

## Evidence and scoring context

Retrieval and explicitly selected tray material feed the run's evidence set.
Generation and scoring must use that same accumulated material. Scoring must not
perform a separate retrieval and then penalize the writer for evidence it never
received.

`harness/score_context.py` shares context-window limits between generation and
scoring. Correction notices survive evidence truncation. Changing material and
newly generated text follow the stable prompt prefix. For long notes, the judge
can receive summaries of older sections and recent sections verbatim, while
code checks still inspect the complete text.

Pre-run user content is distinct from sentences introduced by the current run.
A missing retrieved fact does not establish that the user's existing text is
invented. The harness must preserve this distinction during evaluation and repair.

## Memory integration

`database/kite/` adapts the external `memoket-kite` package for application use.
`database/kb/` provides application-level retrieval, browsing, entity and topic
behavior. Harness memory tools expose selected operations to a run, while the UI
lets a person inspect facts and source evidence directly.

Fact identifiers and source links connect recalled material to citations in the
note. A retrieval result is evidence to examine. It is not an automatic assertion
that every generated interpretation of that evidence is correct.

## Change review and recovery

Generated edits are represented through revisions and change layers. The editor
supports individual hunk decisions, while stored run rounds and snapshots support
recovery. A later round can be worse than an earlier one; the harness can deliver
the earlier best result when its policy calls for that behavior.

The relevant paths include `frontend/src/editor/roundDiff.ts`,
`frontend/src/components/ChangeLayersPanel.tsx`, `backend/app/harness/snapshot.py`
and the persistence methods under `backend/app/database/`.

## Provider and trust boundaries

Provider configuration belongs to the user. Local model endpoints can keep
processing on a trusted machine or network. Hosted model and transcription
features send relevant content to the configured provider.

The API targets a trusted local environment. `X-User-Id` selects application data;
it is not an authentication mechanism. Review [SECURITY.md](../SECURITY.md) before
changing network exposure or deploying a shared service.

## Validation boundaries

Unit and contract tests use stubs for model behavior. They check state transitions,
request wiring, document transformations and known regression cases. They do not
prove real-model writing quality, provider account compatibility or visual fit in
every window size. Those require separate end-to-end and visual verification.
