"""LLM provider settings: preset mainstream providers (OpenAI / Anthropic / Gemini / DeepSeek / Qwen / ...)
+ local servers (Ollama / LM Studio) + a custom OpenAI-compatible endpoint. Global, not per user — see the
comments on the provider_config / provider_credentials tables in store.py. After a switch, llm.py (the
writing calls) and kite_memory.py (extraction / Q&A / entity merging) use the new provider without a restart.

P19 #1: the local model has its own address / model / key; vision can follow the writing model or be set
separately; every section has "Test" (`POST /provider/test`: really calls `/models`, falls back to one minimal
completion, and reports the result right away).

The preset registry lives in `util/providers.py`: default address, suggested model names, whether a key is
needed, and the request-body shape (family). Each provider keeps its own key / model / address (switching
never loses one); the API only reports "key set" plus the last four characters, **never the key itself**, and
nothing here is logged.
"""

from __future__ import annotations

import re
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..database import store
from ..database.ingest import asr
from ..util import i18n, llm, providers
from ..util.config import get_settings
from .schemas import ProviderConfigIn, ProviderConfigOut, ProviderPresetOut, ProviderTestIn, ProviderTestOut
from .deps import current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])

_URL_RE = re.compile(r"^https?://[^\s/]+")


def _preset_out(p: dict, cfg: dict, s) -> ProviderPresetOut:
    """One preset plus what is saved for it. The `local` entry's default address / model come from .env /
    factory defaults (P19 #1); every other entry from the registry. The key is reported as set/unset + tail only."""
    creds = store.get_provider_credentials(p["id"], cfg)
    key = creds["api_key"]
    models = list(p["models"])
    base_default = p["base_url"]
    if p["id"] == "local":
        base_default = s.llm_base_url
        if s.llm_model and s.llm_model not in models:
            models.insert(0, s.llm_model)
    return ProviderPresetOut(
        id=p["id"], label=p["label"], base_url=base_default, models=models,
        needs_key=p["needs_key"], family=p["family"], group=p["group"], docs=p["docs"],
        key_set=bool(key), key_preview=f"...{key[-4:]}" if key else "",
        model=creds["model"], base_url_saved=creds["base_url"])


def _to_out(cfg: dict) -> ProviderConfigOut:
    key = cfg["gpt_api_key"]
    s = get_settings()
    active = store.get_active_llm_config()
    vision = store.get_active_vision_config()
    conf = store.llm_configured()
    return ProviderConfigOut(
        provider=cfg["provider"],
        gpt_model=cfg["gpt_model"],
        gpt_base_url=cfg["gpt_base_url"],
        gpt_api_key_set=bool(key),
        gpt_api_key_preview=f"...{key[-4:]}" if key else "",
        asr_base_url=cfg["asr_base_url"],
        asr_default_url=s.whisper_base_url,
        **_asr_out(cfg),
        auto_sync_notes=bool(cfg.get("auto_sync_notes")),
        vision_base_url=cfg["vision_base_url"],
        vision_model=cfg["vision_model"],
        vision_api_key_set=bool(cfg["vision_api_key"]),
        vision_follows_llm=bool(vision["follows_llm"]),
        vision_active_url=vision["base_url"],
        vision_active_model=vision["model"],
        local_base_url=cfg["local_base_url"],
        local_model=cfg["local_model"],
        local_api_key_set=bool(cfg["local_api_key"]),
        local_default_url=s.llm_base_url,
        local_default_model=s.llm_model,
        configured=conf["configured"],
        configured_source=conf["source"],
        active_url=active["base_url"],
        active_model=active["model"],
        active_provider=active.get("provider", ""),
        active_family=active.get("family", ""),
        providers=[_preset_out(p, cfg, s) for p in providers.preset_dicts()],
    )


def _asr_out(cfg: dict) -> dict:
    """Voice-service fields of ProviderConfigOut. A key counts as set when either the Settings
    page or `.env` supplies it; only a 4-character tail is ever shown."""
    s = get_settings()
    out: dict = {"asr_provider": store.get_active_asr_config()["provider"]}
    for p in asr.HOSTED:
        key = cfg[f"{p}_api_key"] or getattr(s, f"{p}_api_key")
        out[f"{p}_api_key_set"] = bool(key)
        out[f"{p}_api_key_preview"] = f"...{key[-4:]}" if key else ""
        region = (cfg[f"{p}_region"] or getattr(s, f"{p}_region") or "").strip().lower()
        out[f"{p}_region"] = region if region in asr.REGIONS[p] else asr.DEFAULT_REGION[p]
    return out


def _asr_provider(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip().lower()
    if v not in asr.PROVIDERS:
        raise HTTPException(400, "asr_provider must be whisper / assemblyai / speechmatics")
    return v


def _asr_region(provider: str, v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip().lower()
    if v and v not in asr.REGIONS[provider]:
        raise HTTPException(400, f"{provider}_region must be one of {' / '.join(asr.REGIONS[provider])}")
    return v


@router.get("/provider", response_model=ProviderConfigOut)
def get_provider():
    return _to_out(store.get_provider_config())


def _url(v: str | None, what: str, allow_empty: bool) -> str | None:
    """The API once stored "not a url" / "192.168.1.1:8081" (no scheme) verbatim (round 251), and every
    later model / transcription call failed with a baffling connection error. Only http(s):// is accepted
    here; a trailing slash is dropped. `what` is the English label of the field (translated for the error)."""
    if v is None:
        return None
    v = v.strip().rstrip("/")
    if not v:
        if allow_empty:
            return ""
        raise HTTPException(400, i18n.msg("{what} must not be empty", what=i18n.msg(what)))
    if not _URL_RE.match(v):
        raise HTTPException(400, i18n.msg("{what} must start with http:// or https://: {url}",
                                          what=i18n.msg(what), url=v[:60]))
    return v


def _key(v: str | None) -> str | None:
    # a whitespace-only key means "not entered": keep the saved one ("  " used to be stored as a new key)
    if v is None:
        return None
    v = v.strip()
    return v or None


def _key_or_clear(v: str | None) -> str | None:
    """New-style `api_key`: omitted = keep; **explicit empty string = clear** (the settings page's "Clear saved
    key" sends exactly that); whitespace only = not entered, keep (same as `_key`: never store "  " as a key)."""
    if v is None:
        return None
    if v == "":
        return ""
    return v.strip() or None


@router.post("/provider", response_model=ProviderConfigOut)
def set_provider(body: ProviderConfigIn):
    if body.provider not in providers.PROVIDERS:
        raise HTTPException(400, f"provider must be one of: {', '.join(providers.PROVIDERS)}")
    model = body.gpt_model.strip() if body.gpt_model is not None else None
    if model == "":
        raise HTTPException(400, i18n.msg("Model name must not be empty"))
    cfg = store.set_provider_config(
        body.provider, gpt_api_key=_key(body.gpt_api_key),
        gpt_model=model, gpt_base_url=_url(body.gpt_base_url, "Model address", allow_empty=False),
        asr_base_url=_url(body.asr_base_url, "Voice service address", allow_empty=True),
        auto_sync_notes=body.auto_sync_notes,
        # local model / vision: an empty address clears it and falls back to the default (like the voice
        # address, empty is a valid value); a whitespace-only key leaves the saved one alone
        local_base_url=_url(body.local_base_url, "Local model address", allow_empty=True),
        local_model=body.local_model.strip() if body.local_model is not None else None,
        local_api_key=_key(body.local_api_key),
        vision_base_url=_url(body.vision_base_url, "Vision model address", allow_empty=True),
        vision_model=body.vision_model.strip() if body.vision_model is not None else None,
        vision_api_key=_key(body.vision_api_key),
        # new-style fields for the selected provider: empty address = preset default; empty key = clear,
        # whitespace = keep
        api_key=_key_or_clear(body.api_key),
        model=body.model.strip() if body.model is not None else None,
        base_url=_url(body.base_url, "Model address", allow_empty=True),
        asr_provider=_asr_provider(body.asr_provider),
        assemblyai_api_key=_key(body.assemblyai_api_key),
        assemblyai_region=_asr_region("assemblyai", body.assemblyai_region),
        speechmatics_api_key=_key(body.speechmatics_api_key),
        speechmatics_region=_asr_region("speechmatics", body.speechmatics_region))
    return _to_out(cfg)


def _saved_key(slot: str) -> str:
    """An empty test key uses the key saved for that voice service, vision endpoint or LLM preset."""
    cfg = store.get_provider_config()
    if slot in asr.HOSTED:
        return cfg[f"{slot}_api_key"] or getattr(get_settings(), f"{slot}_api_key")
    if slot == "vision":
        return store.get_provider_config()["vision_api_key"]
    if slot in providers.PROVIDERS:
        return store.get_provider_credentials(slot)["api_key"]
    return ""


async def probe_endpoint(kind: str, base_url: str, model: str = "", api_key: str = "",
                         *, family: str = providers.DEFAULT_FAMILY,
                         timeout: float = 8.0, client: httpx.AsyncClient | None = None) -> ProviderTestOut:
    """Really connect once. Voice: `GET {base}/health`. Models: first `GET {base}/models` (which models exist,
    whether the entered one is among them); if the list is unavailable (some gateways do not implement it),
    send one minimal chat completion. **The result is one human sentence** naming the address actually
    tried, not some default from elsewhere.

    `family` picks the limit field of that minimal completion: the `openai` family sends
    `max_completion_tokens=1` (reasoning-tier models reject `max_tokens`, P26 #1), everything else sends
    `max_tokens=1`; if the endpoint rejects the field, the other one is tried once.

    **The vision section also sends an image** (P23 #4): with `kind == "vision"` the probe does not just ask
    "is it reachable" but sends the three-digit image drawn by `util/probe_image` and asks the model to read
    it — a text-only model is reachable and returns 200 too, so "connected" proves nothing about vision."""
    t0 = time.perf_counter()
    base = base_url.strip().rstrip("/")
    if not _URL_RE.match(base):
        return ProviderTestOut(ok=False, message=i18n.msg("Address must start with http:// or https://: {url}",
                                                          url=base[:60] or i18n.msg("(empty)")))

    def ms() -> int:
        return int((time.perf_counter() - t0) * 1000)

    own = client is None
    c = client or httpx.AsyncClient(timeout=timeout)
    try:
        if kind == "asr":
            try:
                r = await c.get(f"{base}/health")
            except httpx.HTTPError as exc:
                return ProviderTestOut(ok=False, elapsed_ms=ms(), message=i18n.msg(
                    "Could not reach the voice service at {base}: {error} - make sure the whisper.cpp server is running and the address and port are right",
                    base=base, error=type(exc).__name__))
            if r.status_code == 200:
                return ProviderTestOut(ok=True, elapsed_ms=ms(), message=i18n.msg(
                    "Voice service at {base} answered in {ms} ms", base=base, ms=ms()))
            return ProviderTestOut(ok=False, elapsed_ms=ms(), message=i18n.msg(
                "{base}/health returned {status} - this does not look like a whisper.cpp server",
                base=base, status=r.status_code))

        async def vision_ok(found: bool | None) -> ProviderTestOut:
            """**Vision section: really send an image** (P23 #4). P19 wired "Test" to all three sections, but the
            vision one ran the same probe as the writing model (`/models` or a text-only completion) — that
            "connected" proves nothing about vision; a text-only model passed and the user only found out when
            "image to table" produced nonsense. The probe image carries a three-digit number (`util/probe_image`);
            only reading it correctly counts (guessing: 1/900). It goes through `vision.ask_image` itself, not a
            hand-built request — the gate must guard the real path (P21)."""
            from ..editor import vision
            from ..util.probe_image import PROBE_NUMBER, probe_png
            try:
                answer = await vision.ask_image(
                    "This image shows a three-digit number. Reply with just those three digits and nothing else.",
                    # reasoning models spend part of the completion budget on reasoning; with 24 the model

                    probe_png(), max_tokens=128, timeout=timeout,
                    cfg={"base_url": base, "model": model, "api_key": api_key, "family": family})
            except vision.VisionError as exc:
                return ProviderTestOut(
                    ok=False, models=models[:50], model_found=found, elapsed_ms=ms(),
                    message=i18n.msg(
                        "Connected, but sending an image failed: {err} — this model probably does not accept images; pick one with vision (e.g. qwen2.5vl)",
                        err=str(exc)[:160]))
            if PROBE_NUMBER in answer:
                return ProviderTestOut(ok=True, models=models[:50], model_found=found, elapsed_ms=ms(),
                                       message=i18n.msg("\"{model}\" read {number} from the image — vision works ({ms} ms)",
                                                        model=model, number=PROBE_NUMBER, ms=ms()))
            return ProviderTestOut(
                ok=False, models=models[:50], model_found=found, elapsed_ms=ms(),
                message=i18n.msg(
                    "\"{model}\" accepted the image but did not read {number} (it answered \"{answer}\") — this model probably lacks vision; screen activity / image-to-table would produce made-up results",
                    model=model, number=PROBE_NUMBER, answer=answer[:60] or i18n.msg("(empty)")))

        headers = {"Authorization": f"Bearer {api_key or 'no-key'}"}
        models: list[str] = []
        list_err = ""
        try:
            r = await c.get(f"{base}/models", headers=headers)
            if r.status_code in (401, 403):
                return ProviderTestOut(ok=False, elapsed_ms=ms(), message=i18n.msg(
                    "{base} rejected the request ({code}): wrong API key or no permission", base=base, code=r.status_code))
            if r.status_code == 200:
                data = r.json()
                items = data.get("data") if isinstance(data, dict) else data
                models = [str(m.get("id") or m.get("name") or "") for m in (items or []) if isinstance(m, dict)]
                models = [m for m in models if m]
            else:
                list_err = i18n.msg("/models returned {code}", code=r.status_code)
        except httpx.HTTPError as exc:
            return ProviderTestOut(ok=False, elapsed_ms=ms(), message=i18n.msg(
                "Cannot reach {base}: {err} — make sure the server is running and the address and port are right (local Ollama is http://127.0.0.1:11434/v1)",
                base=base, err=type(exc).__name__))
        except ValueError:
            list_err = i18n.msg("/models did not return JSON")
        if models:
            if not model:
                return ProviderTestOut(ok=True, models=models[:50], model_found=None, elapsed_ms=ms(), message=i18n.msg(
                    "Connected; {n} models available. No model name yet — start with the first one, \"{first}\"",
                    n=len(models), first=models[0]))
            if model in models:
                if kind == "vision":
                    return await vision_ok(True)
                return ProviderTestOut(ok=True, models=models[:50], model_found=True, elapsed_ms=ms(), message=i18n.msg(
                    "Connected; \"{model}\" is available at {base} ({ms} ms)", model=model, base=base, ms=ms()))
            shown = ", ".join(models[:5]) + ("…" if len(models) > 5 else "")
            return ProviderTestOut(ok=False, models=models[:50], model_found=False, elapsed_ms=ms(), message=i18n.msg(
                "Connected, but {base} has no \"{model}\" — available: {shown}", base=base, model=model, shown=shown))
        # no list: send one minimal completion
        if not model:
            return ProviderTestOut(ok=False, elapsed_ms=ms(), message=i18n.msg(
                "Connected to {base}, but the model list is unavailable ({err}) and no model name is set — enter a model name and test again",
                base=base, err=list_err or i18n.msg("empty list")))
        if kind == "vision":
            return await vision_ok(None)
        # the limit field follows the family (`util/providers.py`): reasoning-tier models of the `openai`

        # denominator (Ollama / LM Studio only know that one)
        limit_field = "max_completion_tokens" if family == "openai" else "max_tokens"
        probe_body = {"model": model, "messages": [{"role": "user", "content": "hi"}],
                      limit_field: 1}
        try:
            r = await c.post(f"{base}/chat/completions", headers=headers, json=probe_body)

            # runs when `/models` is unavailable, but when it does, "Test" must not call a perfectly good
            # configuration "returned 400" while the writing path (`util/llm._payload`) works. Same path as
            # `vision.ask_image`.
            if llm.rejects_max_tokens(r.status_code, r.content) and \
                    llm.swap_to_max_completion_tokens(probe_body):
                r = await c.post(f"{base}/chat/completions", headers=headers, json=probe_body)
            elif llm.rejects_max_completion_tokens(r.status_code, r.content) and \
                    "max_completion_tokens" in probe_body:
                probe_body["max_tokens"] = probe_body.pop("max_completion_tokens")
                r = await c.post(f"{base}/chat/completions", headers=headers, json=probe_body)
        except httpx.HTTPError as exc:
            return ProviderTestOut(ok=False, elapsed_ms=ms(),
                                   message=i18n.msg("Cannot reach {base}: {err}", base=base, err=type(exc).__name__))
        if r.status_code == 200:
            return ProviderTestOut(ok=True, model_found=None, elapsed_ms=ms(),
                                   message=i18n.msg("\"{model}\" at {base} answered ({ms} ms)", model=model, base=base, ms=ms()))
        if r.status_code in (401, 403):
            return ProviderTestOut(ok=False, elapsed_ms=ms(), message=i18n.msg(
                "{base} rejected the request ({code}): wrong API key or no permission", base=base, code=r.status_code))
        if r.status_code == 404:
            return ProviderTestOut(ok=False, elapsed_ms=ms(), message=i18n.msg(
                "{base} has no model or endpoint named \"{model}\" (404)", base=base, model=model))
        return ProviderTestOut(ok=False, elapsed_ms=ms(),
                               message=i18n.msg("{base} returned {code}: {text}", base=base, code=r.status_code, text=r.text[:120]))
    finally:
        if own:
            await c.aclose()


@router.post("/provider/test", response_model=ProviderTestOut)
async def test_provider(body: ProviderTestIn):
    if body.kind not in ("llm", "vision", "asr"):
        raise HTTPException(400, "kind must be llm / vision / asr")
    provider = (body.asr_provider or "").strip().lower()
    if body.kind == "asr" and provider in asr.HOSTED:

        key = (body.api_key or "").strip() or _saved_key(provider)
        ok, message, elapsed = await asr.probe_hosted(provider, key, body.region)
        return ProviderTestOut(ok=ok, message=message, elapsed_ms=elapsed)
    if body.kind == "asr" and provider not in ("", "whisper"):
        raise HTTPException(400, "asr_provider must be whisper / assemblyai / speechmatics")
    # empty key field: use the key saved for `saved_key_of`; without that, the key of `provider` itself
    key = (body.api_key or "").strip() or _saved_key(body.saved_key_of or body.provider)
    # request-body shape by preset id (no provider -> saved_key_of; 'vision' / empty -> compatible:
    # max_tokens first, then negotiate)
    family = providers.family_of(body.provider or body.saved_key_of)
    return await probe_endpoint(body.kind, body.base_url, body.model.strip(), key, family=family)


@router.get("/usage")
def usage(user: str = Depends(current_user)) -> dict:
    """Model usage: calls and tokens for today / 7 days / 30 days / all time, by feature. Only calls made through
    this repo's util/llm are recorded (writing trio, continue, blocks, checks...); KITE extraction uses its own
    provider and is estimated from character counts inside the import job."""
    return store.usage_summary(user)
