"""Provider presets (`util/providers.py`) + per-provider credentials (`provider_credentials`) +
`family`-driven request bodies.

    cd backend && python -m pytest tests/test_providers.py -v

Covers: registry sanity; switching providers keeps keys; the legacy `gpt_*` / `local_*` columns keep
feeding `gpt` / `local`; `get_active_llm_config().family` decides whether `llm._payload` sends
`max_tokens`; the `/settings/provider` API shape (keys only as "set" + last four chars); the
`/provider/test` probe body per family (HTTP fully stubbed, no network).
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import store  # noqa: E402
from app.routers import settings as S  # noqa: E402
from app.util import llm, providers  # noqa: E402

_LOCAL_ENV = SimpleNamespace(llm_base_url="http://local-model:8080/v1", llm_api_key="no-key",
                             llm_model="muse-glimmer-30b", asr_provider="whisper",
                             whisper_base_url="http://127.0.0.1:8081")
_LOCAL_ACTIVE = {"base_url": "http://local-model:8080/v1", "api_key": "no-key",
                 "model": "muse-glimmer-30b", "provider": "local", "family": "local"}


@pytest.fixture()
def local_env(monkeypatch):
    monkeypatch.setattr(store, "get_settings", lambda: _LOCAL_ENV)


# ==================================================================== 1. registry

REQUIRED = {"openai", "anthropic", "gemini", "xai", "deepseek", "qwen", "moonshot", "zhipu",
            "minimax", "mistral", "groq", "openrouter", "ollama", "lmstudio", "gpt", "local"}


def test_registry_ids_unique_urls_valid_family_and_group_known():
    ids = [p["id"] for p in providers.preset_dicts()]
    assert len(ids) == len(set(ids)), "duplicate preset id"
    assert REQUIRED <= set(ids)
    for p in providers.PROVIDERS.values():
        assert re.match(r"^https?://[^\s/]+", p.base_url), p.id
        assert not p.base_url.endswith("/"), f"{p.id} base_url has a trailing slash (would produce //chat/completions)"
        assert p.family in providers.FAMILIES, p.id
        assert p.group in providers.GROUPS, p.id
        assert p.label.strip()
        assert len(p.models) <= 4, p.id
    # every hosted preset suggests at least two model names (LM Studio's model id is whatever its UI
    # loaded; the docs list none)
    for p in providers.PROVIDERS.values():
        if p.group == "hosted":
            assert len(p.models) >= 2, p.id


def test_legacy_ids_unchanged_gpt_is_openai_family_local_needs_no_key():
    assert providers.PROVIDERS["gpt"].family == "openai"
    assert providers.PROVIDERS["local"].family == "local"
    for pid in ("ollama", "lmstudio", "local"):
        assert providers.PROVIDERS[pid].needs_key is False
        assert providers.PROVIDERS[pid].family == "local"
    assert providers.PROVIDERS["openai"].family == "openai"
    for pid in ("anthropic", "gemini", "deepseek", "qwen", "moonshot", "zhipu", "minimax", "mistral",
                "groq", "openrouter", "xai"):
        assert providers.PROVIDERS[pid].family == "compatible", pid
        assert providers.PROVIDERS[pid].needs_key is True, pid


def test_family_of_and_family_for_fallback_direction():
    assert providers.family_of("gpt") == "openai"
    assert providers.family_of("ollama") == "local"
    assert providers.family_of("anthropic") == "compatible"
    assert providers.family_of("azure") == providers.DEFAULT_FAMILY == "compatible"
    assert providers.family_of(None) == "compatible"
    # the new field wins; else the provider id is looked up; else the safe side (both limit fields sent)
    assert providers.family_for({"family": "local", "provider": "gpt"}) == "local"
    assert providers.family_for({"provider": "gpt"}) == "openai"
    assert providers.family_for({"provider": "deepseek"}) == "compatible"
    assert providers.family_for({}) == "compatible"
    assert providers.family_for(None) == "compatible"
    assert providers.family_for({"family": "nonsense", "provider": "gpt"}) == "openai"


# ==================================================================== 2. per-provider credentials

def test_switching_providers_keeps_keys(local_env):
    store.set_provider_config("openai", api_key="sk-oa", model="gpt-6-luna")
    store.set_provider_config("deepseek", api_key="sk-ds", model="deepseek-flash",
                              base_url="https://api.deepseek.com/")
    assert store.get_active_llm_config() == {
        "base_url": "https://api.deepseek.com", "api_key": "sk-ds", "model": "deepseek-flash",
        "provider": "deepseek", "family": "compatible"}
    store.set_provider_config("openai")          # switch only, no fields
    assert store.get_active_llm_config() == {
        "base_url": "https://api.openai.com/v1", "api_key": "sk-oa", "model": "gpt-6-luna",
        "provider": "openai", "family": "openai"}
    assert store.get_provider_credentials("deepseek") == {
        "api_key": "sk-ds", "model": "deepseek-flash", "base_url": "https://api.deepseek.com"}
    assert store.llm_configured() == {"configured": True, "source": "openai"}


def test_none_keeps_empty_clears_empty_url_falls_back_to_preset_default(local_env):
    store.set_provider_config("zhipu", api_key="sk-z", model="glm-5.3", base_url="https://gw.example/v4")
    store.set_provider_config("zhipu", api_key=None, model=None, base_url=None)
    assert store.get_provider_credentials("zhipu") == {
        "api_key": "sk-z", "model": "glm-5.3", "base_url": "https://gw.example/v4"}
    store.set_provider_config("zhipu", base_url="")
    assert store.get_provider_credentials("zhipu")["base_url"] == ""
    assert store.get_active_llm_config()["base_url"] == providers.PROVIDERS["zhipu"].base_url
    store.set_provider_config("zhipu", api_key="")
    assert store.get_provider_credentials("zhipu")["api_key"] == ""
    # key cleared: a key-requiring provider falls back to the local model rather than sending an empty key
    assert store.get_active_llm_config() == _LOCAL_ACTIVE


def test_legacy_columns_still_feed_gpt_and_local_new_fields_land_in_them_not_in_new_table(local_env):
    store.set_provider_config("gpt", gpt_api_key="sk-old", gpt_model="gpt-4.1-mini")       # legacy write
    assert store.get_provider_credentials("gpt") == {
        "api_key": "sk-old", "model": "gpt-4.1-mini", "base_url": "https://api.openai.com/v1"}
    store.set_provider_config("gpt", api_key="sk-new", base_url="https://gw.example.com/v1/")   # new-style write
    cfg = store.get_provider_config()
    assert cfg["gpt_api_key"] == "sk-new" and cfg["gpt_base_url"] == "https://gw.example.com/v1"
    assert cfg["gpt_model"] == "gpt-4.1-mini"
    store.set_provider_config("gpt", base_url="")                                         # empty = preset default
    assert store.get_provider_config()["gpt_base_url"] == "https://api.openai.com/v1"
    store.set_provider_config("gpt", model="")                                            # empty gpt model = keep
    assert store.get_provider_config()["gpt_model"] == "gpt-4.1-mini"
    assert store.get_active_llm_config()["family"] == "openai"

    store.set_provider_config("local", base_url="http://127.0.0.1:1234/v1/", model="lm", api_key="k")
    cfg = store.get_provider_config()
    assert (cfg["local_base_url"], cfg["local_model"], cfg["local_api_key"]) == ("http://127.0.0.1:1234/v1", "lm", "k")
    assert store.get_active_llm_config() == {
        "base_url": "http://127.0.0.1:1234/v1", "api_key": "k", "model": "lm",
        "provider": "local", "family": "local"}
    with store.connect() as c:
        assert c.execute("SELECT count(*) FROM provider_credentials").fetchone()[0] == 0, \
            "gpt / local must not get rows in the new table: two copies would raise the question which one to read"


def test_key_requiring_provider_without_key_falls_back_to_local_and_counts_as_unconfigured(local_env, monkeypatch):
    from app.util import config as C
    monkeypatch.setattr(C, "env_set", lambda name: False)
    store.set_provider_config("anthropic", model="claude-sonnet-5-5")
    assert store.get_active_llm_config() == _LOCAL_ACTIVE
    assert store.llm_configured() == {"configured": False, "source": "default"}


def test_ollama_needs_no_key_a_model_name_is_enough(local_env):
    store.set_provider_config("ollama", model="qwen3:8b")
    assert store.get_active_llm_config() == {
        "base_url": "http://127.0.0.1:11434/v1", "api_key": "no-key", "model": "qwen3:8b",
        "provider": "ollama", "family": "local"}
    assert store.llm_configured() == {"configured": True, "source": "ollama"}


def test_missing_model_name_is_not_configured(local_env, monkeypatch):
    from app.util import config as C
    monkeypatch.setattr(C, "env_set", lambda name: False)
    store.set_provider_config("openai", api_key="sk-x")
    assert store.llm_configured() == {"configured": False, "source": "default"}


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        store.set_provider_config("azure")
    with pytest.raises(ValueError):
        store.set_provider_credentials("gpt", api_key="x")


# ==================================================================== 3. family -> request body

@pytest.mark.parametrize("pid,wants_max_tokens", [
    ("openai", False), ("gpt", False),
    ("anthropic", True), ("deepseek", True), ("ollama", True), ("local", True),
])
def test_family_decides_whether_max_tokens_is_sent(monkeypatch, pid, wants_max_tokens):
    monkeypatch.setattr(store, "get_active_llm_config", lambda: {
        "base_url": "http://x/v1", "api_key": "k", "model": "m",
        "provider": pid, "family": providers.PROVIDERS[pid].family})
    body = llm._payload([{"role": "user", "content": "hi"}], stream=False,
                        max_tokens=100, temperature=0.3, effort="low")
    assert ("max_tokens" in body) is wants_max_tokens
    assert body["max_completion_tokens"] == 100 + llm.REASONING_RESERVE


def test_family_flows_from_store_into_payload(local_env):
    store.set_provider_config("anthropic", api_key="sk-a", model="claude-sonnet-5-5")
    body = llm._payload([], stream=False, max_tokens=10, temperature=0.3, effort="low")
    assert "max_tokens" in body and body["model"] == "claude-sonnet-5-5"
    store.set_provider_config("openai", api_key="sk-o", model="gpt-6-luna")
    body = llm._payload([], stream=False, max_tokens=10, temperature=0.3, effort="low")
    assert "max_tokens" not in body and body["model"] == "gpt-6-luna"


def test_vision_following_the_writing_model_picks_the_limit_field_by_family(local_env):
    """`get_active_vision_config` spreads `get_active_llm_config()`, so family comes along."""
    from app.editor import vision
    sent: list[dict] = []

    class _C:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            sent.append(dict(json))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]},
                                  request=httpx.Request("POST", url))

    store.set_provider_config("openai", api_key="sk-o", model="gpt-6-luna")
    assert store.get_active_vision_config()["family"] == "openai"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(vision.httpx, "AsyncClient", _C)
        asyncio.run(vision.ask_image("read", b"\x89PNG", max_tokens=24))
    assert "max_completion_tokens" in sent[0] and "max_tokens" not in sent[0]
    store.set_provider_config("ollama", model="qwen3-vl:8b")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(vision.httpx, "AsyncClient", _C)
        asyncio.run(vision.ask_image("read", b"\x89PNG", max_tokens=24))
    assert "max_tokens" in sent[1] and "max_completion_tokens" not in sent[1]


# ==================================================================== 4. /settings/provider

def _client(tmp_path, monkeypatch) -> TestClient:
    from app.main import app
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    return TestClient(app, headers={"X-User-Id": "u1"})


def test_api_lists_presets_returns_key_tail_only_and_keeps_keys_across_switches(tmp_path, monkeypatch, local_env):
    with _client(tmp_path, monkeypatch) as c:
        out = c.get("/api/settings/provider").json()
        ids = [p["id"] for p in out["providers"]]
        assert ids == [p["id"] for p in providers.preset_dicts()]
        openai = next(p for p in out["providers"] if p["id"] == "openai")
        assert openai["base_url"] == "https://api.openai.com/v1" and openai["needs_key"] and openai["family"] == "openai"
        assert openai["models"] and openai["key_set"] is False
        local = next(p for p in out["providers"] if p["id"] == "local")
        # the `local` entry's default address = .env / factory default (the router reads its own get_settings)
        real = S.get_settings()
        assert local["base_url"] == real.llm_base_url
        if real.llm_model:
            assert local["models"][0] == real.llm_model

        r = c.post("/api/settings/provider", json={"provider": "openai", "api_key": "sk-abcd1234", "model": "gpt-6-luna"})
        assert r.status_code == 200, r.text
        assert "sk-abcd1234" not in r.text, "the key must never be echoed back"
        out = r.json()
        assert out["provider"] == out["active_provider"] == "openai" and out["active_family"] == "openai"
        assert out["active_model"] == "gpt-6-luna" and out["configured"] and out["configured_source"] == "openai"
        openai = next(p for p in out["providers"] if p["id"] == "openai")
        assert openai["key_set"] and openai["key_preview"] == "...1234" and openai["model"] == "gpt-6-luna"

        out = c.post("/api/settings/provider", json={"provider": "moonshot", "api_key": "sk-moon5678", "model": "kimi-k3"}).json()
        assert out["active_provider"] == "moonshot" and out["active_url"] == "https://api.moonshot.cn/v1"
        # switch back without any field: the openai key is still there
        out = c.post("/api/settings/provider", json={"provider": "openai"}).json()
        assert out["active_provider"] == "openai" and out["active_model"] == "gpt-6-luna"
        assert next(p for p in out["providers"] if p["id"] == "moonshot")["key_set"]
        # explicit empty string clears the key -> falls back to local
        out = c.post("/api/settings/provider", json={"provider": "openai", "api_key": ""}).json()
        assert next(p for p in out["providers"] if p["id"] == "openai")["key_set"] is False
        assert out["active_provider"] == "local"
        # whitespace only = not entered, keep
        c.post("/api/settings/provider", json={"provider": "openai", "api_key": "sk-again"})
        out = c.post("/api/settings/provider", json={"provider": "openai", "api_key": "   "}).json()
        assert next(p for p in out["providers"] if p["id"] == "openai")["key_set"]


def test_api_legacy_fields_still_work_and_bad_input_is_400(tmp_path, monkeypatch, local_env):
    with _client(tmp_path, monkeypatch) as c:
        out = c.post("/api/settings/provider", json={"provider": "gpt", "gpt_api_key": "sk-legacy", "gpt_model": "gpt-4.1-mini"}).json()
        assert out["gpt_api_key_set"] and out["active_provider"] == "gpt" and out["active_family"] == "openai"
        gpt = next(p for p in out["providers"] if p["id"] == "gpt")
        assert gpt["key_set"] and gpt["model"] == "gpt-4.1-mini" and gpt["base_url_saved"] == "https://api.openai.com/v1"
        out = c.post("/api/settings/provider", json={"provider": "local", "local_base_url": "http://127.0.0.1:11434/v1", "local_model": "qwen3:8b"}).json()
        assert out["active_provider"] == "local" and out["configured_source"] == "local"
        assert next(p for p in out["providers"] if p["id"] == "local")["model"] == "qwen3:8b"
        assert c.post("/api/settings/provider", json={"provider": "azure"}).status_code == 400
        assert c.post("/api/settings/provider", json={"provider": "openai", "base_url": "not a url"}).status_code == 400
        assert c.post("/api/settings/provider", json={"provider": "openai", "base_url": "api.openai.com/v1"}).status_code == 400


# ==================================================================== 5. /provider/test probe body

class _FakeClient:
    """`/models` unimplemented (404) so the probe falls through to the minimal completion; records every
    POST body. With `reject_first`, the first completion answers 400 "unsupported parameter <field>"."""

    def __init__(self, reject_first: str = ""):
        self.sent: list[dict] = []
        self.reject_first = reject_first

    async def get(self, url, headers=None):
        return httpx.Response(404, text="no", request=httpx.Request("GET", url))

    async def post(self, url, headers=None, json=None):
        self.sent.append(dict(json))
        if self.reject_first and len(self.sent) == 1:
            body = {"error": {"message": f"Unsupported parameter: '{self.reject_first}'",
                              "type": "invalid_request_error", "param": self.reject_first,
                              "code": "unsupported_parameter"}}
            return httpx.Response(400, content=_dumps(body), request=httpx.Request("POST", url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]},
                              request=httpx.Request("POST", url))

    async def aclose(self): ...


def _dumps(d: dict) -> bytes:
    return json.dumps(d).encode()


@pytest.mark.parametrize("family,field", [("openai", "max_completion_tokens"),
                                          ("compatible", "max_tokens"), ("local", "max_tokens")])
def test_probe_sends_the_limit_field_of_its_family(family, field):
    c = _FakeClient()
    out = asyncio.run(S.probe_endpoint("llm", "http://x/v1", "m", "k", family=family, client=c))
    assert out.ok, out.message
    assert len(c.sent) == 1
    assert {k for k in c.sent[0] if k in ("max_tokens", "max_completion_tokens")} == {field}
    assert c.sent[0][field] == 1


def test_probe_openai_family_swaps_back_to_max_tokens_when_rejected():
    c = _FakeClient(reject_first="max_completion_tokens")
    out = asyncio.run(S.probe_endpoint("llm", "http://x/v1", "m", "k", family="openai", client=c))
    assert out.ok, out.message
    assert c.sent[0]["max_completion_tokens"] == 1 and "max_tokens" not in c.sent[0]
    # second body: field swapped, value carried over, nothing else changed
    assert c.sent[1]["max_tokens"] == 1 and "max_completion_tokens" not in c.sent[1]
    assert c.sent[1]["model"] == "m" and c.sent[1]["messages"] == c.sent[0]["messages"]


def test_probe_compatible_family_swaps_to_max_completion_tokens_when_rejected():
    c = _FakeClient(reject_first="max_tokens")
    out = asyncio.run(S.probe_endpoint("llm", "http://x/v1", "m", "k", family="compatible", client=c))
    assert out.ok, out.message
    assert "max_tokens" in c.sent[0] and "max_completion_tokens" in c.sent[1] and "max_tokens" not in c.sent[1]


def test_test_endpoint_resolves_family_from_provider_then_saved_key_of(tmp_path, monkeypatch):
    seen: list[dict] = []

    async def fake_probe(kind, base_url, model="", api_key="", *, family="compatible", **kw):
        seen.append({"kind": kind, "family": family, "key": api_key})
        return S.ProviderTestOut(ok=True, message="ok")

    monkeypatch.setattr(S, "probe_endpoint", fake_probe)
    with _client(tmp_path, monkeypatch) as c:
        store.set_provider_config("ollama", model="qwen3:8b")
        store.set_provider_config("openai", api_key="sk-saved", model="gpt-6-luna")
        c.post("/api/settings/provider/test", json={"kind": "llm", "base_url": "http://x/v1", "model": "m", "provider": "openai"})
        c.post("/api/settings/provider/test", json={"kind": "llm", "base_url": "http://x/v1", "model": "m", "saved_key_of": "ollama"})
        c.post("/api/settings/provider/test", json={"kind": "llm", "base_url": "http://x/v1", "model": "m"})
        c.post("/api/settings/provider/test", json={"kind": "vision", "base_url": "http://x/v1", "model": "m", "saved_key_of": "openai"})
    assert [s["family"] for s in seen] == ["openai", "local", "compatible", "openai"]
    assert seen[3]["key"] == "sk-saved", "an empty key field means: use the key saved for that provider"
    assert seen[0]["key"] == "sk-saved", "without saved_key_of, the provider's own saved key is used"
