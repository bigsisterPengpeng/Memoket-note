# Connect your writing tools

MEMOKET NOTE can sit between an existing note collection and the next draft.
Import material, choose whether to create notes, extract knowledge, or both,
then review and export the finished work.

## Local files and Obsidian

Open Import, select Notes + knowledge base, Notes only, or Knowledge base only,
then choose Markdown files or an Obsidian vault. Vault metadata and
trash folders are skipped. The importer cleans supported wiki-link and attachment
syntax while keeping the document hierarchy. Click Export in the editor toolbar to download Markdown without an account; the desktop app can write into a local Obsidian vault.

On export, note identifiers support repeat exports. Review the overwrite option
before replacing edits made in the destination. This is not live two-way sync.

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
import is a desktop macOS operation and may request permission to control Notes.
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

## Integration boundary

The repository has local HTTP APIs for application operations. It does not ship
an MCP server, an Obsidian plugin, a Notion browser extension, a Word add-in or a
Google Docs integration. Import/export support should not be read as those claims.
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
existing login on this computer. NOTE also provides its own CLI and stdio MCP for
external agents. See [setup, commands and validation limits](agents-and-memoket.md).
These are explicit imports; no recording deletion, write-back or automatic sync
is exposed.
