"""Availability checks must not start native apps or read account content."""

from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.connectors import memoket
from app.main import app
from app.routers import import_sources


def unexpected(*args, **kwargs):
    raise AssertionError("An availability check started a process")


@pytest.mark.parametrize("platform,tool,available", [
    ("linux", "/usr/bin/osascript", False),
    ("darwin", None, False),
    ("darwin", "/usr/bin/osascript", True),
])
def test_apple_availability_uses_backend_environment(monkeypatch, platform, tool, available):
    monkeypatch.setattr(import_sources, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(import_sources.shutil, "which", lambda name: tool)
    monkeypatch.setattr(import_sources, "subprocess", SimpleNamespace(run=unexpected))
    response = TestClient(app).get("/api/import/apple/available")
    assert response.status_code == 200
    result = response.json()
    assert result["available"] is available
    assert bool(result["reason"]) is not available


@pytest.mark.parametrize("installed", [True, False])
def test_memoket_availability_does_not_run_cli_or_verify_login(monkeypatch, installed):
    monkeypatch.setattr(memoket.shutil, "which", lambda name: "/opt/bin/memoket" if installed else None)
    monkeypatch.setattr(memoket, "subprocess", SimpleNamespace(run=unexpected))
    response = TestClient(app).get("/api/connectors/memoket/available")
    assert response.status_code == 200
    result = response.json()
    assert result["available"] is installed
    assert bool(result["reason"]) is not installed
    assert "/opt/bin" not in str(result)
    assert "version" not in result


def test_memoket_availability_rejects_unsupported_launcher(monkeypatch):
    monkeypatch.setattr(memoket.shutil, "which", lambda name: "memoket.cmd")
    monkeypatch.setattr(memoket, "subprocess", SimpleNamespace(run=unexpected))
    result = TestClient(app).get("/api/connectors/memoket/available").json()
    assert result["available"] is False
    assert "Batch launchers" in result["reason"]
