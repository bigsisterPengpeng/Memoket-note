# Agent-native writing workspace

An English conceptual introduction to MEMOKET NOTE, a personal project built on [memoket-kite](https://github.com/memoket/memoket-kite).

[Watch or download the video](agent-native-writing-workspace.mp4) · [English captions](agent-native-writing-workspace.en.vtt)

This video explains the architecture. It uses synthetic English narration and typographic scenes rather than a live application recording. Model output still needs human review.

## Transcript

### 00:00:00 — Agent-native writing workspace

Meet Memoket Note, an agent-native writing workspace. This personal open-source project is built on the memoket-kite memory engine. It brings AI writing actions, source-backed memory and reviewable edits into the same note. A writing agent harness coordinates the work behind the scenes.

### 00:00:16 — One evolving note

A writing task starts with a note, its purpose and the material you want to use. The editor keeps this state together, so you can work on the draft while the agent retrieves context and proposes changes. You remain responsible for the final text.

### 00:00:31 — The task has a scope

For a small task, use a direct writing action. Select a paragraph to rewrite, polish or verify. Continue at the cursor when you need the next passage. For a longer task, start a workflow with the note goal and completion criteria. Each entry point carries the relevant scope.

### 00:00:49 — Evidence within reach

Memoket-kite supplies long-term memory. Note uses its facts and source links to bring relevant evidence into the writing task. You can inspect recalled material, collect it in the tray and cite it in the draft. Retrieval is evidence to review, not a guarantee that a generated claim is correct.

### 00:01:06 — Write. Check. Decide.

The writing agent harness manages task state and tools, and turns a writing request into a loop. First it prepares material, then drafts or revises. Deterministic checks inspect constraints such as citations, output shape and repetition. A model judge assesses the configured writing dimensions. The policy uses that feedback to choose another round, repair, pause or stop.

### 00:01:29 — You decide what stays

Changes stay reviewable. Inspect individual edits and decide what to keep or revert. Run snapshots and note history support recovery. The harness has explicit limits and stopping conditions, and can retain an earlier best round. Automated checks help you review the result, but they do not replace your judgment.

### 00:01:47 — A weekly report

For example, start a weekly report by setting the audience and what the report must cover. Gather notes and other material, then let the harness prepare evidence, draft and check. Review the proposed changes and verify their citations before exporting or sharing the finished report.

### 00:02:04 — Built on memoket-kite

Memoket Note is a personal project, with application code licensed under AGPL version three. The separate memoket-kite engine uses the Apache two license. Configure your own model and transcription services. This is a conceptual walkthrough of the implemented architecture, rather than a live product demonstration or performance benchmark.

## Sources and attribution

Concepts adapted from the project maintainer's supplied introduction deck. Implementation references: `backend/app/harness/`, `backend/app/database/kite/` and `frontend/src/components/`.

Memoket artwork comes from the [official memoket-kite assets](https://github.com/memoket/memoket-kite/tree/main/assets) and links to [memoket.ai](https://memoket.ai). Memoket names and artwork belong to their respective owners. The application is a personal project.

Application code: AGPL-3.0-only. Separate memory engine: Apache-2.0. See the repository license and third-party notices.
