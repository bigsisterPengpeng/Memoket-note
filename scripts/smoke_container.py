"""Exercise the built Compose image using an isolated, disposable library."""

from __future__ import annotations

import io
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="memoket-note:local", help="Locally built image to exercise")
    args = parser.parse_args()
    project = "memoket-smoke-" + uuid.uuid4().hex[:12]
    env = os.environ.copy()
    env.update(MEMOKET_NOTE_PORT="0", LLM_BASE_URL="http://127.0.0.1:9/v1",
               WHISPER_BASE_URL="http://127.0.0.1:9")
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="memoket-compose-") as directory:
        # Resolve the optional .env beside this copy, away from real credentials.
        compose_file = Path(directory) / "compose.yaml"
        shutil.copyfile(ROOT / "compose.yaml", compose_file)
        override = Path(directory) / "image.json"
        override.write_text(json.dumps({"services": {"note": {"image": args.image}}}))
        empty_env = Path(directory) / "smoke.env"
        empty_env.touch()
        command = ["docker", "compose", "--env-file", str(empty_env),
                   "--project-name", project, "-f", str(compose_file), "-f", str(override)]

        def compose(*args: str) -> str:
            return subprocess.check_output(command + list(args), env=env, cwd=directory,
                                           text=True, timeout=180).strip()

        def address() -> str:
            return "http://" + compose("port", "note", "8000")

        base = ""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path: str, body: dict | None = None, origin: str | None = None):
            headers = {"X-User-Id": "container-smoke"}
            if origin:
                headers["Origin"] = origin
            data = None
            if body is not None:
                headers["Content-Type"] = "application/json"
                data = json.dumps(body).encode()
            req = urllib.request.Request(base + path, data=data, headers=headers)
            with opener.open(req, timeout=15) as response:
                return response.read(), response.headers

        try:
            compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "90")
            base = address()
            info = json.loads(subprocess.check_output(
                ["docker", "inspect", compose("ps", "-q", "note")], text=True))[0]
            assert info["Config"]["User"] == "10001:10001"
            assert info["HostConfig"]["ReadonlyRootfs"]
            assert all(p["HostIp"] == "127.0.0.1"
                       for p in info["NetworkSettings"]["Ports"]["8000/tcp"])
            assert any(m["Type"] == "volume" and m["Destination"] == "/data" for m in info["Mounts"])
            checks.append("non-root runtime, read-only image, loopback port and named data volume")

            assert json.loads(request("/api/ready")[0]) == {"status": "ok"}
            html, headers = request("/")
            assert b"MEMOKET NOTE" in html and "no-store" in headers["Cache-Control"]
            script = re.search(rb'src="(/assets/[^" ]+\.js)"', html)
            assert script and request(script[1].decode())[0]
            checks.append("readiness and built frontend without available model/transcription providers")

            content = "# Maple field notes\n\nThe fictional team approved amber shelf labels.\n"
            note = json.loads(request("/api/notes", {"title": "Maple container check", "content": content}, base)[0])
            assert note["content"] == content
            try:
                request("/api/notes", {"title": "Rejected cross-site write"}, "https://example.invalid")
            except urllib.error.HTTPError as exc:
                assert exc.code == 403
            else:
                raise AssertionError("Cross-site write was accepted")
            checks.append("same-origin note creation and cross-site write rejection")

            assert json.loads(request("/api/skills")[0])
            recall = json.loads(request("/api/memory/recall", {"query": "Maple labels"})[0])
            assert recall["kb_empty"] and not recall["facts"]
            checks.append("built-in skills and fresh KITE library initialize on the data volume")

            fact_text = "The fictional Maple team approved amber shelf labels."
            seed = (
                "import json; from app.database.kite.kite_memory import UserMemory; "
                "m = UserMemory('container-smoke'); m.ensure(); "
                "print(json.dumps(m.add_manual_fact('maple-container', " + repr(fact_text) +
                ", date='2026-10-22', title='Fictional Maple source')))"
            )
            fact = json.loads(compose("exec", "-T", "note", "python", "-c", seed))
            evidence = json.loads(request("/api/memory/facts/" + fact["id"])[0])
            assert evidence["text"] == fact_text and fact_text in evidence["sources"]

            exported = request("/api/export/markdown")[0]
            with zipfile.ZipFile(io.BytesIO(exported)) as archive:
                assert any(content.encode() in archive.read(name) for name in archive.namelist() if name.endswith(".md"))
            cli = json.loads(compose("exec", "-T", "note", "python", "-m", "app.cli",
                                     "--user", "container-smoke", "get", note["id"]))
            assert cli["content"] == content
            mcp_check = """
import asyncio, os, sys
from mcp import Client, StdioServerParameters

async def check():
    env = {**os.environ, 'MEMOKET_NOTE_USER': 'container-smoke'}
    params = StdioServerParameters(command=sys.executable, args=['-m', 'app.mcp_server'], env=env)
    async with Client(params, read_timeout_seconds=20) as client:
        tools = await client.list_tools()
        assert {'list_notes', 'get_note', 'recall_memory'} <= {tool.name for tool in tools.tools}
        result = await client.call_tool('list_notes', {'query': 'Maple container check'})
        assert not result.is_error
        assert any(note['title'] == 'Maple container check' for note in result.structured_content['notes'])

asyncio.run(check())
"""
            compose("exec", "-T", "note", "python", "-c", mcp_check)
            checks.append("Markdown export, NOTE CLI and a real MCP handshake/tool call")

            compose("stop", "note")
            backup = Path(directory) / "library-backup"
            compose("cp", "note:/data", str(backup))
            with sqlite3.connect(backup / "notes.sqlite3") as database:
                row = database.execute("SELECT content FROM notes WHERE id = ?", (note["id"],)).fetchone()
                assert row and row[0] == content
            assert fact_text in (backup / "container-smoke/codebook.xml").read_text()
            checks.append("stopped-library backup includes notes and KITE source evidence")

            compose("up", "-d", "--no-build", "--force-recreate", "--wait", "--wait-timeout", "90")
            base = address()
            restored = json.loads(request("/api/notes/" + note["id"])[0])
            assert restored["content"] == content
            evidence = json.loads(request("/api/memory/facts/" + fact["id"])[0])
            assert evidence["text"] == fact_text and fact_text in evidence["sources"]
            checks.append("notes and KITE source evidence survive container replacement")
            print(json.dumps({"passed": True, "checks": checks}, indent=2))
        finally:
            # Only remove resources belonging to this newly generated smoke project.
            compose("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
