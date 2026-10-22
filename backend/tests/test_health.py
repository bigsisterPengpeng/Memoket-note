'Regression tests for health.'

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import store  # noqa: E402
from app.database.ingest import asr  # noqa: E402


def test_readiness_does_not_probe_external_services(monkeypatch):
    import app.main as main

    def unexpected(*args, **kwargs):
        raise AssertionError("Readiness must not contact a provider or inspect its credentials")

    monkeypatch.setattr(asr, "healthy", unexpected)
    monkeypatch.setattr(store, "get_active_llm_config", unexpected)
    monkeypatch.setattr(main.httpx, "AsyncClient", unexpected)
    with TestClient(main.app) as client:
        response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_probes_run_concurrently(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")

    async def slow_asr() -> bool:
        await asyncio.sleep(0.3)
        return False

    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k):
            await asyncio.sleep(0.3)
            return _Resp()

    import app.main as main
    monkeypatch.setattr(asr, "healthy", slow_asr)
    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)


    monkeypatch.setattr(store, "llm_configured", lambda: {"configured": True, "source": "env"})

    with TestClient(main.app) as c:
        t0 = time.perf_counter()
        r = c.get("/api/health")
        dt = time.perf_counter() - t0
    assert r.status_code == 200
    body = r.json()
    assert body["llm"]["ok"] is True and body["asr"]["ok"] is False
    assert dt < 0.55, f'\u4e24\u4e2a\u63a2\u6d4b\u4e32\u884c\u4e86\uff1a{dt:.2f}s'
