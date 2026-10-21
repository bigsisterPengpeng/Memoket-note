"""Speech-to-text provider layer: whisper.cpp / AssemblyAI / Speechmatics.

Every HTTP call goes through an `httpx.MockTransport` (asr._TRANSPORT); no real service, key or
audio is ever touched. Polling sleeps are replaced with a no-op that advances a fake clock.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import store
from app.database.ingest import asr
from app.util import i18n

KEY = "test-key-0000-abcd"


class Recorder:
    """MockTransport handler driven by a routing function; records every request."""

    def __init__(self, route):
        self.route = route
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return self.route(request)


@pytest.fixture()
def mock(monkeypatch):
    """Install a handler: `rec = mock(route)`. Also fakes sleep + clock so polling is instant."""
    clock = {"t": 0.0}

    async def fake_sleep(s):
        clock["t"] += s

    monkeypatch.setattr(asr, "_sleep", fake_sleep)
    monkeypatch.setattr(asr.time, "monotonic", lambda: clock["t"])

    def install(route):
        rec = Recorder(route)
        monkeypatch.setattr(asr, "_TRANSPORT", httpx.MockTransport(rec))
        return rec

    install.clock = clock
    return install


def _use(provider: str, region: str = "", key: str = KEY):
    store.set_provider_config("local", asr_provider=provider,
                              **({f"{provider}_api_key": key, f"{provider}_region": region}
                                 if provider in asr.HOSTED else {}))


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- store / config

def test_active_config_defaults_to_whisper():
    cfg = store.get_active_asr_config()
    assert cfg["provider"] == "whisper"
    assert cfg["base_url"] == store.get_asr_base_url()
    assert cfg["api_key"] == ""


def test_active_config_hosted_provider_and_region():
    _use("speechmatics", "us")
    cfg = asr.active_config()
    assert cfg["provider"] == "speechmatics" and cfg["api_key"] == KEY
    assert cfg["base_url"] == "https://us1.asr.api.speechmatics.com/v2"
    _use("assemblyai", "")
    assert asr.active_config()["base_url"] == "https://api.assemblyai.com"
    _use("assemblyai", "eu")
    assert asr.active_config()["base_url"] == "https://api.eu.assemblyai.com"


def test_unknown_stored_provider_falls_back_to_whisper():
    store.set_provider_config("local", asr_provider="nonsense")
    assert store.get_active_asr_config()["provider"] == "whisper"


# ---------------------------------------------------------------- whisper

def test_whisper_posts_multipart_and_filters_hallucinations(mock):
    store.set_provider_config("local", asr_base_url="http://whisper.local:8081")

    def route(req):
        assert req.url == "http://whisper.local:8081/v1/audio/transcriptions"
        assert b'name="file"' in req.content
        # The stock hallucination ("thanks for watching, see you next time") must be dropped.
        return httpx.Response(200, json={"text": 'hello world! \u8c22\u8c22\u89c2\u770b\uff0c\u4e0b\u6b21\u89c1\uff01'})

    mock(route)
    assert run(asr.transcribe(b"RIFF", "a.wav")) == "hello world!"


# ---------------------------------------------------------------- AssemblyAI

def _assemblyai_route(statuses, final="completed", text="hello from assemblyai", error=""):
    polls = iter(statuses)

    def route(req):
        assert req.headers["authorization"] == KEY          # raw key, no Bearer prefix
        path = req.url.path
        if req.method == "POST" and path == "/v2/upload":
            assert req.content == b"AUDIO"
            assert req.headers["content-type"] == "application/octet-stream"
            return httpx.Response(200, json={"upload_url": "https://cdn.example/u1"})
        if req.method == "POST" and path == "/v2/transcript":
            return httpx.Response(200, json={"id": "t1", "status": "queued"})
        if req.method == "GET" and path == "/v2/transcript/t1":
            status = next(polls, final)
            if status == 429:
                return httpx.Response(429, headers={"Retry-After": "1"})
            body = {"id": "t1", "status": status}
            if status == "completed":
                body["text"] = text
            if status == "error":
                body["error"] = error
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    return route


def test_assemblyai_upload_create_poll_done(mock):
    _use("assemblyai")
    rec = mock(_assemblyai_route(["queued", "processing", 429, "processing"]))
    assert run(asr.transcribe(b"AUDIO", "a.wav")) == "hello from assemblyai"
    create = next(r for r in rec.seen if r.url.path == "/v2/transcript")
    body = json.loads(create.content)
    assert body == {"audio_url": "https://cdn.example/u1", "language_detection": True}
    assert all(r.url.host == "api.assemblyai.com" for r in rec.seen)
    assert sum(r.url.path == "/v2/transcript/t1" for r in rec.seen) == 5


def test_assemblyai_explicit_language_and_eu_host(mock):
    _use("assemblyai", "eu")
    rec = mock(_assemblyai_route([]))
    run(asr.transcribe(b"AUDIO", language="en-US"))
    create = next(r for r in rec.seen if r.url.path == "/v2/transcript")
    assert json.loads(create.content)["language_code"] == "en_us"
    assert all(r.url.host == "api.eu.assemblyai.com" for r in rec.seen)


def test_assemblyai_job_error_is_reported(mock):
    _use("assemblyai")
    mock(_assemblyai_route(["processing"], final="error", error="File does not appear to contain audio."))
    with pytest.raises(asr.AsrJobError) as ei:
        run(asr.transcribe(b"AUDIO"))
    msg = asr.describe_error(ei.value)
    assert msg.startswith("AssemblyAI could not transcribe this recording")
    assert "contain audio" in msg


def test_assemblyai_timeout_is_bounded(mock, monkeypatch):
    _use("assemblyai")
    monkeypatch.setattr(asr, "_poll_timeout", lambda: 60.0)
    rec = mock(_assemblyai_route([], final="processing"))
    with pytest.raises(asr.AsrTimeout):
        run(asr.transcribe(b"AUDIO"))
    polls = sum(r.url.path == "/v2/transcript/t1" for r in rec.seen)
    assert 5 < polls < 30                               # backing off, not a busy loop
    assert mock.clock["t"] == pytest.approx(60.0)
    assert "within 1 minutes" in asr.describe_error(asr.AsrTimeout("assemblyai", 60.0))


def test_assemblyai_rejected_key_maps_to_sentence(mock):
    _use("assemblyai")
    mock(lambda req: httpx.Response(401, json={"error": "Authentication error"}))
    with pytest.raises(httpx.HTTPStatusError) as ei:
        run(asr.transcribe(b"AUDIO"))
    msg = asr.describe_error(ei.value)
    assert "AssemblyAI rejected the API key (401)" in msg
    assert KEY not in msg


# ---------------------------------------------------------------- Speechmatics

def _speechmatics_route(statuses, final="done", errors=None):
    polls = iter(statuses)

    def route(req):
        assert req.headers["authorization"] == f"Bearer {KEY}"
        path = req.url.path
        if req.method == "POST" and path == "/v2/jobs":
            assert b'name="data_file"' in req.content
            assert b'name="config"' in req.content
            return httpx.Response(201, json={"id": "j1"})
        if req.method == "GET" and path == "/v2/jobs/j1":
            status = next(polls, final)
            job = {"id": "j1", "status": status}
            if errors:
                job["errors"] = errors
            return httpx.Response(200, json={"job": job})
        if req.method == "GET" and path == "/v2/jobs/j1/transcript":
            assert req.url.params["format"] == "txt"
            return httpx.Response(200, text="hello from speechmatics\n")
        return httpx.Response(404)

    return route


def _config_of(req: httpx.Request) -> dict:
    body = req.content.decode()
    part = body.split('name="config"', 1)[1]
    return json.loads(part.split("\r\n\r\n", 1)[1].split("\r\n--", 1)[0])


def test_speechmatics_submit_poll_fetch_txt(mock):
    _use("speechmatics")
    rec = mock(_speechmatics_route(["running", "running"]))
    assert run(asr.transcribe(b"AUDIO", "a.m4a", language="zh")) == "hello from speechmatics"
    submit = next(r for r in rec.seen if r.method == "POST")
    assert _config_of(submit) == {"type": "transcription", "transcription_config": {
        "language": "cmn", "model": "enhanced"}}
    assert all(r.url.host == "eu1.asr.api.speechmatics.com" for r in rec.seen)


def test_speechmatics_auto_language_and_us_region(mock):
    _use("speechmatics", "us")
    rec = mock(_speechmatics_route([]))
    run(asr.transcribe(b"AUDIO"))
    assert _config_of(rec.seen[0])["transcription_config"]["language"] == "auto"
    assert rec.seen[0].url.host == "us1.asr.api.speechmatics.com"


def test_speechmatics_rejected_job(mock):
    _use("speechmatics")
    mock(_speechmatics_route([], final="rejected", errors=[{"message": "unsupported file format"}]))
    with pytest.raises(asr.AsrJobError) as ei:
        run(asr.transcribe(b"AUDIO"))
    assert "Speechmatics could not transcribe this recording: unsupported file format" == \
        asr.describe_error(ei.value)


def test_speechmatics_no_credit(mock):
    _use("speechmatics")
    mock(lambda req: httpx.Response(402))
    with pytest.raises(httpx.HTTPStatusError) as ei:
        run(asr.transcribe(b"AUDIO"))
    assert "no credit" in asr.describe_error(ei.value)


# ---------------------------------------------------------------- missing key / errors / health

@pytest.mark.parametrize("provider,label", [("assemblyai", "AssemblyAI"), ("speechmatics", "Speechmatics")])
def test_missing_key_makes_no_request(mock, provider, label):
    store.set_provider_config("local", asr_provider=provider)
    rec = mock(lambda req: httpx.Response(500))
    with pytest.raises(asr.AsrConfigError) as ei:
        run(asr.transcribe(b"AUDIO"))
    assert rec.seen == []
    assert asr.describe_error(ei.value) == f"No API key for {label} - add it in Settings under Voice service"


def test_describe_error_in_chinese():
    token = i18n.ctx_lang.set("zh")
    try:
        got = asr.describe_error(asr.AsrConfigError("assemblyai"))
    finally:
        i18n.ctx_lang.reset(token)
    assert got.startswith("AssemblyAI ") and "API key" in got and got != \
        "No API key for AssemblyAI - add it in Settings under Voice service"


def test_hosted_connect_error_names_provider():
    _use("speechmatics")
    got = asr.describe_error(httpx.ConnectError("dns"))
    assert got == "Could not reach Speechmatics (https://eu1.asr.api.speechmatics.com/v2) - check the network connection"


def test_healthy_reflects_provider(mock):
    rec = mock(lambda req: httpx.Response(200))
    assert run(asr.healthy()) is True                    # whisper: GET /health
    assert rec.seen[-1].url.path == "/health"
    store.set_provider_config("local", asr_provider="assemblyai")
    n = len(rec.seen)
    assert run(asr.healthy()) is False                   # hosted, no key
    _use("assemblyai")
    assert run(asr.healthy()) is True
    assert len(rec.seen) == n                            # hosted health never spends the rate limit


# ---------------------------------------------------------------- routers

def _client():
    from app.main import app
    return TestClient(app)


def test_settings_round_trip_never_returns_keys():
    with _client() as c:
        out = c.post("/api/settings/provider", json={
            "provider": "local", "asr_provider": "speechmatics",
            "speechmatics_api_key": KEY, "speechmatics_region": "us"}).json()
        assert out["asr_provider"] == "speechmatics"
        assert out["speechmatics_api_key_set"] is True
        assert out["speechmatics_api_key_preview"] == "...abcd"
        assert out["speechmatics_region"] == "us"
        assert out["assemblyai_api_key_set"] is False and out["assemblyai_region"] == "us"
        assert KEY not in json.dumps(out)
        # Blank key = keep; switching provider keeps the other provider's key.
        out = c.post("/api/settings/provider", json={
            "provider": "local", "asr_provider": "assemblyai", "speechmatics_api_key": "  "}).json()
        assert out["asr_provider"] == "assemblyai" and out["speechmatics_api_key_set"] is True
        got = c.get("/api/settings/provider").json()
        assert got["asr_provider"] == "assemblyai" and got["speechmatics_region"] == "us"
        assert c.post("/api/settings/provider", json={"provider": "local", "asr_provider": "x"}).status_code == 400
        assert c.post("/api/settings/provider", json={
            "provider": "local", "assemblyai_region": "mars"}).status_code == 400


def test_health_reports_active_provider(monkeypatch):
    async def ok():
        return True
    monkeypatch.setattr(asr, "healthy", ok)
    _use("assemblyai", "eu")
    with _client() as c:
        body = c.get("/api/health").json()
    assert body["asr"]["provider"] == "assemblyai"
    assert body["asr"]["base_url"] == "https://api.eu.assemblyai.com"
    assert KEY not in json.dumps(body)


@pytest.mark.parametrize("provider,host,path,auth", [
    ("assemblyai", "api.assemblyai.com", "/v2/transcript", KEY),
    ("speechmatics", "eu1.asr.api.speechmatics.com", "/v2/jobs", f"Bearer {KEY}"),
])
def test_provider_test_hosted_uses_saved_key_and_no_audio(mock, provider, host, path, auth):
    _use(provider)
    rec = mock(lambda req: httpx.Response(200, json={}))
    with _client() as c:
        out = c.post("/api/settings/provider/test", json={
            "kind": "asr", "base_url": "", "asr_provider": provider}).json()
    assert out["ok"] is True and "accepted the API key" in out["message"]
    assert len(rec.seen) == 1
    req = rec.seen[0]
    assert req.method == "GET" and req.url.host == host and req.url.path == path
    assert req.headers["authorization"] == auth and req.url.params["limit"] == "1"
    assert KEY not in out["message"]


def test_provider_test_hosted_bad_key_and_missing_key(mock):
    rec = mock(lambda req: httpx.Response(401))
    with _client() as c:
        out = c.post("/api/settings/provider/test", json={
            "kind": "asr", "base_url": "", "asr_provider": "speechmatics", "api_key": "typed-key",
            "region": "us"}).json()
        assert out["ok"] is False and "rejected the API key (401)" in out["message"]
        assert rec.seen[0].url.host == "us1.asr.api.speechmatics.com"
        out = c.post("/api/settings/provider/test", json={
            "kind": "asr", "base_url": "", "asr_provider": "assemblyai"}).json()
        assert out["ok"] is False and out["message"].startswith("No API key for AssemblyAI")
        assert len(rec.seen) == 1
        assert c.post("/api/settings/provider/test", json={
            "kind": "asr", "base_url": "", "asr_provider": "bogus"}).status_code == 400


def test_provider_test_whisper_still_probes_health(monkeypatch):
    from app.routers import settings as S
    seen = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def get(self, url, **k):
            seen.append(url)
            return httpx.Response(200)

        async def aclose(self):
            pass

    monkeypatch.setattr(S.httpx, "AsyncClient", FakeClient)
    with _client() as c:
        out = c.post("/api/settings/provider/test", json={
            "kind": "asr", "base_url": "http://w.local:8081", "asr_provider": "whisper"}).json()
    assert out["ok"] is True and out["message"].startswith("Voice service at http://w.local:8081")
    assert seen == ["http://w.local:8081/health"]


def test_poll_budget_cancels_a_stalled_request(monkeypatch):
    monkeypatch.setattr(asr, "_poll_timeout", lambda: 0.02)
    cancelled = []

    async def stalled():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    with pytest.raises(asr.AsrTimeout):
        run(asr._poll_until("speechmatics", stalled))
    assert cancelled == [True]


def test_poll_does_not_start_another_request_after_deadline(mock, monkeypatch):
    monkeypatch.setattr(asr, "_poll_timeout", lambda: 1.0)
    calls = []

    async def step():
        calls.append(True)
        return None if len(calls) == 1 else "late completion"

    with pytest.raises(asr.AsrTimeout):
        run(asr._poll_until("assemblyai", step))
    assert calls == [True]
