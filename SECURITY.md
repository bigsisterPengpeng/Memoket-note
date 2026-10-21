# Security

## Deployment boundary

MEMOKET NOTE is designed for a local desktop or trusted development environment.
The X-User-Id header selects a library; it is not an authentication mechanism.
Do not expose the backend directly to an untrusted network. Shared deployments
need authentication, authorization, transport security and access controls.

## Data and credentials

Notes, imported material, model settings and service credentials are stored on
the machine running the backend. AI requests send relevant content to the
configured service. Hosted transcription uploads audio to the chosen provider.
Review configured endpoints before processing confidential material.

Keep .env files, data directories, backups and logs out of version control.
Logs and diagnostic exports may contain note identifiers, paths or content.
Use disposable libraries for tests and benchmarks. The packaged backend requires
an absolute data directory outside the application bundle.

## Reporting a vulnerability

Use the repository's private vulnerability reporting option when it is enabled.
If no private channel is available, ask maintainers for one without posting exploit
details or confidential content in public issues.

Include the affected revision, OS, expected and actual behavior, and a minimal
reproduction using synthetic data. Remove credentials, personal notes, recordings
and private endpoints from attachments.
