# CLI, MCP and the Memoket companion

NOTE is an agent-native writing workspace built on KITE. The Memoket hardware companion is a separate product. These interfaces connect them in two directions:

- **Bring recording sources in.** NOTE calls the official Memoket CLI with your existing login. Search recordings, read their reports or transcripts, then explicitly import a selected brief into local notes. Choose knowledge extraction to make it available to KITE across later writing sessions.
- **Let agents use NOTE.** NOTE's CLI and stdio MCP server read local notes and memory, create drafts, and propose revisions. An external agent can use both the Memoket cloud MCP and NOTE's local MCP in the same task.

## Connect the companion

Install the [official CLI](https://memoket.ai/pages/connector#cli) from npm and sign in yourself:

```sh
npm install -g @memoket-ai/cli
memoket login
memoket tools
memoket doctor
```

In NOTE, open **Import → Memoket recordings**. Check the connection, search for a project, select a recording and import its brief. The **Import to** choice determines whether to create notes, extract knowledge, or both. Extraction uses your configured model and may send the selected content to that provider. A notes-only import does not extract memory.

The companion bridge is validated on macOS. Windows `.cmd`/`.bat` launchers are rejected to keep tool arguments out of a command shell; an external agent can use the official remote MCP directly.

The backend must be able to find the `memoket` executable and Node.js. Desktop launches may have a different PATH from Terminal. Set `MEMOKET_CLI` to the absolute executable path in the backend environment if necessary; restart the backend after changing it. NOTE never asks for or copies your Memoket password or CLI token. The official CLI manages its own credentials and may refresh or mint its own access token during a read call.

Seven recording read tools are allowed: `list_conversations`, `search_recordings`, `get_conversations`, `get_brief`, `get_summaries`, `get_transcripts` and `get_transcripts_by_participant`. NOTE does not expose token management, webhooks, account changes or recording deletion.

Imports retain the recording ID and report fields. Re-imports use the existing incremental import mechanism: unchanged notes are not duplicated and local edits are preserved. A brief is a summary, not a complete transcript. Paginated reports are rejected rather than silently imported incompletely; use the read tool's returned cursor to fetch further pages. Transcript pagination needs **both** `next_offset` and `next_text_offset`. Recording dates are not inferred from opaque IDs: the import date is not evidence of when a conversation happened. Universal live sync and write-back to Memoket are not provided.

## NOTE CLI

Start the backend first. From `backend/`, use the same Python environment as the application:

```sh
.venv/bin/python -m app.cli --help
.venv/bin/python -m app.cli list --query Maple
.venv/bin/python -m app.cli get NOTE_ID
.venv/bin/python -m app.cli recall 'Maple shelf labels'
.venv/bin/python -m app.cli create --title 'Maple draft' --file ../examples/maple-weekly-update.md
.venv/bin/python -m app.cli revise NOTE_ID --selection 'An existing passage.' --action polish
.venv/bin/python -m app.cli export NOTE_ID > reviewed-draft.md
.venv/bin/python -m app.cli memoket-read search_recordings --json '{"query":"Maple"}'
.venv/bin/python -m app.cli memoket-read get_transcripts --json '{"conversation_id":"RECORDING_ID","offset":0,"text_offset":0}'
.venv/bin/python -m app.cli memoket-import RECORDING_ID --title 'Selected conversation' --to notes
.venv/bin/python -m app.cli job JOB_ID
```

Commands return JSON, except `export`, which writes Markdown to stdout. Errors go to stderr with a nonzero exit code. `revise` returns proposals; it never applies changes. Creation makes a new note instead of overwriting one. Import returns a job ID; use `job` to inspect completion or failure.

`MEMOKET_NOTE_URL` defaults to `http://127.0.0.1:8000`; `--url` overrides it. `MEMOKET_NOTE_USER` defaults to `default`; `--user` overrides it. Choose the same workspace identity as the UI. Only loopback HTTP origins are accepted. User IDs select local data and are **not authentication**. Keep the backend bound to loopback.

## NOTE stdio MCP

Install the optional server dependency:

```sh
backend/.venv/bin/python -m pip install -r backend/requirements-agents.txt -c backend/constraints.txt
```

Use absolute paths in your MCP client's configuration:

```json
{
  "mcpServers": {
    "memoket-note": {
      "command": "/absolute/path/to/Memoket-note/backend/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/Memoket-note/backend",
      "env": {
        "MEMOKET_NOTE_URL": "http://127.0.0.1:8000",
        "MEMOKET_NOTE_USER": "default"
      }
    }
  }
}
```

Clients differ in how they set a working directory. If yours does not support `cwd`, set `PYTHONPATH` to the absolute `backend/` directory instead. The server connects to an already running backend; it does not initialize a database itself. It uses stdin/stdout for MCP and keeps diagnostics off stdout.

Tools: `list_notes`, `get_note`, `recall_memory`, `create_note`, `propose_revision`, `get_import_job`, `read_memoket`, `import_memoket`. Read/write and external-service annotations are advertised. Notes and retrieved content remain untrusted source material. Give an agent access only to the local workspace you intend it to use.

For the companion directly, add the [official remote MCP](https://memoket.ai/pages/connector#mcp): **https://mcp.memoket.ai/mcp**. URL-only clients use OAuth. Clients that require a credential use a personal API token created with the official CLI. Keep that credential in the client's secret settings, never in this repository. NOTE's local stdio MCP and Memoket's remote MCP serve different data; connecting one does not automatically connect the other.

## Packaged macOS application

Packaged backends support the same interfaces without system Python:

```sh
"/Applications/MEMOKET NOTE.app/Contents/Resources/backend/memoket-note-backend" --cli --help
"/Applications/MEMOKET NOTE.app/Contents/Resources/backend/memoket-note-backend" --mcp
```

Use the bundled executable with `--mcp` as the command/args pair. Set `MEMOKET_NOTE_URL` to the backend origin used by your running app; the desktop shell can choose a free port. Do not assume port 8000 if it is occupied. Building a desktop package with MCP requires installing `requirements-agents.txt` before PyInstaller.

## Validation scope

Automated tests cover MCP discovery and calls, CLI output, loopback restrictions, argv-based invocation, read-tool allowlisting, error redaction, empty/partial responses, user isolation and incremental imports. The public Memoket CLI catalog was checked against version 3.0.0. Real-account recording access still needs validation with your own signed-in companion account. Tests and demonstrations use fictional data.
