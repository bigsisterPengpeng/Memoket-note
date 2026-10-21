# Contributing

Use Python 3.11 and Node.js 22.12 or later. Follow [README.md](README.md) for installation. Install Python requirements with `-c constraints.txt` to reproduce the validated versions; KITE is pinned to a tested upstream commit.

## Validate changes

```sh
cd backend
PYTHONPATH=. .venv/bin/python -m pytest -q

cd ../frontend
npm test
npm run build

cd ../desktop
npm run build
npm test
```

From the repository root, run:

```sh
python3 scripts/audit_publication.py
python3 scripts/audit_source_language.py --english-source
```

The tests use synthetic inputs and stubs rather than live model calls. Backend fixtures isolate SQLite databases and KITE codebooks. Frontend subprocesses receive disposable data directories. Historical research logs, private corpora and screenshot-driving scripts are excluded from this source distribution. Passing tests does not establish a live-model quality benchmark or certify every visual state.

Shared contracts in `shared/` execute independently on both sides. Add both a failing case and a valid counterexample when fixing text transforms, completion criteria or action guards. Do not derive expected results from the implementation under test.

## Code conventions

- Use English identifiers, comments, documentation, model instructions and default UI text.
- Keep optional translations in the dedicated locale dictionaries. Preserve multilingual user content and saved-format compatibility.
- Put persistence and retrieval in `backend/app/database/`, workflows in `backend/app/harness/`, and HTTP adaptation in `backend/app/routers/`.
- Use the existing design tokens and icon mapping. Follow [UI conventions](docs/UI_SPEC.md). Check hover, keyboard focus, long text, appearance modes and the 900 × 600 minimum desktop window.
- Keep comments that explain constraints or non-obvious decisions. Remove retrospective development narratives.
- Include the problem, resulting behavior, validation and material limitations in pull requests.

## Dependencies and packaging

Mermaid uses explicit `dagre` layout and `classic` appearance settings. The desktop toolchain overrides `@electron/get` to version 5; its local test checks the packaging adapter, cache reuse and checksum rejection without downloading Electron. That version uses native Fetch options and `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY` rather than the older `GLOBAL_AGENT_*` variables.

Local macOS builds use ad-hoc signing. Configure your own identity in a local electron-builder override for signed distributions. Retain the application license, third-party notices and dictionary license in packages. Never bundle a development library or backups.

## Privacy and security

Keep credentials in an ignored `.env` file or environment variables. Never use a personal library for tests. Do not commit real notes, recordings, imported files, credentials, generated codebooks or local application data. Read [SECURITY.md](SECURITY.md) before exposing the service beyond a trusted local environment.

## Enable GitHub Actions

The publishing credential cannot create workflows, so automatic CI is not enabled. To enable it with an account or token that has the required workflow permission:

```sh
mkdir -p .github/workflows
cp docs/ci-workflow.yml.example .github/workflows/ci.yml
```

The template runs publication/language audits, Python static checks, backend tests, frontend tests and desktop checks. Local validation remains available through the commands above.

## Test and demonstration data

Use independently authored synthetic notes, facts and model responses. Production
recordings, meeting transcripts, customer data, private model captures and real
user identifiers do not belong in tests, comments, documentation or media.
Unicode escaping, translation and abbreviation do not anonymize source material.
Review decoded string literals as well as visible source text before publishing.

Screenshots must use a disposable library with invented content. Label staged
examples and distinguish UI navigation from an actual model-driven run. Keep
private audit inputs and findings outside the source distribution.
