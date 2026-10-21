# Validation notes

Validated on October 21, 2026 with Python 3.11.15, Node.js 22.22.3 and macOS arm64.
The final checks reuse the isolated dependency installations from the earlier
publication preparation. This update changes no dependency versions.

| Check | Result |
|---|---|
| Backend pytest | 415 passed |
| Frontend Vitest | 57 files, 308 passed |
| Independent frontend/backend shared contracts | 61 passed |
| Frontend types, lint and production build | Passed |
| Desktop typecheck and packaging downloader test | Passed |
| Python static analysis | No pyflakes findings in `backend/app` |
| Publication audit | No recognizable credential, private-data-path or personal-absolute-path findings |
| Source-language audit | Literal Han characters remain confined to optional translation dictionaries |

Backend tests report six deprecation warnings in third-party dependencies. The
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
- The visible Export button, Markdown download and local vault export.
- Clickable imported-source citations, dated original evidence and backlinks.

No horizontal overflow was found in the checked flow, import, export or template
components. Compact windows now collapse both side panes so the writing area
remains usable. Screenshots and DOM dimensions support these checks. Native
dark-mode appearance, live Notion/Feishu round trips and Apple Notes automation
permissions remain manual validation work.

## Packaged application

The macOS Apple Silicon installer is version 0.1.2. Deep signature verification,
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
