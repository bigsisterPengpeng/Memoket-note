# Connect your writing tools

MEMOKET NOTE can sit between an existing note collection and the next draft.
Import material, choose whether to create notes, extract knowledge, or both,
then review and export the finished work.

## Local files and Obsidian

Open Import, select Notes + knowledge base, Notes only, or Knowledge base only,
then choose Markdown files or an Obsidian vault. Vault metadata and
trash folders are skipped. The importer cleans supported wiki-link and attachment
syntax while keeping the document hierarchy. Click Export in the editor toolbar to download Markdown without an account; the desktop app can write into a local Obsidian vault.

Local vault export keeps existing files by default, including same-name files on
the first export. An unchanged file from a recorded export to that vault can be
updated; externally edited or untracked files appear in the conflict list.
Review the list before selecting **Overwrite existing or edited files in this
vault**. Changing the destination clears that choice. Copy links use the recorded
vault rather than a newly typed path. Legacy links use the entered path until a
successful export records their destination. Older export records remain readable.
An older record without a vault needs one confirmed overwrite before changed
content can update automatically. Identical content can be safely adopted
without overwrite.

Images and recordings are copied before their note is marked exported. Repeating
an unchanged export restores missing attachments. Conflicting attachment files
are also preserved unless overwrite is chosen; missing source attachments and
write failures appear in the result. Successful files can be retried without
creating duplicate notes. This is not live two-way sync.

Writes use temporary files and atomic filesystem operations, so an interrupted
write does not truncate an existing note. Child symbolic links and occupied
paths are rejected, including when overwrite is selected. Vault filesystems must
support hard links and atomic replacement; unsupported operations are reported
as failures. Concurrent exports in one backend are serialized, but other editors
are not locked: content is compared again immediately before replacement, not
protected by a transaction shared with Obsidian. Back up your vault as usual.

## Notion

Create a Notion integration and grant it access to the intended pages. Paste its
existing token into Import; pages not shared with that integration are not visible.
To export, configure an accessible parent page. Notes become child pages with
supported rich-text blocks; local binary attachments have limitations.

## Feishu

Use an app with the required document, Wiki or Drive permissions and access to
the target resources. Import supports the selectable scopes and explicit document
links. Export needs the destination folder and appropriate write permissions.

The Notion and Feishu paths are implemented, but have not been certified against
real accounts in the current validation. Account access and provider API changes
can affect results. Never commit credentials to the repository.

## Evernote and Apple Notes

Export an Evernote notebook as `.enex`, then choose it in Import. Apple Notes
import requires the app backend to run on macOS with AppleScript available and
may request permission to control Notes. Import checks this before enabling the
action. Docker workspaces can use file import instead. A failed or timed-out
availability check shows an explicit message and **Check again**, rather than
remaining on a loading state.
Both produce local notes that can subsequently be exported as Markdown.

## Documents, audio and web pages

Use batch import for supported PDF, DOCX, text, Markdown and audio files.
Transcription needs a configured service. Extracting facts uses the configured
model. The Materials tray can clip a URL's page text for the current writing task;
it is not a general browser synchronization service.

## Model providers

Choose a model in Settings. Local OpenAI-compatible services and hosted provider
presets are supported; the relevant content goes to the endpoint you configure.
Memory is stored locally even when model inference uses a hosted service.

**Test** checks the values currently entered; it does not save them. Changing the
provider, address, model, key or voice region invalidates the previous result
and model suggestions. Test again before relying on the new configuration, then
save it. The visual test follows the current writing key when **Use the writing
model above** is selected; an independent vision setup uses its own key.

Connection tests stop waiting after 45 seconds and can be retried. Editing the
tested configuration or closing Settings aborts the browser request and ignores
late responses. A provider request already sent by the backend may still finish;
cancelling the browser request does not undo it. Connection checks are not a
general writing-quality benchmark.

## Integration boundary

The repository has local HTTP APIs, a CLI and a stdio MCP server for workspace
operations. It does not ship an Obsidian plugin, a Notion browser extension, a
Word add-in or a Google Docs integration. Import/export support should not be
read as those claims.
The API assumes a trusted local environment; see [SECURITY.md](../SECURITY.md).

## Voice services

Select the provider in Settings under Voice service:

| Provider | Requirements | Processing |
|---|---|---|
| Whisper | A running whisper.cpp server | Self-hosted transcription |
| AssemblyAI | An API key and a US or EU region | Audio upload and a polled batch job |
| Speechmatics | An API key and a US or EU region | A polled batch job using the enhanced model |

`ASR_POLL_TIMEOUT_S` limits hosted job polling; its default is 1,800 seconds.
The connection test contacts the selected provider without uploading audio.
Hosted transcription sends the selected recording to that provider.

## Memoket hardware companion

Import selected recording briefs through the official Memoket CLI, using your
existing login where the app backend runs. The Import panel checks CLI
installation without starting it or reading account content; search checks the
saved login. A Docker workspace does not inherit a host login. NOTE also provides its own CLI and stdio MCP for
external agents. See [setup, commands and validation limits](agents-and-memoket.md).
These are explicit imports; no recording deletion, write-back or automatic sync
is exposed.
