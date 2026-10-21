# Stay in the document. Let the agent work.

MEMOKET NOTE began with a practical question: why does using AI to write so often make it harder to keep writing?

## The friction is in the handoffs

A writer copies a passage into a chatbot, explains its context, asks for a revision, and pastes it back. Research adds more handoffs: a browser, an old note, a summary, another prompt. Diagrams and data analysis can introduce yet another tool. A chat panel inside an editor shortens the distance, but still asks the writer to manage a conversation alongside the document.

Each handoff costs attention. After investigating one detail, the writer has to reconstruct the argument they were making. Finding an old note solves a retrieval problem but can interrupt the thought it was meant to support.

Longer tasks add another failure mode. A writer gives an AI a pile of notes and an outline, then spends the next several rounds correcting the timeline, restoring lost details and trying to preserve the good parts of earlier drafts. The conversation advances, but control over the document becomes harder to track.

## Three design principles

### 1. Express the intent through the work

Common writing operations should be actions on the passage, block or document already in front of the writer. The application should supply the relevant context instead of asking the person to paste the same background into every prompt. A button should represent a coherent operation, not merely open an empty conversation.

This reduces repeated prompting; it does not remove the need to specify a goal, choose a provider, or review the result. Some tasks still need a brief or a choice of source material. The interface should ask for information that changes the work, rather than make the writer orchestrate every model call.

### 2. Bring memory into the writing context

Related decisions, source wording and history should be usable beside the draft. The writer should be able to follow evidence without first remembering which application or old document contains it. Memory must persist beyond the current note or model conversation.

NOTE uses KITE for local memory. Contextual retrieval, dated source evidence, citations and the Materials tray connect that memory to current writing. A browsable knowledge base makes stored information inspectable and correctable. Retrieval is an aid to judgment, not proof that an old fact is still true.

### 3. Delegate a task, preserve control over its execution

A writing task needs a goal, relevant evidence, tools, feedback and stopping conditions. A single generated response is only one step. The writing agent harness coordinates retrieval, drafting, checking, revision and the next action. The workspace keeps progress and changes visible to the person directing it.

Autonomy should not erase edit history. Writers need to accept or reject specific changes, recover earlier states, and stop an unhelpful run. Revision layers, snapshots, history, per-round pauses and retention of an earlier best round are ways to make iteration reviewable. Automated checks cannot guarantee factual accuracy or a good argument; the writer retains the final judgment.

## What “agent-native” means in this project

The application owns the document, task and editing state. The harness gives the agent bounded tools and an execution loop. KITE supplies persistent memory. These parts cooperate around the writing task instead of making the person move text between disconnected conversations and artifacts.

The aspiration extends to research, structured blocks, diagrams, data analysis and presentations. Implementation varies by feature. In particular, slide export currently covers Markdown slides and PDF, and account integrations still need real-account validation. The [architecture](architecture.md), [connection guide](connections.md) and [validation notes](validation.md) describe what exists and what has been checked.

## Keep the writer's existing workflow

Notes already live in different places. Import and export should connect those sources to the writing workspace, with clear boundaries. They do not imply universal live synchronization, shared editing, or an extension installed inside every source application.

A useful test of the design is simple: can a writer turn existing notes into a reviewed draft, understand its evidence, recover from a poor revision, and take the result back to their tools while keeping hold of their train of thought?
