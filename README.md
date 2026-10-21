<p align="center">
  <a href="https://memoket.ai"><img src="docs/media/memoket-brand.png" width="420" alt="Memoket"></a>
</p>

# MEMOKET NOTE

**A writing agent that remembers your work.**

An **agent-native writing workspace** that brings past notes, decisions and sources
into your next draft. Start with the notes you already have, then take your work
back to the tools you use.

A personal open-source project built on the
[Memoket KITE memory engine](https://github.com/memoket/memoket-kite).

[![Import notes, recall lasting memory, review an agent-written draft and export it](docs/media/writing-workflow.gif)](docs/media/agent-native-writing-workspace.mp4)

[Watch the real workflow](docs/media/agent-native-writing-workspace.mp4) ·
[Try it locally](#development-setup) ·
[Bring your notes](#bring-your-notes-keep-your-workflow) ·
[Why agent-native?](#why-agent-native) ·
[Architecture](docs/architecture.md)

## Bring yesterday's work into today's draft

You have a kickoff note, an accessibility decision and last week's rehearsal
results. Now you need a weekly update. Import the notes once, keep their evidence
in memory, and let the writing agent work from that history.

| Step | What you do | What carries forward |
|---|---|---|
| **Import** | Bring Markdown, an Obsidian vault, Notion pages or Apple Notes on macOS | Existing notes and supported source dates |
| **Long-term memory** | Extract knowledge, then reopen the workspace later | Local KITE facts with dated original evidence |
| **Write and review** | Give the agent a goal, inspect its sources and edit the draft | A writing task, source links and reviewable changes |
| **Export** | Download Markdown or write to a connected destination | Your draft, ready for the next part of your workflow |

![A reviewed Maple draft with source links and its selected memory materials](docs/media/screenshots/writing-with-memory.png)

### A real run with fictional notes

The narrated video follows the [Maple pilot example](examples/maple-pilot.md):
three invented notes become 14 extracted facts. The facts survive a backend
restart. GPT-4.1 writes a draft that cites 10 saved facts, and a reviewer removes
a repeated title and corrects an unsupported timing claim before exporting.
The Markdown download and a separate Obsidian vault receive the reviewed body.

This is an edited capture of actual application interactions and live model
output, with sampled screen frames, shortened waits and synthetic English
narration. Source material is entirely fictional. The recording demonstrates
Markdown import and local export; Notion and Apple Notes appear as available
connections without accessing personal accounts. Model output still needs review.

[Watch the demo](docs/media/agent-native-writing-workspace.mp4) ·
[English captions](docs/media/agent-native-writing-workspace.en.vtt) ·
[Transcript](docs/media/agent-native-writing-workspace.md) ·
[Repeat the workflow](docs/workspace-tour.md)

## Where long-term memory appears

Memory persists in the local KITE library across notes and application sessions.
It is available outside the current document or a single model conversation.

- **Related memory beside the draft:** retrieval follows the paragraph at the
  cursor, with a selectable source scope.
- **A fact with evidence:** open the fact to inspect its date and original words.
  Quote it into the note with a source identifier you can follow.
- **Materials for this task:** collect selected facts, notes and web clips so the
  writing agent can prioritize them instead of relying on whatever happens to
  be visible in a chat window.
- **A browsable knowledge base:** revisit facts, entities, source records and the
  timeline when you need to understand or correct what has been stored.

![A saved fact showing its date, original words and related evidence](docs/media/screenshots/source-evidence.png)

Remembering a fact does not make it current or correct. Source dates and original
words remain visible so you can review them; generated claims still need judgment.

## Why agent-native?

The note carries the task and the work in progress. The agent operates through
writing tools and a **writing agent harness**, rather than returning one isolated
chat response that you must manually move into a document.

| What the agent needs | What the workspace provides |
|---|---|
| A bounded task | The selected passage, cursor, block, note or multi-note plan; a goal, audience and done criteria |
| Relevant context | KITE retrieval, source links and explicitly selected Materials |
| A way to act | Tools for retrieval, writing, revision and supported generated blocks |
| Feedback | Code checks for constraints plus configured model judging of writing dimensions |
| A next step | Policy to revise, continue, pause or stop within limits |
| Human control | Visible run progress, edit review, snapshots and history |

A direct Continue action handles a small passage. Smart Continue runs an
iterative writing workflow. You can choose a mode that pauses after each round
so you can accept or revert changes before continuing.

### The writing agent harness

The harness manages task state, tools, writing rounds, checks, stopping conditions
and recovery. The workspace is the complete writing application; KITE is its
memory engine; the harness coordinates the agent's work.

**Prepare evidence → draft or revise → check → decide → review.**

The shared loop supports note and section writing as well as supported chart,
table and analysis blocks. It can keep an earlier best round when a later round
regresses. Automated checks support review; they do not prove factual accuracy.
See the [implementation architecture](docs/architecture.md).

## A template defines more than an outline

The 104 templates across 12 categories set sourcing, writing, checking and finish
rules. A weekly report and a technical design document need different evidence
and different completion criteria. You can also define a custom task for one note.

![Writing templates with explicit sourcing, writing, checks and finish rules](docs/media/screenshots/templates-900x600.png)

## Bring your notes. Keep your workflow.

Start with the notes you already have and export a reviewed draft back into your
workflow. Connections use files and supported account integrations; the options
below describe implemented adapters, not a claim of live shared editing.

| Your existing tool or material | Bring it into NOTE | Take work out of NOTE |
|---|---|---|
| Markdown / Obsidian | Import Markdown files or a vault; retain the folder structure and clean app-specific syntax | Export Markdown or write into a local vault |
| Notion | Import pages accessible to your integration | Write notes as child pages under a selected parent |
| Feishu | Import supported documents, Drive or Wiki content available to your app | Write documents into a selected folder |
| Evernote | Import exported `.enex` notebooks | Export the resulting notes as Markdown |
| Apple Notes on macOS | Import through the local Notes app | Export Markdown for further use |
| PDF, DOCX and plain text | Batch import source documents into the knowledge base | Use the recalled evidence in your drafts |
| Recordings | Transcribe with a configured local or hosted service, then import | Work from the transcript and extracted knowledge |
| A web page | Clip its text into the current note's Materials | Use the selected material during writing |

Notion and Feishu adapters still need real-account end-to-end validation. Hosted
services use your own credentials. The code does not provide an MCP connector,
an editor extension or automatic live synchronization with every writing tool.
See [connection setup and limits](docs/connections.md).

![Download Markdown without an account or export to a connected writing tool](docs/media/screenshots/import-connections.png)

## Relationship to memoket-kite and Memoket

[KITE](https://github.com/memoket/memoket-kite) is Memoket's separate open-source
memory engine. It stores structured facts with source evidence and supports
inspectable retrieval without an embedding or vector-database stack.

NOTE uses the `memoket-kite` Python package through adapters in
`backend/app/database/kite/`. This repository adds the note editor, material tray,
writing workflows, checks and change-review interface around that memory layer.
KITE remains an independent project with its own repository and Apache-2.0
license; this application's code uses AGPL-3.0-only.

This is a personal project based on KITE. The Memoket name and artwork connect it
to the memory engine's origins and [memoket.ai](https://memoket.ai). They do not
imply that this repository has the commercial product's support commitments.
The local KITE integration does not require a Memoket wearable or subscription.
Production synchronization with Gem or the Memoket App is not included here.

## Data and providers

The default interface language is English. Notes and settings are stored locally.
AI features send relevant content to the model or transcription service you
configure. Choose local services when content must stay on your machine or
network. Hosted services require your own accounts and may incur usage charges.

## Development setup

Use Python 3.11 and Node.js 22.12 or later. The browser edition needs a
current browser, including Safari 17.4 or later. From the repository root:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip setuptools -c backend/constraints.txt
backend/.venv/bin/python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt -c backend/constraints.txt
cp .env.example backend/.env
```

Start the backend:

```sh
cd backend
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, start the frontend:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to the backend. The API reference
is at `http://127.0.0.1:8000/docs`; `/api/health` reports backend and service status.

In Settings, select a writing provider and model. Hosted providers need your own
credentials. Local providers need a running OpenAI-compatible server. Environment
variables provide deployment defaults; settings saved in the application take
precedence. An optional judge model can be configured separately.

## Desktop development and packaging

Keep the Vite development server running, then start Electron:

```sh
cd desktop
npm ci
npm run dev
```

To package, install PyInstaller in the backend virtual environment, then build:

```sh
backend/.venv/bin/python -m pip install pyinstaller -c backend/constraints.txt
cd desktop
npm run dist
```

Packages are written to `desktop/out/`. Signing credentials are specific to the
maintainer's environment; contributors can override electron-builder signing
configuration for their own builds. A package includes the backend and frontend.
User data is stored outside the application bundle.

## Architecture

A React and CodeMirror editor runs over a FastAPI backend, with KITE for local
memory and an Electron desktop shell. The [architecture guide](docs/architecture.md)
explains the modules, writing tools and harness loop. The running backend exposes
request schemas at `/docs`.

Interactive writing paths use deterministic retrieval. Model-based planning is
available on the explicit knowledge question path. Writing workflows share a loop
and express their differences through mode configuration and checks.

Design references: [architecture](docs/architecture.md),
[UI conventions](docs/UI_SPEC.md), and [shared cases](shared/README.md).

## Current scope

This is an early personal project. Notion and Feishu import/export integrations
need end-to-end validation with real accounts. Slide export currently covers
Markdown slides and PDF, rather than a complete presentation-authoring suite.

The application targets a trusted local environment. See [SECURITY.md](SECURITY.md)
for provider data flow and deployment constraints.

## Validation

See [validation notes](docs/validation.md) for results, platforms and remaining manual checks.
Automatic CI is not enabled in this initial publication; a
[GitHub Actions workflow template](docs/ci-workflow.yml.example) is included.

```sh
cd backend
PYTHONPATH=. .venv/bin/python -m pytest -q

cd ../frontend
npm test
npm run build

cd ../desktop
npm run build
```

Automated tests use stubs instead of live model calls. The separately recorded
Maple workflow uses a real configured model. Frontend test commands give
backend subprocesses disposable data directories. Backend fixtures isolate database
writes. The source distribution excludes private corpora, archived research evidence and
screenshot-driving scripts. Test results are not live-model quality benchmarks.

Frontend checks cover types, lint, component/editor behavior and shared
frontend/backend contracts. The source-language audit rejects literal Han characters
outside the dedicated optional translation dictionaries. Model instructions and
default UI text are English; multilingual document content remains supported.

See [CONTRIBUTING.md](CONTRIBUTING.md) for change conventions and
[SECURITY.md](SECURITY.md) for deployment and reporting guidance.

## License and attribution

Licensed under [AGPL-3.0-only](LICENSE). See
[third-party notices](docs/third-party-notices.md) for attribution and dependency
information. Model weights are not included. Provider services have their own
terms and account requirements.
