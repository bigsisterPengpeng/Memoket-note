# Validation notes

## Current release: October 30, 2026 / 0.1.6

| Check | Result |
|---|---|
| Backend pytest | 456 passed |
| Frontend Vitest | 62 files, 336 passed |
| Shared frontend/backend contracts | 61 passed |
| Types, lint, Python static checks and desktop test | Passed |
| Publication and English-source audits | Passed |
| Linux arm64 container smoke test | Seven groups passed |
| macOS arm64 installer | Signature, disk image, isolated backend/CLI and bundled web checks passed |

Memory source selection now applies before candidate limits, ranking, date-range
caps, pagination and cluster expansion. The agent's lookup, topic/entity listing,
filtering, date-range and compiled session-context tools use the selected
scope. Library browsing and explicit fact/source-ID inspection remain available
separately, preserving verification of citations already in a document.

Twenty new regression cases cover five source scopes, 820 stronger excluded
candidates in both strict and relaxed modes, useful cluster follow-up, raw-line fallback, scoped counts, empty
scopes, source deletion, unknown-scope compatibility, user isolation and actual
KITE stage bindings with a stubbed query compiler. A digest regression first
fails against the previous revision because 405 excluded facts exhaust its
400-row date-range cap; it now returns the two allowed notes. No live provider
calls are required.

The [reproducible synthetic comparison](retrieval-evaluation.md) uses 144
source-linked facts and 40 query/scope cases. Direct-recall hit rate increases
from 20% to 100%; cluster expansion obeys the source scope in every case.
These results target the reproduced failure rather than general semantic
relevance or writing quality. Warm p95 times remain below 1.5 ms on the test
host. First-query initialization is more expensive; cached source views trade
some memory for avoiding repeated full-library scans.

The actual UI was checked with a disposable fictional library. Switching between
Notes only, Imports only and Screen activity only changed the related-memory
cards; opening a card showed its dated original evidence and returning to the
draft retained the selected scope. The production web bundle in the installer
matches the current frontend build byte for byte. The bundled backend passes
all five source filters and reads original evidence from that same fixture.

The Linux arm64 image passed seven disposable smoke groups, including the real
CLI/MCP handshake, stopped-library backup and saved KITE evidence after container
replacement. The synthetic retrieval cases also passed inside the image with
networking disabled. Existing containers and library volumes were preserved.

The 0.1.6 macOS arm64 installer is locally ad-hoc signed and not notarized. The
real installed application profile, notes, recordings and account connectors
were not used. Native screen-reader behavior and real-model writing quality
were not validated for this retrieval fix. Backend tests retain five
third-party deprecation warnings, and the frontend retains its large-chunk build
warning. No dependency or CI configuration was added.

## Container deployment update: October 22, 2026

The Compose image was built and exercised as Linux arm64 on a macOS Apple
Silicon Docker host. Backend pytest passed all 430 cases, including a regression
test proving readiness does not probe model providers. Python static checks,
publication and English-source audits, Compose validation and Dockerfile build
checks passed. The actual image build compiled the frontend production bundle.
The build retains the existing frontend large-chunk warning.

The disposable container smoke test passed all seven groups: non-root/read-only
runtime and loopback networking; readiness and built web assets with unavailable
providers; same-origin note creation and cross-site rejection; built-in skills
and empty KITE initialization; Markdown export, NOTE CLI and MCP handshake/tool calls; consistent
stopped-library backup; and notes plus manually seeded KITE facts and original
evidence surviving container replacement. Its temporary project and volume were
removed. The real Docker build context was exported separately and inspected:
577 input files, with no local records, environment files, libraries or databases.

A browser check of the running container confirmed editor loading, typing,
autosave and reopening a saved fictional Maple note after reload. An external
MCP client also connected through `docker exec -i`, discovered eight tools and
read that fictional note through the container's stdio server. No real model,
account connector, Apple Notes automation or screen capture was exercised for
this update. This does not establish live extraction quality, Linux x86-64 or
Windows host compatibility. The macOS installer below was not rebuilt because
this update adds container deployment and a readiness route without changing
desktop behavior.

## Previous application validation: October 21, 2026

Validated on October 21, 2026 with Python 3.11.15, Node.js 22.22.3 and macOS arm64.
The final checks reuse the isolated dependency installations from the earlier
publication preparation. The CLI reuses core dependencies; the optional stdio MCP server adds the pinned MCP 2.3.0 runtime. KITE and existing application dependency versions remain pinned.

| Check | Result |
|---|---|
| Backend pytest | 429 passed |
| Frontend Vitest | 58 files, 310 passed |
| Independent frontend/backend shared contracts | 61 passed |
| Frontend types, lint and production build | Passed |
| Desktop typecheck and packaging downloader test | Passed |
| Python static analysis | No pyflakes findings in `backend/app` |
| Publication audit | No recognizable credential, private-data-path or personal-absolute-path findings |
| Source-language audit | Literal Han characters remain confined to optional translation dictionaries |

Backend tests report five deprecation warnings in third-party dependencies. The
frontend production build retains its large-chunk warning. Dependency advisory
audits passed on October 20, 2026; those results are a dated snapshot, not a claim
that no dependency can develop a vulnerability. KITE remains pinned to an upstream
commit.

## Real workflow with fictional data

The [Maple example](../examples/maple-pilot.md) uses three independently authored
fictional Markdown notes. The actual application imports them and uses GPT-4.1
to extract 14 facts. The same identifiers remain retrievable after backend
restarts. The writing workflow then produces a draft citing 10 stored facts.

Human review removes a repeated title and corrects an unsupported timing claim.
The reviewed draft has 168 whitespace-delimited words including headings. All
10 fact identifiers resolve to stored facts and readable original evidence.
Clicking a source link and returning through the note backlink works in the UI.

The actual Markdown download matches the saved body. The separate local Obsidian
export contains that same body and all 10 source identifiers. The demonstration
does not connect to real Notion, Feishu or Apple Notes accounts.

The English video uses sampled captures of those actual interactions and live
model output, with edited timing and synthetic narration. Its captions match its
transcript. Every chapter is visually inspected and the complete video/audio
stream decodes without errors. Model output and extraction results can vary.

## CLI, MCP and inline-action validation

The NOTE stdio MCP server exposes eight tools. Both the source server and the
packaged executable complete a real MCP handshake, list their tools, list the
fictional Maple notes and recall three saved facts through the running backend.
CLI creation, JSON output and Markdown export are also checked. Automated tests
cover loopback-only client URLs, read-tool allowlisting, subprocess argument
handling, diagnostic redaction, batch-launcher rejection, user isolation and
incremental imports that preserve local edits.

The official Memoket CLI 3.0.0 public catalog advertises seven recording read
tools. The UI can locate that installed CLI. Real-account recording reads and
imports have not been validated: tests use fictional tool responses, and no
personal recordings are included in the demonstration or publication.

A separate fictional rehearsal note exercises right-click Polish and the slash
menu's Data visualization action with a real model. A broad polish invents a
causal relationship and is reverted; a focused grammar improvement is accepted.
The chart explanation is corrected against the source. Review controls remain
necessary even when automated checks pass. Selection edits now preserve boundary
whitespace. Chart generation separates tool preparation from writing and inserts
validated chart artifacts without asking the model to recopy their syntax.
Bar-chart axes include zero, including when values are negative.

The revised video is approximately 119 seconds with 33 English caption cues.
The README embeds the video through a GitHub-hosted attachment. These are edited captures;
UI interactions are automated to demonstrate the workflow and review steps.
The image-generation feature appears as a menu option; the demonstrated figure
operation is data visualization.

## Regression fixes from the live run

A non-reasoning model rejected the optional `reasoning_effort` argument. The
client now retries after an explicit rejection, including replies that omit the
parameter field. Regression tests exercise normal completions, tool calls and
both streaming paths, retain output limits, and confirm that authentication,
quota and unrelated errors are not hidden.

Imported source identifiers use longer hashes than direct note ingests. Citation
recognition now covers these identifiers in frontend rendering, backend checks,
source backlinks and export handling. Shared fictional cases keep those formats
consistent. Rapidly selecting materials also exposed overlapping tray writes;
additions now queue per note and merge with the saved materials.

## UI checks

The updated screens use fictional data and retain the existing visual tokens.
Layout and interaction checks cover:

- Welcome and Export at 1280 × 720, 900 × 600, 720 × 612, 375 × 600 and 667 × 375.
- Import at 1280 × 720, 900 × 600 and 375 × 600.
- All nine Engineering template previews at 900 × 600, 720 × 612 and 375 × 600.
- Memoket import at 900 × 600 and 720 × 615, including wrapped controls.
- The original README layout was checked at 1040 × 900 and 390 × 844. Its animated preview has since been replaced by a GitHub-hosted video attachment; the demo button leads to that video section. GitHub's Markdown renderer was checked to produce a video element with playback controls.
- The visible Export button, Markdown download and local vault export.
- Clickable imported-source citations, dated original evidence and backlinks.

No horizontal overflow was found in the checked flow, import, export or template
components. Compact windows now collapse both side panes so the writing area
remains usable. Screenshots and DOM dimensions support these checks. Native
dark-mode appearance, live Notion/Feishu round trips and Apple Notes automation
permissions remain manual validation work.

The video attachment was additionally checked with GitHub's authenticated
Markdown renderer, which produced a video element with playback controls. Its
hosted media returned HTTP 200 with a video content type. On Windows, playback
of the same MP4 in the local README preview advanced to 35 seconds without a
browser media error. Private-repository attachments require repository access.

## Packaged application

The macOS Apple Silicon installer is version 0.1.3. Deep signature verification,
disk-image verification, read-only mounting and the Applications shortcut pass.
The bundled backend starts with a disposable copy of the fictional library and
serves the current frontend. It reads all 14 facts, indexes imported and manual
citations, returns source evidence and backlinks, and exports a note to a separate
local vault. No development database is bundled.

The build uses local ad-hoc signing and is not notarized. Windows and Linux
installers were not built. The installed user's application profile is not used
for this validation.

## Publication and CI

Publication checks include tracked files and non-ignored additions. Local demo
libraries, credentials, recordings used during editing, audit inputs and build
outputs stay outside the source distribution. The only published example inputs
are fictional notes and the reviewed example draft.

Automatic GitHub Actions runs remain disabled. The unused workflow template in
`docs/ci-workflow.yml.example` is available for maintainers who choose to enable
CI later. Automated tests use stubs; the separately recorded Maple workflow uses
a real configured model. These checks are not general writing-quality benchmarks.
