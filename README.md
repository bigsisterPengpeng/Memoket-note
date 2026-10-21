<p align="center">
  <a href="https://memoket.ai"><img src="docs/media/memoket-brand.png" width="680" alt="Memoket"></a>
</p>

# MEMOKET NOTE

**An agent-native writing workspace with long-term memory and reviewable edits.**

MEMOKET NOTE is my personal open-source project, built on
[memoket-kite](https://github.com/memoket/memoket-kite). It combines a local note
editor with AI writing actions, source-backed retrieval and a writing loop that
can prepare material, draft, check and revise. You set the goal and decide which
changes to keep.

The workspace includes a **writing agent harness** that coordinates tools,
iterative drafting, quality checks and recovery. KITE supplies long-term memory;
the harness manages the writing task; the workspace brings them into the editor.

[Introduction video](docs/media/agent-native-writing-workspace.mp4) ·
[The writing agent harness](#the-writing-agent-harness) ·
[Development setup](#development-setup) · [Contributing](CONTRIBUTING.md)

## Watch the introduction

[![Watch the agent-native writing workspace introduction](docs/media/agent-native-writing-workspace-poster.png)](docs/media/agent-native-writing-workspace.mp4)

**[Watch or download the English introduction](docs/media/agent-native-writing-workspace.mp4)**
([transcript](docs/media/agent-native-writing-workspace.md),
[English captions](docs/media/agent-native-writing-workspace.en.vtt)). The video
explains the architecture and a weekly-report workflow. It uses narrated concept
scenes rather than a live application recording.

## The writing agent harness

The writing agent harness is the runtime around the model: it carries task state,
controls tools, checks output and decides what happens next. Here, the note is the
shared work in progress throughout that loop.

1. **Define the task.** Set the goal, audience, structure and completion criteria.
   Use a direct action for a selection, cursor position or block, or start a
   workflow for a longer document.
2. **Prepare evidence.** Retrieve task-specific facts from KITE and include
   material selected in the note's tray. Keep identifiers and source links
   attached to the evidence.
3. **Draft and check.** Generate or revise the text. Run deterministic checks for
   citations, structure, repetition and block shape, then use the configured
   judge for writing-quality dimensions.
4. **Choose the next step.** Feed failures into another round, repair a draft,
   pause or stop within configured limits. Preserve an earlier best round when
   later output regresses.
5. **Review the changes.** Inspect edits by layer or hunk, keep or revert changes,
   and recover earlier text through snapshots and history.

The harness supports note and section writing alongside block tasks such as
charts, tables and analysis. The core loop shares state and checks across task
modes. Automated evaluations support review; they do not prove factual accuracy
or make a draft ready to publish without human judgment.

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

## Features

- A note tree with linked clones, tabs, split panes, history, backlinks and Markdown export.
- An editor with an outline, tracked revisions, inline citations and generated blocks.
- 104 writing templates across 12 categories, searchable by name and description.
- Writing workflows that retrieve sources, draft, check requirements and revise.
- Batch import for PDF, DOCX, text, Markdown and audio, with progress and cancellation.
- Knowledge search, source tracing, a topic map, entities, facts and a timeline.
- Local Whisper transcription and hosted AssemblyAI or Speechmatics transcription.
- Model presets for local services and hosted providers, with credentials per provider.
- Reusable writing skills, automatic database backups and a desktop log viewer.

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

## Voice service

Select the provider in Settings under Voice service:

| Provider | Requirements | Processing |
|---|---|---|
| Whisper | A running whisper.cpp server | Self-hosted transcription |
| AssemblyAI | An API key and a US or EU region | Audio upload and a polled batch job |
| Speechmatics | An API key and a US or EU region | A polled batch job using the enhanced model |

`ASR_POLL_TIMEOUT_S` limits hosted job polling; its default is 1,800 seconds.
The connection test contacts the selected provider without uploading audio.
Hosted transcription sends the selected recording to that provider.

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

| Directory | Responsibility |
|---|---|
| `frontend/src/components/` | React interface components |
| `frontend/src/editor/` | Editor behavior, templates and text transformations |
| `frontend/src/util/` | Frontend utilities and shared UI contracts |
| `backend/app/routers/` | FastAPI routes and streamed events |
| `backend/app/harness/` | Writing loops, tools, quality checks and skills |
| `backend/app/database/` | SQLite persistence, knowledge search and KITE integration |
| `backend/app/editor/` | Backend editor operations |
| `backend/app/util/` | Configuration and provider clients |
| `desktop/src/` | Electron windows, menus, permissions and backend lifecycle |
| `shared/` | Cases that verify frontend/backend behavior matches |
| `docs/` | Architecture, interface conventions and contributor documentation |

Interactive writing paths use deterministic retrieval. Model-based planning is
available on the explicit knowledge question path. Writing workflows share a loop
and express their differences through mode configuration and checks.

Design references: [architecture](docs/architecture.md),
[UI conventions](docs/UI_SPEC.md), and [shared cases](shared/README.md).

## Selected API endpoints

Use the backend's `/docs` page for request schemas and the complete API.

| Endpoint | Purpose |
|---|---|
| `GET /api/memory/topics` | Knowledge topics |
| `GET /api/memory/entities` | Entities |
| `GET /api/memory/facts` | Filtered, paginated facts |
| `GET /api/memory/facts/{id}/sources` | Source evidence for a fact |
| `GET /api/memory/timeline` | Knowledge timeline |
| `POST /api/ingest/text` | Import text |
| `POST /api/ingest/audio` | Import and transcribe audio |
| `POST /api/ingest/transcribe` | Transcribe without importing |
| `POST /api/ingest/batch` | Import multiple files |
| `GET /api/ingest/jobs` | List import jobs |
| `GET /api/ingest/jobs/{id}` | Import job status |
| `GET /api/ingest/jobs/{id}/events` | Stream import progress |
| `POST /api/ingest/jobs/{id}/cancel` | Cancel pending work |
| `POST /api/note-harness/run` | Stream a note-writing workflow |
| `POST /api/writing-plan/start` | Create a multi-note writing plan |
| `POST /api/writing-plan/run` | Run a writing plan |
| `GET /api/harness/paused` | List paused workflows |
| `POST /api/harness/{id}/resume` | Resume a workflow |
| `POST /api/compose/block` | Generate an editor block |

The `X-User-Id` header selects a user's codebook; it is not authentication.
See [SECURITY.md](SECURITY.md) before exposing
the API beyond a trusted local environment.

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

Normal tests use stubs instead of live model calls. Frontend test commands give
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
