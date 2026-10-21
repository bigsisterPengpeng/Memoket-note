"""Local HTTP client shared by the NOTE CLI and MCP server."""

from __future__ import annotations

import os
import re
from urllib.parse import quote, urlsplit

import httpx


class WorkspaceClient:
    def __init__(self, url: str | None = None, user: str | None = None):
        self.url = (url or os.environ.get("MEMOKET_NOTE_URL", "http://127.0.0.1:8000")).rstrip("/")
        parsed = urlsplit(self.url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("MEMOKET_NOTE_URL must be a loopback HTTP origin")
        self.user = user or os.environ.get("MEMOKET_NOTE_USER", "default")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", self.user) or self.user in {".", ".."}:
            raise ValueError("Invalid workspace user ID")

    def request(self, method: str, path: str, **kwargs):
        with httpx.Client(base_url=self.url, headers={"X-User-Id": self.user},
                          timeout=180, trust_env=False, follow_redirects=False) as client:
            response = client.request(method, path, **kwargs)
        if response.is_error:
            try:
                detail = response.json().get("detail", response.reason_phrase)
            except ValueError:
                detail = response.reason_phrase
            raise ValueError(f"NOTE {response.status_code}: {detail}")
        return response.json()

    def notes(self, query: str = ""):
        result = self.request("GET", "/api/notes/brief", params={"q": query})
        result["notes"] = result["notes"][:100]
        return result

    def note(self, note_id: str):
        return self.request("GET", f"/api/notes/{quote(note_id, safe='')}")

    def create(self, title: str, content: str):
        return self.request("POST", "/api/notes", json={"title": title, "content": content})

    def recall(self, query: str, limit: int = 8):
        if not query.strip() or not 1 <= limit <= 30:
            raise ValueError("Recall needs a query and a limit between 1 and 30")
        return self.request("POST", "/api/memory/recall", json={"query": query, "limit": limit})

    def revise(self, note_id: str, selection: str, action: str = "polish"):
        if action not in {"polish", "rewrite"}:
            raise ValueError("Action must be polish or rewrite")
        note = self.note(note_id)
        if not selection.strip() or selection not in note["content"]:
            raise ValueError("Select an existing passage from the note")
        return self.request("POST", "/api/rewrite", json={
            "content": note["content"], "selection": selection, "intent": action})

    def job(self, job_id: str):
        return self.request("GET", f"/api/ingest/jobs/{quote(job_id, safe='')}")

    def memoket_read(self, tool: str, arguments: dict):
        return self.request("POST", "/api/connectors/memoket/read",
                            json={"tool": tool, "arguments": arguments})

    def memoket_import(self, conversation_id: str, title: str, to: str = "notes"):
        return self.request("POST", "/api/connectors/memoket/import", json={
            "conversation_id": conversation_id, "title": title, "to": to})
