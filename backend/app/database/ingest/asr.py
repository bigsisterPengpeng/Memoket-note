"""Speech-to-text provider layer: self-hosted whisper.cpp, AssemblyAI, Speechmatics.

`transcribe()` is the single entry point for every piece of transcribed text (knowledge-base
ingest, batch import and the editor's voice input all go through it), so provider dispatch and
the Whisper hallucination filter both live here. Which provider is active, and with which key,
comes from `store.get_active_asr_config()` (Settings page -> `provider_config` table, with the
`.env` values as deployment fallback). API keys are never logged and never appear in messages.

Hosted providers are asynchronous: upload -> create job -> poll until a terminal state, with a
bounded total budget (`ASR_POLL_TIMEOUT_S`, default 30 minutes) and a backing-off interval.

Endpoints verified against the official docs (2026-10):

whisper.cpp server (self-hosted; it runs with --inference-path /v1/audio/transcriptions, so the
path matches OpenAI's; `language` / `temperature` are whisper.cpp form extensions)
  POST {base}/v1/audio/transcriptions   multipart `file` + response_format / language / temperature
  GET  {base}/health

AssemblyAI   https://www.assemblyai.com/docs/api-reference/files/upload
             https://www.assemblyai.com/docs/api-reference/transcripts/submit
             https://www.assemblyai.com/docs/api-reference/transcripts/get
             https://www.assemblyai.com/docs/api-reference/transcripts/list
             https://www.assemblyai.com/docs/pre-recorded-audio/select-the-speech-model
  Hosts    https://api.assemblyai.com (US, default) / https://api.eu.assemblyai.com (EU)
  Header   `Authorization: <api key>` (no Bearer prefix)
  POST /v2/upload                raw bytes, Content-Type application/octet-stream -> {"upload_url"}
  POST /v2/transcript            {"audio_url", "language_detection": true | "language_code": "xx"}
                                 -> {"id", "status"}. `speech_models` (list; the singular
                                 `speech_model` is deprecated) is left out so the service default
                                 applies (universal-3-5-pro, falling back to universal-2).
  GET  /v2/transcript/{id}       status queued | processing | completed | error; `text`, `error`.
                                 Polling is capped at 60 requests/minute per key + transcript
                                 (429 with Retry-After), hence the backing-off interval.
  GET  /v2/transcript?limit=1    cheap authenticated call for the Settings "test" button.

Speechmatics batch   https://docs.speechmatics.com/api-ref/batch/create-a-new-job
                     https://docs.speechmatics.com/get-started/authentication (regional hosts)
                     https://docs.speechmatics.com/features-other/lang-id ("language": "auto")
  Hosts    https://eu1.asr.api.speechmatics.com/v2 (on-demand / EU, default)
           https://us1.asr.api.speechmatics.com/v2 (US)
  Header   `Authorization: Bearer <api key>`
  POST /jobs                     multipart `data_file` + `config` (JSON string):
                                 {"type": "transcription", "transcription_config":
                                  {"language": "auto" | code, "model": "enhanced"}}
                                 -> 201 {"id"}. Use `model`; `operating_point` is deprecated.
  GET  /jobs/{id}                {"job": {"status": running | done | rejected | deleted | expired,
                                          "errors": [{"message"}]}}
  GET  /jobs/{id}/transcript?format=txt   plain text (formats: json-v2 default, txt, srt)
  GET  /jobs?limit=1             cheap authenticated call for the Settings "test" button.
  Language codes are Speechmatics' own: Mandarin is "cmn" (see `_SPEECHMATICS_LANG`).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Awaitable, Callable, Literal, TypeVar

import httpx

from .. import store
from ...util import i18n
from ...util.config import get_settings

Provider = Literal["whisper", "assemblyai", "speechmatics"]
PROVIDERS: tuple[str, ...] = ("whisper", "assemblyai", "speechmatics")
HOSTED: tuple[str, ...] = ("assemblyai", "speechmatics")
PROVIDER_LABEL: dict[str, str] = {
    "whisper": "Whisper server", "assemblyai": "AssemblyAI", "speechmatics": "Speechmatics",
}

ASSEMBLYAI_HOSTS: dict[str, str] = {
    "us": "https://api.assemblyai.com",
    "eu": "https://api.eu.assemblyai.com",
}
SPEECHMATICS_HOSTS: dict[str, str] = {
    "eu": "https://eu1.asr.api.speechmatics.com/v2",
    "us": "https://us1.asr.api.speechmatics.com/v2",
}
REGIONS: dict[str, dict[str, str]] = {"assemblyai": ASSEMBLYAI_HOSTS, "speechmatics": SPEECHMATICS_HOSTS}
DEFAULT_REGION: dict[str, str] = {"assemblyai": "us", "speechmatics": "eu"}

# Connection budget: 10 s to connect (an unreachable server must not make the user wait for the
# whole transcription budget), 30 min for a self-hosted transcription of a long recording.
CONNECT_TIMEOUT_S = 10.0
WHISPER_TIMEOUT_S = 1800.0
UPLOAD_TIMEOUT_S = 600.0
# Hosted providers: poll every 1 s at first, backing off x1.5 up to 10 s between polls.
POLL_INITIAL_S = 1.0
POLL_MAX_S = 10.0
POLL_BACKOFF = 1.5

# Tests swap these: `_sleep` for a no-op and `_TRANSPORT` for an `httpx.MockTransport`.
_sleep = asyncio.sleep
_TRANSPORT: httpx.AsyncBaseTransport | None = None

T = TypeVar("T")


class AsrError(Exception):
    """Errors this module raises itself (as opposed to raw httpx errors)."""


class AsrConfigError(AsrError):
    """The active hosted provider has no API key."""

    def __init__(self, provider: str):
        super().__init__(f"no API key for {provider}")
        self.provider = provider


class AsrTimeout(AsrError):
    """The hosted job did not reach a terminal state within the polling budget."""

    def __init__(self, provider: str, seconds: float):
        super().__init__(f"{provider} did not finish within {int(seconds)} s")
        self.provider, self.seconds = provider, seconds


class AsrJobError(AsrError):
    """The provider accepted the file but reported that transcription failed."""

    def __init__(self, provider: str, reason: str):
        super().__init__(f"{provider}: {reason}")
        self.provider, self.reason = provider, reason


def host_for(provider: str, region: str) -> str:
    """Regional API host for a hosted provider; an unknown or empty region means the default."""
    hosts = REGIONS[provider]
    return hosts.get((region or "").strip().lower()) or hosts[DEFAULT_REGION[provider]]


def active_config() -> dict:
    """`store.get_active_asr_config()` plus the resolved `base_url` of the active provider."""
    cfg = store.get_active_asr_config()
    if cfg["provider"] in HOSTED:
        cfg["base_url"] = host_for(cfg["provider"], cfg["region"])
    return cfg


def _client(timeout: float | httpx.Timeout) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_TRANSPORT)


def _poll_timeout() -> float:
    return float(get_settings().asr_poll_timeout_s)


# ---------------------------------------------------------------- Whisper hallucination filter
# On silence and music Whisper produces a handful of stock sentences that appear far too often in
# its training data (subtitled video endings). They are hallucinations, not recognition errors:

# a tiny share, but they get recalled and cited and end up in the user's writing.
# Filtering here rather than at fact extraction: `transcribe()` is the only entry point for
# transcribed text, so one filter at the source covers every consumer.
# The list holds unambiguous whole sentences only. A first version used broad patterns
# ("subscribe", "thanks for watching", "subtitles") and hit 133 real sentences in which the user
# discussed his own email-subscription funnel. One notch wider and it misfires, so whole-sentence
# matching only; missing a hallucination is cheaper than deleting the user's words.
# The sentences are Chinese and are kept as \u escapes because the repo forbids Han characters in
# code. In order: "please like, subscribe, share and tip to support the Mingjing and Diandian
# channels" (long and short), "thanks for watching, see you next time" (three variants), "this
# sentence is a Mandarin sentence", "subtitles provided by the Amara.org community", "subtitle
# volunteers", "thanks for watching".
_HALLUCINATED = (
    '\u8bf7\u4e0d\u541d\u70b9\u8d5e\u8ba2\u9605\u8f6c\u53d1\u6253\u8d4f\u652f\u6301\u660e\u955c\u4e0e\u70b9\u70b9\u680f\u76ee',
    '\u8bf7\u4e0d\u541d\u70b9\u8d5e\u8ba2\u9605\u8f6c\u53d1\u6253\u8d4f',
    '\u8c22\u8c22\u89c2\u770b\uff0c\u4e0b\u6b21\u89c1\uff01',
    '\u8c22\u8c22\u89c2\u770b\uff0c\u4e0b\u6b21\u518d\u89c1',
    '\u611f\u8c22\u89c2\u770b\uff0c\u4e0b\u6b21\u518d\u89c1',
    '\u8fd9\u53e5\u5b50\u662f\u666e\u901a\u8bdd\u7684\u53e5\u5b50\u3002',
    '\u5b57\u5e55\u7531Amara.org\u793e\u533a\u63d0\u4f9b',
    '\u5b57\u5e55\u5fd7\u613f\u8005',
    '\u591a\u8c22\u6536\u770b',
)
# Sentence boundary: CJK full stop / exclamation / question mark, ASCII ! ?, newline.
_SPLIT = re.compile("(?<=[\u3002\uff01\uff1f!?\n])")
# Trailing punctuation ignored when comparing: CJK stop/!/?/enumeration comma/comma, ASCII ! ? ,
_TRAILING_PUNCT = "\u3002\uff01\uff1f!?\u3001,\uff0c"


def _normalize(sentence: str) -> str:
    return "".join(sentence.split()).strip(_TRAILING_PUNCT)


_NORMALIZED = {_normalize(p) for p in _HALLUCINATED}


def drop_hallucinations(text: str) -> str:
    """Remove the stock sentences Whisper recites on silence.

    Splits into sentences and compares each whole sentence (whitespace removed) against the list.
    No substring matching, for the reason given above: one notch wider and it deletes the user's
    own words about subscriptions.
    """
    if not text:
        return text
    kept = [part for part in _SPLIT.split(text) if _normalize(part) not in _NORMALIZED]
    return "".join(kept).strip()


# ---------------------------------------------------------------- transcription


async def transcribe(data: bytes, filename: str = "audio.wav",
                     language: str = "auto") -> str:
    """Transcribe `data` with the active provider and return plain text (hallucinations removed).

    `language` is "auto" or a Whisper-style code ("en", "zh"); hosted providers get it mapped to
    their own vocabulary. Raises httpx errors, `AsrConfigError` (hosted provider without key),
    `AsrTimeout` (polling budget exhausted) or `AsrJobError` (provider reported a failure);
    `describe_error()` turns any of them into one sentence for the user.
    """
    cfg = active_config()
    provider = cfg["provider"]
    if provider == "assemblyai":
        text = await _transcribe_assemblyai(data, cfg, language)
    elif provider == "speechmatics":
        text = await _transcribe_speechmatics(data, filename, cfg, language)
    else:
        text = await _transcribe_whisper(data, filename, cfg["base_url"], language)
    return drop_hallucinations((text or "").strip())


async def _transcribe_whisper(data: bytes, filename: str, base: str, language: str) -> str:
    async with _client(httpx.Timeout(WHISPER_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)) as client:
        r = await client.post(
            f"{base}/v1/audio/transcriptions",
            files={"file": (filename, data)},
            data={"response_format": "json", "language": language or "auto",
                  "temperature": "0.0"},
        )
        r.raise_for_status()
        payload = r.json()
    return payload.get("text") or ""


def _require_key(cfg: dict) -> str:
    key = (cfg.get("api_key") or "").strip()
    if not key:
        raise AsrConfigError(cfg["provider"])
    return key


async def _poll_until(provider: str, step: Callable[[], Awaitable[T | None]]) -> T:
    """Call `step()` until it returns a result, sleeping with backoff in between; give up after
    the configured total budget."""
    budget = _poll_timeout()
    deadline = time.monotonic() + budget
    delay = POLL_INITIAL_S
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AsrTimeout(provider, budget)
        try:
            # The HTTP read itself must fit inside the polling budget, not only the sleeps.
            out = await asyncio.wait_for(step(), timeout=remaining)
        except asyncio.TimeoutError:
            raise AsrTimeout(provider, budget) from None
        if out is not None:
            return out
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AsrTimeout(provider, budget)
        await _sleep(min(delay, remaining))
        delay = min(delay * POLL_BACKOFF, POLL_MAX_S)


def _assemblyai_lang(language: str) -> str:
    # AssemblyAI codes are lower case with an underscore for regional variants (en_us, en_au).
    return language.strip().lower().replace("-", "_")


async def _transcribe_assemblyai(data: bytes, cfg: dict, language: str) -> str:
    key = _require_key(cfg)
    base = cfg["base_url"]
    headers = {"Authorization": key}
    async with _client(httpx.Timeout(UPLOAD_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)) as client:
        r = await client.post(f"{base}/v2/upload", content=data,
                              headers={**headers, "Content-Type": "application/octet-stream"})
        r.raise_for_status()
        audio_url = r.json()["upload_url"]
        body: dict = {"audio_url": audio_url}
        if not language or language == "auto":
            body["language_detection"] = True
        else:
            body["language_code"] = _assemblyai_lang(language)
        r = await client.post(f"{base}/v2/transcript", json=body, headers=headers)
        r.raise_for_status()
        transcript_id = r.json()["id"]

        async def step() -> str | None:
            r = await client.get(f"{base}/v2/transcript/{transcript_id}", headers=headers)
            if r.status_code == 429:        # polling cap: treat as "not yet", the backoff handles it
                return None
            r.raise_for_status()
            j = r.json()
            status = j.get("status")
            if status == "completed":
                return j.get("text") or ""
            if status == "error":
                raise AsrJobError("assemblyai", str(j.get("error") or "error"))
            return None

        return await _poll_until("assemblyai", step)


# Whisper-style codes that Speechmatics spells differently. Everything else is passed through as
# its two-letter base ("en-US" -> "en").
_SPEECHMATICS_LANG = {"zh": "cmn", "zh-cn": "cmn", "zh-tw": "cmn", "zh-hans": "cmn", "zh-hant": "cmn",
                      "yue": "yue"}


def _speechmatics_lang(language: str) -> str:
    code = (language or "auto").strip().lower().replace("_", "-")
    if code in ("", "auto"):
        return "auto"
    if code in _SPEECHMATICS_LANG:
        return _SPEECHMATICS_LANG[code]
    return code.split("-")[0]


async def _transcribe_speechmatics(data: bytes, filename: str, cfg: dict, language: str) -> str:
    key = _require_key(cfg)
    base = cfg["base_url"]
    headers = {"Authorization": f"Bearer {key}"}
    config = {"type": "transcription",
              "transcription_config": {"language": _speechmatics_lang(language),
                                       "model": "enhanced"}}
    async with _client(httpx.Timeout(UPLOAD_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)) as client:
        r = await client.post(f"{base}/jobs", files={"data_file": (filename, data)},
                              data={"config": json.dumps(config)}, headers=headers)
        r.raise_for_status()
        job_id = r.json()["id"]

        async def step() -> str | None:
            r = await client.get(f"{base}/jobs/{job_id}", headers=headers)
            if r.status_code == 429:
                return None
            r.raise_for_status()
            payload = r.json()
            job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
            status = job.get("status")
            if status == "done":
                t = await client.get(f"{base}/jobs/{job_id}/transcript", params={"format": "txt"},
                                     headers=headers)
                t.raise_for_status()
                return t.text
            if status in ("rejected", "deleted", "expired"):
                errors = job.get("errors") or []
                reason = next((str(e.get("message")) for e in errors
                               if isinstance(e, dict) and e.get("message")), status)
                raise AsrJobError("speechmatics", reason)
            return None

        return await _poll_until("speechmatics", step)


async def healthy() -> bool:
    """Status-bar check. Self-hosted: `GET /health` with a 2 s budget (it either answers at once
    on the LAN or is not running). Hosted: the key is present; the health endpoint is polled often
    and must not spend the account's rate limit."""
    cfg = active_config()
    if cfg["provider"] in HOSTED:
        return bool(cfg["api_key"])
    try:
        async with _client(2.0) as client:
            r = await client.get(f"{cfg['base_url']}/health")
            return r.status_code == 200
    except Exception:
        return False


async def probe_hosted(provider: str, api_key: str, region: str = "",
                       *, timeout: float = 8.0) -> tuple[bool, str, int]:
    """Settings "test" button for a hosted provider: one authenticated list call that proves the
    key without uploading audio. Returns (ok, sentence for the user, elapsed ms)."""
    if provider not in HOSTED:
        raise ValueError(f"not a hosted provider: {provider}")
    label = PROVIDER_LABEL[provider]
    key = (api_key or "").strip()
    if not key:
        return False, i18n.msg("No API key for {provider} - paste the key first", provider=label), 0
    base = host_for(provider, region)
    if provider == "assemblyai":
        url, headers = f"{base}/v2/transcript", {"Authorization": key}
    else:
        url, headers = f"{base}/jobs", {"Authorization": f"Bearer {key}"}
    t0 = time.perf_counter()

    def ms() -> int:
        return int((time.perf_counter() - t0) * 1000)

    try:
        async with _client(timeout) as client:
            r = await client.get(url, params={"limit": 1}, headers=headers)
    except httpx.HTTPError as exc:
        return False, i18n.msg("Could not reach {provider} at {base}: {error} - check the network connection",
                               provider=label, base=base, error=type(exc).__name__), ms()
    if r.status_code == 200:
        return True, i18n.msg("{provider} accepted the API key ({base}, {ms} ms)",
                              provider=label, base=base, ms=ms()), ms()
    return False, _status_sentence(label, base, r.status_code), ms()


def _status_sentence(label: str, base: str, status: int) -> str:
    if status in (401, 403):
        return i18n.msg("{provider} rejected the API key ({status}) - check the key in Settings",
                        provider=label, status=status)
    if status == 402:
        return i18n.msg("{provider} reports that the account has no credit left (402)", provider=label)
    if status == 429:
        return i18n.msg("{provider} is rate-limiting requests (429) - try again in a minute", provider=label)
    return i18n.msg("{provider} returned {status} ({base}) - transcription failed, try again later",
                    provider=label, status=status, base=base)


# ---------------------------------------------------------------- error sentences


def describe_error(exc: BaseException) -> str:
    """The sentence the user sees when transcription fails. It names the voice service (and which
    provider), never the LLM: a misdirected "check the LLM provider in Settings" sent people to
    the wrong screen. Keys are never part of the sentence."""
    cfg = active_config()
    provider, base = cfg["provider"], cfg["base_url"]
    label = PROVIDER_LABEL.get(provider, provider)
    hosted = provider in HOSTED
    if isinstance(exc, AsrConfigError):
        return i18n.msg("No API key for {provider} - add it in Settings under Voice service",
                        provider=PROVIDER_LABEL.get(exc.provider, exc.provider))
    if isinstance(exc, AsrTimeout):
        return i18n.msg("{provider} did not finish transcribing within {minutes} minutes - try a shorter recording or try again later",
                        provider=PROVIDER_LABEL.get(exc.provider, exc.provider),
                        minutes=max(1, int(round(exc.seconds / 60))))
    if isinstance(exc, AsrJobError):
        return i18n.msg("{provider} could not transcribe this recording: {reason}",
                        provider=PROVIDER_LABEL.get(exc.provider, exc.provider), reason=exc.reason[:160])
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        if hosted:
            return i18n.msg("Could not reach {provider} ({base}) - check the network connection",
                            provider=label, base=base)
        return i18n.msg("The voice service at {base} is unreachable - check the voice service address in Settings or make sure that server is running",
                        base=base)
    if isinstance(exc, httpx.TimeoutException):
        return i18n.msg("The voice service at {base} timed out - transcription did not finish, try again later",
                        base=base)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if hosted:
            return _status_sentence(label, base, status)
        return i18n.msg("The voice service returned {status} ({base}) - transcription failed, try again later",
                        status=status, base=base)
    if isinstance(exc, httpx.HTTPError):
        return i18n.msg("Connection to the voice service failed ({base}): {error}",
                        base=base, error=type(exc).__name__)
    return i18n.msg("Transcription failed: {error}", error=(str(exc).strip() or type(exc).__name__)[:160])
