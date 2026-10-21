<p align="center">
  <a href="docs/media/agent-native-writing-workspace.mp4">
    <picture>
      <source media="(max-width: 600px)" srcset="docs/media/readme/hero-mobile.jpg">
      <img src="docs/media/readme/hero.jpg" width="100%" alt="MEMOKET NOTE — Stay in the document. Let the agent work. An agent-native writing workspace with long-term memory, shown with a real draft and fictional demo data.">
    </picture>
  </a>
</p>

<p align="center">
  <a href="docs/media/agent-native-writing-workspace.mp4"><img src="docs/media/readme/button-watch.svg" height="36" alt="Watch the demo · 80 seconds"></a>
&nbsp;
  <a href="#development-setup"><img src="docs/media/readme/button-start.svg" height="36" alt="Run locally"></a>
&nbsp;
  <a href="https://github.com/memoket/memoket-kite"><img src="docs/media/readme/button-kite.svg" height="36" alt="Explore KITE"></a>
</p>

<p align="center">
  <strong>An agent-native writing workspace that keeps your task, memory and edits together.</strong><br>
A personal open-source project built on <a href="https://github.com/memoket/memoket-kite">Memoket KITE</a>.
</p>

<p align="center">
  <a href="#why-agent-native">Why agent-native?</a> &nbsp; / &nbsp;
  <a href="#memory-without-the-detour">Memory</a> &nbsp; / &nbsp;
  <a href="#a-task-a-harness-a-result-you-can-review">The harness</a> &nbsp; / &nbsp;
  <a href="#bring-your-notes-keep-your-workflow">Connections</a> &nbsp; / &nbsp;
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

## Why agent-native?

**You opened a document. Why are you managing a chat?**

Copy a paragraph into a chatbot. Explain the context. Paste the answer back. Find an old note, switch to the browser, then try to remember where you were going. Ask for one more revision and lose the part you wanted to keep.

NOTE is designed around three goals:

- **Less interaction friction.** Use writing actions on the passage or document you're already in. The workspace supplies its context.
- **Keep your train of thought.** Recall related notes and source evidence beside the draft, without rebuilding the background in a new conversation.
- **Delegate work, keep control.** Give the agent a task. Let its harness retrieve, write, check and revise. Inspect the changes and keep or revert them.

That is what *agent-native* means here: the document carries the work; the agent has tools to act on it. Read the [design principles](docs/why-agent-native.md).

## See the whole workflow in 80 seconds

[![Play the real workflow: three notes, fourteen saved facts, one reviewed draft](docs/media/readme/demo.svg)](docs/media/agent-native-writing-workspace.mp4)

The [fictional Maple pilot](examples/maple-pilot.md) goes from **three imported notes** to **14 facts that survive a backend restart**, then a live GPT-4.1 draft citing **10 saved facts**. A reviewer corrects the draft before exporting it to Markdown and a separate Obsidian vault.

[Play video](docs/media/agent-native-writing-workspace.mp4) · [English captions](docs/media/agent-native-writing-workspace.en.vtt) · [Transcript](docs/media/agent-native-writing-workspace.md) · [Repeat the example](docs/workspace-tour.md)

<details>
<summary><strong>Animated preview and recording notes</strong></summary>

[![Actual import, memory, writing and export interactions](docs/media/writing-workflow.gif)](docs/media/agent-native-writing-workspace.mp4)

The video uses actual application interactions and live model output, with sampled frames, shortened waits and synthetic English narration. All source material is fictional. The reviewer removes a repeated title and corrects an unsupported timing claim. Notion and Apple Notes appear as connection options; the recording does not access personal accounts. Model output still needs review.

</details>

## Memory without the detour

![Long-term memory in NOTE: a saved fact retains its date, original words and a backlink to the draft](docs/media/readme/memory.jpg)

**The relevant past should meet you where you're writing.** Retrieval follows the paragraph at your cursor. Open a fact's dated evidence, quote it into the note, or collect it in the task's Materials. KITE keeps that memory locally across notes and sessions; it is available beyond the current model conversation.

Browse facts, source records, entities and a timeline in the knowledge base. Memory preserves evidence, not a guarantee that a claim is still current or correct. [Inspect the original screenshot](docs/media/screenshots/source-evidence.png).

## A task, a harness, a result you can review

![The writing agent harness retrieves, drafts, checks and revises inside the workspace; the person reviews the changes](docs/media/readme/agent.jpg)

**Give it a goal, an audience and done criteria.** A direct Continue action handles a small passage. Smart Continue runs an iterative writing workflow with retrieval, generation, checks and a decision to revise, pause or stop. You can pause after each round, inspect edits and recover earlier work.

The editor also supports revision layers, snapshots and history. A later attempt can be worse: the harness can retain an earlier best round, and the interface supports individual edit decisions. Automated checks support your review; they do not prove factual accuracy.

<details>
<summary><strong>What the writing agent harness does</strong></summary>

The **workspace** is the application, **KITE** is its memory engine, and the **writing agent harness** coordinates task state, tools, rounds, quality feedback, stopping conditions and recovery.

**Prepare evidence → draft or revise → check → decide → review.**

The run uses a bounded scope: a passage, block, note or multi-note plan. Retrieved memory and selected Materials feed both generation and scoring. Supported modes also cover chart, table and analysis blocks. Model-based planning is available on the explicit knowledge question path; interactive writing uses deterministic retrieval. See [architecture and implementation](docs/architecture.md).

</details>

<details>
<summary><strong>104 templates, plus custom writing tasks</strong></summary>

Templates across 12 categories define sourcing, writing, checking and finish rules. A weekly report and a technical design document need different evidence and completion criteria. A custom task can set the goal for one note.

![Templates with explicit sourcing, writing, checks and finish rules](docs/media/screenshots/templates-900x600.png)

</details>

## Bring your notes. Keep your workflow.

<picture>
  <source media="(max-width: 600px)" srcset="docs/media/readme/connections-mobile.svg">
  <img src="docs/media/readme/connections.svg" width="100%" alt="Bring Markdown, Obsidian, Notion, Apple Notes, Evernote and Feishu into NOTE; export Markdown, a local vault or configured destinations.">
</picture>

**You should not need to abandon your existing notes to write with their memory.** Bring material in, work from its evidence, then download Markdown or send the reviewed draft to a supported destination. Markdown download needs no account.

<details>
<summary><strong>Import and export compatibility</strong></summary>

| Your existing tool or material| Bring it into NOTE | Take work out of NOTE |
|---|---|---|
| Markdown / Obsidian | Import Markdown files or a vault; retain the folder structure and clean app-specific syntax | Export Markdown or write into a local vault |
| Notion | Import pages accessible to your integration | Write notes as child pages under a selected parent |
| Feishu | Import supported documents, Drive or Wiki content available to your app | Write documents into a selected folder |
| Evernote | Import exported `.enex` notebooks | Export the resulting notes as Markdown |
| Apple Notes on macOS | Import through the local Notes app | Export Markdown for further use |
| PDF, DOCX and plain text | Batch import source documents into the knowledge base | Use the recalled evidence in your drafts |
| Recordings | Transcribe with a configured local or hosted service, then import | Work from the transcript and extracted knowledge |
| A web page | Clip its text into the current note's Materials | Use the selected material during writing |

![Actual export dialog with Markdown download and connected destinations](docs/media/screenshots/import-connections.png)

</details>

Notion and Feishu adapters need real-account end-to-end validation. Apple Notes import uses the local macOS Notes app. Connections are explicit imports and exports; universal live synchronization and editor extensions are not included. [Connection setup and limits](docs/connections.md).

## Development setup

Use Python 3.11 and Node.js 22.12 or later. The browser edition needs a current browser, including Safari 17.4 or later. From the repository root:

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

Open `http://localhost:5173`. Vite proxies `/api` to the backend. The API reference is at `http://127.0.0.1:8000/docs`; `/api/health` reports backend and service status.

In Settings, select a writing provider and model. Hosted providers need your own credentials. Local providers need a running OpenAI-compatible server. Environment variables provide deployment defaults; settings saved in the application take precedence. An optional judge model can be configured separately.

<details>
<summary><strong>Desktop development and packaging</strong></summary>

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

Packages are written to `desktop/out/`. Signing credentials are specific to the maintainer's environment; contributors can override electron-builder signing configuration for their own builds. A package includes the backend and frontend. User data is stored outside the application bundle.

</details>

<details>
<summary><strong>Architecture and implementation</strong></summary>

A React and CodeMirror editor runs over a FastAPI backend, with KITE for local memory and an Electron desktop shell. The [architecture guide](docs/architecture.md) explains the modules, writing tools and harness loop. The running backend exposes request schemas at `/docs`.

Interactive writing paths use deterministic retrieval. Model-based planning is available on the explicit knowledge question path. Writing workflows share a loop and express their differences through mode configuration and checks.

Design references: [architecture](docs/architecture.md), [UI conventions](docs/UI_SPEC.md), and [shared cases](shared/README.md).

</details>

<details>
<summary><strong>Validation and test commands</strong></summary>

See [validation notes](docs/validation.md) for results, platforms and remaining manual checks. Automatic CI is not enabled in this initial publication; a [GitHub Actions workflow template](docs/ci-workflow.yml.example) is included.

```sh
cd backend
PYTHONPATH=. .venv/bin/python -m pytest -q

cd ../frontend
npm test
npm run build

cd ../desktop
npm run build
```

Automated tests use stubs instead of live model calls. The separately recorded Maple workflow uses a real configured model. Frontend test commands give backend subprocesses disposable data directories. Backend fixtures isolate database writes. The source distribution excludes private corpora, archived research evidence and screenshot-driving scripts. Test results are not live-model quality benchmarks.

Frontend checks cover types, lint, component/editor behavior and shared frontend/backend contracts. The source-language audit rejects literal Han characters outside the dedicated optional translation dictionaries. Model instructions and default UI text are English; multilingual document content remains supported.

See [CONTRIBUTING.md](CONTRIBUTING.md) for change conventions and [SECURITY.md](SECURITY.md) for deployment and reporting guidance.

</details>

## Built on KITE. Made as a personal project.

[Memoket KITE](https://github.com/memoket/memoket-kite) is the separate open-source memory engine. It stores structured facts with source evidence and supports inspectable retrieval without an embedding or vector-database stack. NOTE adds the editor, task Materials, writing harness and change-review interface around it.

This is a personal project based on KITE, not a promise of commercial product support. The Memoket name and artwork acknowledge its origins at [memoket.ai](https://memoket.ai). The local integration needs no wearable or Memoket subscription; production synchronization with Gem or the Memoket App is not included. KITE is independently licensed under Apache-2.0.

### Data and current scope

Notes and settings are stored locally. AI features send relevant content to your configured model or transcription service. Local endpoints can keep processing on your machine or trusted network; hosted services use your accounts and may incur charges. The default interface and prompts are English.

This is an early project for a trusted local environment. Account integrations still need validation. Slide export covers Markdown slides and PDF. See [SECURITY.md](SECURITY.md) for data flow and deployment limits.

### License

Application code: [AGPL-3.0-only](LICENSE). Memory engine: Apache-2.0. [Third-party notices](docs/third-party-notices.md) cover attribution and artwork. Model weights are not included; provider terms apply separately.

<p align="center">
  <a href="https://memoket.ai">Memoket</a> &nbsp; · &nbsp;
  <a href="https://github.com/memoket/memoket-kite">KITE</a> &nbsp; · &nbsp;
  <a href="docs/why-agent-native.md">Design principles</a> &nbsp; · &nbsp;
  <a href="CONTRIBUTING.md">Contributing</a> &nbsp; · &nbsp;
  <a href="SECURITY.md">Security</a>
</p>
