"""LLM provider config (local model vs GPT): store.py reads/writes + how get_active_llm_config()
falls back to defaults between the two.

    cd backend && python -m pytest tests/test_provider_config.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import store# noqa: E402


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    return store


def test_get_provider_config_defaults_to_local_when_unset(isolated_store):
    cfg = isolated_store.get_provider_config()
    assert cfg["provider"] == "local"
    assert cfg["gpt_api_key"] == ""


def test_set_and_get_provider_config_round_trips(isolated_store):
    isolated_store.set_provider_config("gpt", gpt_api_key="sk-test123", gpt_model="gpt-4.1-mini")
    cfg = isolated_store.get_provider_config()
    assert cfg["provider"] == "gpt"
    assert cfg["gpt_api_key"] == "sk-test123"
    assert cfg["gpt_model"] == "gpt-4.1-mini"
    assert cfg["gpt_base_url"] == "https://api.openai.com/v1"  # not passed, falls back to the default


def test_set_provider_config_preserves_key_when_not_passed(isolated_store):
    # Save a key once, then switching provider on its own (e.g. gpt -> local -> gpt) must not require
    # typing the key again — switching provider back and forth should not clear the key
    isolated_store.set_provider_config("gpt", gpt_api_key="sk-keep-me")
    isolated_store.set_provider_config("local")
    isolated_store.set_provider_config("gpt")
    cfg = isolated_store.get_provider_config()
    assert cfg["gpt_api_key"] == "sk-keep-me"


def test_set_provider_config_rejects_invalid_provider(isolated_store):
    with pytest.raises(ValueError):
        isolated_store.set_provider_config("azure")


def test_get_active_llm_config_falls_back_to_local_settings_by_default(isolated_store, monkeypatch):
    fake_settings = SimpleNamespace(
        llm_base_url="http://local-model:8080/v1", llm_api_key="no-key", llm_model="muse-glimmer-30b")
    monkeypatch.setattr(store, "get_settings", lambda: fake_settings)

    active = isolated_store.get_active_llm_config()
    assert active == {"base_url": "http://local-model:8080/v1", "api_key": "no-key",
                      "model": "muse-glimmer-30b", "provider": "local", "family": "local"}


def test_get_active_llm_config_uses_gpt_once_selected_with_a_key(isolated_store, monkeypatch):
    fake_settings = SimpleNamespace(
        llm_base_url="http://local-model:8080/v1", llm_api_key="no-key", llm_model="muse-glimmer-30b")
    monkeypatch.setattr(store, "get_settings", lambda: fake_settings)

    isolated_store.set_provider_config("gpt", gpt_api_key="sk-real-key", gpt_model="gpt-4.1-mini")
    active = isolated_store.get_active_llm_config()
    # The `provider` field was added in P30 #5 (and `family` with the presets): `llm._payload` uses them to
    # decide whether to send `max_tokens` (Ollama / LM Studio only honour `max_tokens`, and silently ignore
    # unknown fields = no cap). **These two keep using full equality**, not a subset comparison — a missing
    # field should go red; that is exactly what it guards against.
    assert active == {
        "base_url": "https://api.openai.com/v1", "api_key": "sk-real-key",
        "model": "gpt-4.1-mini", "provider": "gpt", "family": "openai"}


def test_get_active_llm_config_falls_back_when_gpt_selected_but_no_key_yet(isolated_store, monkeypatch):
    # provider='gpt' selected but no key yet (e.g. just switched, form not saved yet) — must not call
    # OpenAI with an empty key; falling back to the local model is safer than erroring out
    fake_settings = SimpleNamespace(
        llm_base_url="http://local-model:8080/v1", llm_api_key="no-key", llm_model="muse-glimmer-30b")
    monkeypatch.setattr(store, "get_settings", lambda: fake_settings)

    isolated_store.set_provider_config("gpt")  # gpt_api_key not passed
    active = isolated_store.get_active_llm_config()
    assert active["base_url"] == "http://local-model:8080/v1"


def test_asr_base_url_round_trip_and_fallback(isolated_store):
    """Voice service address: unset falls back to the .env default; set uses it (trailing / stripped); empty string clears it back to the default."""
    from app.util.config import get_settings

    assert isolated_store.get_asr_base_url() == get_settings().whisper_base_url
    isolated_store.set_provider_config("local", asr_base_url="http://127.0.0.1:8081/")
    assert isolated_store.get_asr_base_url() == "http://127.0.0.1:8081"
    # changing other fields leaves it alone
    isolated_store.set_provider_config("gpt", gpt_api_key="sk-x")
    assert isolated_store.get_asr_base_url() == "http://127.0.0.1:8081"
    isolated_store.set_provider_config("gpt", asr_base_url="")
    assert isolated_store.get_asr_base_url() == get_settings().whisper_base_url
