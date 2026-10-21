# Validation notes

Validated on October 20, 2026 with Python 3.11.15, Node.js 22.22.3 and macOS arm64. The source distribution was installed in a separate virtual environment with `constraints.txt` and fresh `npm ci` installations.

| Check | Result |
|---|---|
| Backend pytest | 399 passed |
| Frontend Vitest | 55 files, 303 passed |
| Independent frontend shared contracts | 61 passed |
| Python static analysis | No pyflakes findings in `backend/app` |
| Frontend types, lint and production build | Passed |
| Desktop typecheck and packaging downloader test | Passed; cache reuse and checksum rejection verified |
| Frontend and desktop npm audits, including development dependencies | No known vulnerabilities reported |
| Installed Python dependency audit | No known vulnerabilities reported |
| Publication audit | No credential, private-data-path or personal-absolute-path findings |
| Source-language audit | Literal Han characters are confined to optional translation dictionaries |

KITE is pinned to a specific upstream commit. Dependency audits are snapshots of the advisory data available at validation time.

## Packaged backend

An ad-hoc-signed macOS arm64 application was built from this source. Deep signature verification passed. Its bundled backend was started against a disposable data directory and verified to serve the frontend, return uncached index HTML, report that no model was configured, persist a note and its Engineering workflow, and return JSON errors for unknown API routes. The package contains the dictionary and exact MIT license, application license and third-party notices; development data directories are excluded.

This local build is not notarized. Windows and Linux desktop packages were not built during this validation.

## UI checks

The local browser used only invented notes, imports and knowledge-base facts. Checks covered:

- All nine Engineering previews at 900 × 600, with the full preview region visible and no horizontal text overflow; larger desktop layouts were also checked.
- Keyboard preview selection after cards scroll into view, task persistence after reload and English generated navigation.
- English file selection controls and tree refresh after two synthetic Evernote imports.
- A long topic name in the graph summary at 900 × 600, with its card inside the viewport and scroll available for long content.
- A rendered Mermaid flowchart after the dependency upgrade.

Browser screenshot captures were blurred by the capture path. Layout evidence therefore combines DOM dimensions, accessibility state and functional interaction; it does not certify fine typography. Native dark-mode appearance and real-account Notion/Feishu round trips remain manual validation work.

## Automatic CI

Automatic GitHub Actions runs are intentionally disabled. An unused workflow template is available as `docs/ci-workflow.yml.example`; validation results here come from local checks.

## Scope

Tests use stubs instead of live model calls and do not establish writing-quality or performance benchmarks. Historical research scripts, private corpora and archived screenshot evidence are not distributed. The introduction video is a narrated concept explanation, not a live product recording.

## Product terminology update — October 21, 2026

Product descriptions now use **agent-native writing workspace**. The **writing
agent harness** remains the runtime that manages task state, tools, writing
rounds, checks, stopping conditions and recovery. Internal module and API names
are unchanged.

The updated frontend passed typechecking, lint, all 303 tests across 55 files,
and all 61 independent shared contracts. Its production build passed with the
existing large-chunk warning. Desktop typechecking and the downloader
compatibility test passed. The updated macOS arm64 application passed deep
signature verification; its bundled backend served the current frontend against
a disposable data directory, including the new product and workflow text.
The welcome screen and Settings description were checked in the browser at
1163 × 608 with no horizontal overflow in their content.

The regenerated English introduction is approximately 145 seconds long, with
33 sentence-aligned captions. Caption text and transcript match the narrated
scene script, local media links resolve, and a full video/audio decode reported
no errors. Changed scenes were visually inspected; the remaining four scene
images are identical to the previous version. The underlying eight-slide
presentation passed package, layout and import validation. The publication
audit reported no findings, and literal Han characters remain confined to
optional translation dictionaries. Backend behavior was not changed or
retested for this terminology update; its earlier results are recorded above.

## Layout, source citations and showcase update — October 21, 2026

The writing-mode picker now renders in a document-level portal. Fixed viewport
placement prevents the editor scroller and stacking contexts from clipping its
header or controls. Card tracks and text have explicit intrinsic-size bounds;
the custom form and details adapt to narrow widths. All 104 cards across all 12
categories were checked at 900 × 600, 720 × 612 and 375 × 600. No card or panel
had horizontal overflow, and the header passed hit-testing at every size.
The sticky writing controls also reserve space above the first document line.

The real UI walkthrough exposed a citation-format gap for manually entered KITE
facts. Their identifiers now participate in source highlighting, citation checks,
backlinks, export stripping and completion checks alongside extracted facts.
Regression tests cover deduplication, user-scoped backlinks and rebuilding the
index for existing notes. A source quotation and its persisted backlink were
verified in the actual interface. English sentence endings and long English
paragraph restatement checks were also corrected during fixture replacement.

The showcase contains only invented Harbor notes and manually entered facts.
Its 25-second silent UI tour is an edited sequence of actual screenshots, with
an animated preview and English captions. It does not show a live model run.
The separate narrated concept introduction remains available. Notion and Feishu
real-account validation remains outside this local verification.

After the final fixes, backend validation passed 402 tests (six third-party
deprecation warnings). Frontend validation passed 305 tests across 56 files,
all 61 shared contracts, typechecking and lint. The production build passed
with the existing large-chunk warning. Python static analysis and the
publication audit reported no findings. Literal Han remains confined to optional
translation dictionaries. No automatic CI or live model calls were used.
