# Run the workspace with Docker

Docker Compose builds the browser editor and Python backend into one image. You
do not need Python or Node.js installed on your host. Install Docker Engine or
Docker Desktop with Compose 2.24 or later, then run from the repository root:

```sh
docker compose up --build -d --wait
```

Open **http://localhost:8000**. The first build downloads dependencies and can
take several minutes. Configure a writing provider and model in Settings. Notes,
Markdown import/export and memory browsing work without a model; AI writing and
knowledge extraction require a configured provider. This is a local, single-user
deployment. The published port binds to `127.0.0.1`; the API has no authentication.
See [SECURITY.md](../SECURITY.md) before considering any network deployment.

## Configure models

The editor and API share an origin, so no frontend proxy or CORS configuration is
needed. For a hosted model, enter the provider, endpoint, model and your own key
in Settings. Saved settings take precedence over environment defaults.

For a model running on the host, use
`http://host.docker.internal:11434/v1` or the appropriate host port in Settings.
`localhost` inside the container refers to the container itself. Compose maps
`host.docker.internal` to the host gateway; on Linux the model server must also
listen on an interface reachable from the Docker bridge. Restrict that service
to your trusted machine/network. A server listening only on Linux host loopback
will not be reachable through this mapping.

An optional root `.env` supplies environment defaults; it is never included in
the image. No file is required for initial startup. To use one:

```sh
cp .env.example .env
```

Edit addresses to be reachable **from the container**. The example defaults are
for native development; its `127.0.0.1` model and transcription addresses must be
changed for Docker. Keep provider keys out of version control. Compose fixes the
data and web directories inside the container regardless of `.env` values.

If port 8000 is occupied, set `MEMOKET_NOTE_PORT=8010` in `.env`, then recreate the
container with `docker compose up -d --wait`. Open http://localhost:8010.

## Keep and back up your library

The Compose project uses a named `note-data` volume at `/data`, separate from the
image. Notes, KITE memory, uploaded assets, skills, settings and automatic backups
live there. Restarting, rebuilding or running `docker compose down` preserves it.
Keep the Compose project name `memoket-note` when moving the checkout so it uses
the same volume. Native desktop and container libraries are separate; this setup
does not migrate or mount an existing desktop profile.

For a consistent backup, stop the app and copy its data into a local directory:

```sh
docker compose stop note
mkdir -p backups
docker compose cp note:/data backups/library
docker compose start note
```

Use a fresh backup destination for each snapshot. Backups include notes and saved
provider credentials; store them privately. For recovery, keep the original
volume intact and test a restored copy separately. Never run
`docker compose down --volumes` against your real workspace: it deletes the library.
The smoke test below uses that command only for a newly generated test project.

## Operate and update

```sh
docker compose ps
docker compose logs --tail=100 note
docker compose restart note
docker compose down
```

After reviewing an upstream update, back up the library, update your checkout and
run `docker compose up --build -d --wait` again. Keep a backup before running an
older image: database formats may have changed. Images are built locally; a
hosted image registry and automated image releases are not provided.

The container runs as UID/GID 10001 with a read-only image, a writable named data
volume and temporary `/tmp` storage. Do not mount a Docker socket or your whole
home directory. The readiness check at `/api/ready` is local and does not contact
model providers; `/api/health` separately reports provider connectivity. An
unconfigured or offline model does not make the workspace unhealthy.

## CLI, MCP and platform limits

The image includes NOTE's CLI and stdio MCP dependencies. For example:

```sh
docker compose exec -T note python -m app.cli list
docker compose exec -T note python -m app.cli recall "Maple labels"
docker compose exec -T note python -m app.mcp_server
```

Run the last command through an MCP client using stdio, without a pseudo-terminal.
See [agent setup](agents-and-memoket.md) for the available tools and user selection.

- Browser file uploads and Markdown downloads work with files you explicitly
  select. Obsidian server-side folder import/export sees container paths; a host
  vault needs a separate, deliberately scoped mount and compatible permissions.
- Apple Notes automation, native screen capture and desktop global shortcuts
  require the native macOS application. They are unavailable in the Linux image.
- The official Memoket companion CLI and its host login are not bundled or mounted.
  Use the native setup for companion imports. NOTE's own CLI/MCP is separate from
  that companion connection.
- Audio transcription, image generation and account connectors still require
  their configured services. A Docker health check does not validate them.
- The image is built for the Docker host's architecture. Cross-architecture and
  real-account validation must be reported separately; packaging is not proof of
  connector compatibility.

## Repeat the container checks

Build first, then use host Python 3.11 or later to run the disposable smoke test:

```sh
docker compose build
python3 scripts/smoke_container.py
```

The test uses a unique Compose project, an empty temporary configuration directory,
a random loopback port and fictional Maple notes. It checks the built frontend,
readiness with unavailable providers, note creation, cross-site write rejection,
skills and KITE initialization, export, CLI, MCP handshake/tool calls, stopped-library backup and
persistence of notes and manually seeded KITE evidence after container
replacement. It does not call a model or measure extraction quality. It deletes
only its own test containers and volume.
